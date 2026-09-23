from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.exceptions import PermissionError, ValidationError
from src.model.kanban_models import Task
from src.model.notification import NotificationType
from src.schema.kanban import TaskCreate, TaskUpdate
from src.services.kanban_service import KanbanService

CREATOR_ID = 5
TEAM_ASSIGNEE_ID = 5
OUTSIDER_ID = 10


def _make_service(notification_service=None, mail_service=None):
    column_repo = Mock()
    task_repo = Mock()
    subtask_repo = Mock()
    user_repo = Mock()
    project_repo = Mock()
    service = KanbanService(
        column_repo,
        task_repo,
        subtask_repo,
        user_repo,
        project_repo,
        notification_service=notification_service,
        mail_service=mail_service,
    )
    return service, column_repo, task_repo, subtask_repo, user_repo, project_repo


class TestKanbanTeamAccess:
    """Канбан-задачи доступны только участникам проекта (команды)."""

    @pytest.mark.asyncio
    async def test_should_deny_create_task_for_non_member(self):
        """Не-участник проекта не может создавать задачи"""
        # given
        service, column_repo, task_repo, _, _, project_repo = _make_service()
        column_repo.get_by_id = AsyncMock(return_value=Mock(project_id=1, id=1))
        project_repo.get_by_id = AsyncMock(return_value=Mock(id=1))
        project_repo.is_user_in_project = AsyncMock(return_value=False)

        task_data = TaskCreate(column_id=1, title="Task")
        task_repo.create = AsyncMock(return_value=Mock(id=1, column_id=1, title="Task"))

        # when / then
        with pytest.raises(PermissionError, match="has no access to project"):
            await service.create_task(task_data, current_user_id=CREATOR_ID)

    @pytest.mark.asyncio
    async def test_should_deny_update_assignee_outside_team(self):
        """Нельзя назначить ответственным пользователя вне команды проекта"""
        # given
        service, column_repo, task_repo, _, user_repo, project_repo = _make_service()
        column_repo.get_by_id = AsyncMock(return_value=Mock(project_id=1, id=1))
        task_repo.get_by_id = AsyncMock(return_value=Mock(id=1, column_id=1))
        project_repo.get_by_id = AsyncMock(return_value=Mock(id=1))

        # автор задачи — участник, но ассайнится сторонний пользователь
        project_repo.is_user_in_project = AsyncMock(side_effect=lambda _project_id, user_id: user_id == CREATOR_ID)

        task_data = TaskUpdate(assignee_ids=[OUTSIDER_ID])
        task_repo.update = AsyncMock()
        user_repo.get_by_id = AsyncMock(return_value=Mock(first_name="A", last_name="B"))

        # when / then
        with pytest.raises(ValidationError, match="not a member of project"):
            await service.update_task(1, task_data, current_user_id=CREATOR_ID)

    @pytest.mark.asyncio
    async def test_should_update_task_with_team_assignee(self):
        """Ассайн участника проекта разрешён"""
        # given
        service, column_repo, task_repo, _, user_repo, project_repo = _make_service()
        column_repo.get_by_id = AsyncMock(return_value=Mock(project_id=1, id=1))
        old_task = Mock(id=1, column_id=1, title="Task", assignees=[])
        task_repo.get_by_id = AsyncMock(return_value=old_task)
        project_repo.get_by_id = AsyncMock(return_value=Mock(id=1))
        project_repo.is_user_in_project = AsyncMock(side_effect=lambda _project_id, user_id: user_id == CREATOR_ID)
        user_repo.get_multi_by_ids = AsyncMock(return_value=[Mock(id=TEAM_ASSIGNEE_ID)])
        updated_task = Task(
            id=1,
            column_id=1,
            project_id=1,
            title="Task",
            created_by_id=CREATOR_ID,
            position=0,
            description="",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        task_repo.update = AsyncMock(return_value=updated_task)
        user_repo.get_by_id = AsyncMock(return_value=Mock(first_name="A", last_name="B"))

        task_data = TaskUpdate(assignee_ids=[TEAM_ASSIGNEE_ID])

        # when
        result = await service.update_task(1, task_data, current_user_id=CREATOR_ID)

        # then
        assert result.id == 1
        task_repo.update.assert_awaited_once()


# ============================================================
# Уведомления (in-app + почта) для канбан-событий
# ============================================================


def _user(user_id: int, email: str | None = "user@test.ru"):
    """Мок пользователя — получателя уведомлений."""
    return Mock(id=user_id, email=email, first_name="Иван", last_name="Петров", middle_name="Иванович")


def _actor(user_id: int = CREATOR_ID):
    """Мок инициатора действия."""
    return _user(user_id)


def _task_obj(assignees, created_by_id=CREATOR_ID, project_id=1, title="Задача", column_name="В процессе"):
    """Мок задачи с mocked assignees/column/project."""
    task = Mock()
    task.id = 1
    task.column_id = 1
    task.project_id = project_id
    task.title = title
    task.description = "Описание"
    task.priority = None
    task.due_date = None
    task.tags = None
    task.created_by_id = created_by_id
    task.position = 0
    task.assignees = assignees
    project = Mock()
    project.name = "Проект"
    column = Mock()
    column.name = column_name
    task.project = project
    task.column = column
    return task


def _subtask(task, title="Подзадача", is_completed=False):
    """Мок подзадачи с привязанной задачей."""
    return Mock(task=task, task_id=task.id, title=title, is_completed=is_completed)


class TestKanbanNotifications:
    """Канбан-события создают уведомления и отправляют письма."""

    @pytest.mark.asyncio
    async def test_task_created_notifies_assignees_and_creator(self):
        """Создание задачи уведомляет ответственных и создателя, но не актора."""
        # given
        assignee = _user(2)
        assignee2 = _user(3)
        actor = _actor(5)
        task = _task_obj(assignees=[assignee, assignee2, _actor(5)], created_by_id=7)
        creator = _user(7)

        notification_service = Mock()
        notification_service.create_notification = AsyncMock()
        mail_service = Mock()
        mail_service.send_task_created_email = AsyncMock()
        service, _, _, _, user_repo, _ = _make_service(notification_service, mail_service)
        user_repo.get_by_id = AsyncMock(side_effect=lambda uid: actor if uid == 5 else creator)

        # when
        await service._notify_task_created(task, created_by_id=CREATOR_ID)

        # then: уведомления для assignee 2, assignee 3 и создателя 7 (актор 5 исключён)
        receivers = [call.kwargs["user_id"] for call in notification_service.create_notification.await_args_list]
        assert receivers == [2, 3, 7]
        call = notification_service.create_notification.await_args_list[0]
        assert call.kwargs["type"] == NotificationType.task_created
        assert call.kwargs["task_title"] == "Задача"
        assert call.kwargs["project_name"] == "Проект"

        # then: письма ушли всем получателям с почтой
        email_to = [call.kwargs["to"] for call in mail_service.send_task_created_email.await_args_list]
        assert email_to == ["user@test.ru", "user@test.ru", "user@test.ru"]

    @pytest.mark.asyncio
    async def test_task_created_skips_mail_without_email_but_notifies(self):
        """Получатель без email: уведомление создаётся, письмо не отправляется."""
        # given
        task = _task_obj(assignees=[_user(2, email=None)])
        notification_service = Mock()
        notification_service.create_notification = AsyncMock()
        mail_service = Mock()
        for name in (
            "send_task_created_email",
            "send_task_updated_email",
            "send_task_moved_email",
            "send_task_deleted_email",
            "send_subtask_created_email",
            "send_subtask_updated_email",
            "send_subtask_deleted_email",
        ):
            setattr(mail_service, name, AsyncMock())
        service, _, _, _, user_repo, _ = _make_service(notification_service, mail_service)
        user_repo.get_by_id = AsyncMock(return_value=_actor())

        # when
        await service._notify_task_created(task, created_by_id=CREATOR_ID)

        # then
        notification_service.create_notification.assert_awaited_once()
        mail_service.send_task_created_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_task_moved_notifies_and_sends_mail_with_columns(self):
        """Перемещение задачи передаёт в письмо названия колонок."""
        # given
        assignee = _user(2)
        old_task = _task_obj(assignees=[assignee], column_name="В процессе")
        new_task = _task_obj(assignees=[assignee], title="Задача", column_name="Готово")

        notification_service = Mock()
        notification_service.create_notification = AsyncMock()
        mail_service = Mock()
        mail_service.send_task_moved_email = AsyncMock()
        service, _, _, _, user_repo, _ = _make_service(notification_service, mail_service)
        user_repo.get_by_id = AsyncMock(return_value=_actor())

        # when
        await service._notify_task_moved(old_task, new_task, moved_by_id=CREATOR_ID)

        # then
        call = notification_service.create_notification.await_args_list[0]
        assert call.kwargs["type"] == NotificationType.task_moved
        assert call.kwargs["column_name"] == "Готово"
        email_call = mail_service.send_task_moved_email.await_args_list[0]
        assert email_call.kwargs["from_column"] == "В процессе"
        assert email_call.kwargs["to_column"] == "Готово"

    @pytest.mark.asyncio
    async def test_task_updated_without_changes_skips_notification(self):
        """Обновление без фактических изменений не шлёт уведомление."""
        # given
        assignee = _user(2)
        old_task = _task_obj(assignees=[assignee], title="Задача")
        new_task = _task_obj(assignees=[assignee], title="Задача")
        # поля-«Mock» в сравнении дадут детерминированное совпадение только если задать все целиком
        for attr in ("priority", "due_date", "tags"):
            setattr(old_task, attr, None)
            setattr(new_task, attr, None)

        notification_service = Mock()
        notification_service.create_notification = AsyncMock()
        mail_service = Mock()
        mail_service.send_task_updated_email = AsyncMock()
        service, _, _, _, user_repo, _ = _make_service(notification_service, mail_service)
        user_repo.get_by_id = AsyncMock(return_value=_actor())

        # when
        await service._notify_task_updated(old_task, new_task, updated_by_id=CREATOR_ID)

        # then
        notification_service.create_notification.assert_not_awaited()
        mail_service.send_task_updated_email.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_task_updated_sends_mail_with_changes(self):
        """Обновление полей задачи описывает изменения в письме."""
        # given
        assignee = _user(2, email="a@test.ru")
        old_task = _task_obj(assignees=[assignee], title="Старая")
        new_task = _task_obj(assignees=[assignee], title="Новая")
        for attr in ("priority", "due_date", "tags"):
            setattr(old_task, attr, None)
            setattr(new_task, attr, None)

        notification_service = Mock()
        notification_service.create_notification = AsyncMock()
        mail_service = Mock()
        mail_service.send_task_updated_email = AsyncMock()
        service, _, _, _, user_repo, _ = _make_service(notification_service, mail_service)
        user_repo.get_by_id = AsyncMock(return_value=_actor())

        # when
        await service._notify_task_updated(old_task, new_task, updated_by_id=CREATOR_ID)

        # then
        notification_service.create_notification.assert_awaited_once()
        email_call = mail_service.send_task_updated_email.await_args_list[0]
        assert "title" in email_call.kwargs["changes"]

    @pytest.mark.asyncio
    async def test_task_deleted_notifies(self):
        """Удаление задачи уведомляет ответственных."""
        # given
        assignee = _user(2)
        task = _task_obj(assignees=[assignee])
        notification_service = Mock()
        notification_service.create_notification = AsyncMock()
        mail_service = Mock()
        mail_service.send_task_deleted_email = AsyncMock()
        service, _, _, _, user_repo, _ = _make_service(notification_service, mail_service)
        user_repo.get_by_id = AsyncMock(return_value=_actor())

        # when
        await service._notify_task_deleted(task, deleted_by_id=CREATOR_ID)

        # then
        call = notification_service.create_notification.await_args_list[0]
        assert call.kwargs["type"] == NotificationType.task_deleted
        assert call.kwargs["user_id"] == 2

    @pytest.mark.asyncio
    async def test_subtask_created_and_deleted_notify(self):
        """Создание и удаление подзадачи уведомляют ответственных за задачу."""
        # given
        assignee = _user(2)
        task = _task_obj(assignees=[assignee])
        subtask = _subtask(task)
        notification_service = Mock()
        notification_service.create_notification = AsyncMock()
        mail_service = Mock()
        mail_service.send_subtask_created_email = AsyncMock()
        mail_service.send_subtask_deleted_email = AsyncMock()
        service, _, _, _, user_repo, _ = _make_service(notification_service, mail_service)
        user_repo.get_by_id = AsyncMock(return_value=_actor())

        # when
        await service._notify_subtask_created(subtask, created_by_id=CREATOR_ID)
        await service._notify_subtask_deleted(subtask, deleted_by_id=CREATOR_ID)

        # then
        created = notification_service.create_notification.await_args_list[0]
        deleted = notification_service.create_notification.await_args_list[1]
        assert created.kwargs["type"] == NotificationType.subtask_created
        assert created.kwargs["subtask_title"] == "Подзадача"
        assert deleted.kwargs["type"] == NotificationType.subtask_deleted
        mail_service.send_subtask_created_email.assert_awaited_once()
        mail_service.send_subtask_deleted_email.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subtask_toggled_sends_completed_flag(self):
        """Переключение статуса подзадачи передаёт флаг выполнения в письмо."""
        # given
        assignee = _user(2)
        task = _task_obj(assignees=[assignee])
        subtask = _subtask(task, is_completed=True)
        notification_service = Mock()
        notification_service.create_notification = AsyncMock()
        mail_service = Mock()
        mail_service.send_subtask_updated_email = AsyncMock()
        service, _, _, _, user_repo, _ = _make_service(notification_service, mail_service)
        user_repo.get_by_id = AsyncMock(return_value=_actor())

        # when
        await service._notify_subtask_toggled(subtask, toggled_by_id=CREATOR_ID)

        # then
        call = notification_service.create_notification.await_args_list[0]
        assert call.kwargs["type"] == NotificationType.subtask_updated
        email_call = mail_service.send_subtask_updated_email.await_args_list[0]
        assert email_call.kwargs["completed"] is True
