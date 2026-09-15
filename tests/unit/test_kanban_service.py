from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.exceptions import PermissionError, ValidationError
from src.model.kanban_models import Task
from src.schema.kanban import TaskCreate, TaskUpdate
from src.services.kanban_service import KanbanService

CREATOR_ID = 5
TEAM_ASSIGNEE_ID = 5
OUTSIDER_ID = 10


def _make_service():
    column_repo = Mock()
    task_repo = Mock()
    subtask_repo = Mock()
    user_repo = Mock()
    project_repo = Mock()
    service = KanbanService(column_repo, task_repo, subtask_repo, user_repo, project_repo)
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
        old_task = Mock(id=1, column_id=1, title="Task")
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
