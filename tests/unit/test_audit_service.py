from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from src.model.audit import AuditLog
from src.repository.audit_repository import AuditRepository
from src.services.audit_service import ACTIVITY_DAYS_WINDOW, AuditService

COUNT_DAY1 = 3
COUNT_DAY2 = 1


def _make_log(
    entity_type: str,
    action: str,
    entity_id: int,
    performed_at: datetime,
    new_values: dict | None = None,
    old_values: dict | None = None,
    log_id: int = 1,
    performed_by: int | None = 1,
    project_id: int | None = None,
) -> AuditLog:
    return AuditLog(
        id=log_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        new_values=new_values,
        old_values=old_values,
        performed_by=performed_by,
        performed_at=performed_at,
        project_id=project_id,
    )


def _setup_mock_repo(
    logs: list[AuditLog] | None = None,
    *,
    registered_at: date | None = date(2026, 9, 1),
    project_created_at: date | None = date(2026, 9, 1),
    project_first_activity_at: date | None = None,
    project_total: int | None = None,
    projects: dict[int, str] | None = None,
    resumes: dict[int, str] | None = None,
    tasks: dict[int, str] | None = None,
    columns: dict[int, str] | None = None,
    stages: dict[int, str] | None = None,
    users: dict[int, str] | None = None,
) -> Mock:
    logs = logs if logs is not None else []
    repo = Mock(spec=AuditRepository)
    repo.get_logs_by_user_id = AsyncMock(return_value=logs)
    repo.get_user_registered_at = AsyncMock(return_value=registered_at)
    repo.get_logs_by_project_id = AsyncMock(
        return_value=(logs, project_total if project_total is not None else len(logs))
    )
    repo.get_performed_at_by_project_id = AsyncMock(return_value=[log.performed_at for log in logs])
    repo.get_project_created_at = AsyncMock(return_value=project_created_at)
    # По умолчанию активности нет — окно откатывается к дате создания проекта.
    repo.get_first_activity_at_by_project_id = AsyncMock(return_value=project_first_activity_at)
    repo.create_log = AsyncMock()
    repo.get_project_names = AsyncMock(return_value=projects or {})
    repo.get_resume_names = AsyncMock(return_value=resumes or {})
    repo.get_task_titles = AsyncMock(return_value=tasks or {})
    repo.get_column_names = AsyncMock(return_value=columns or {})
    repo.get_stage_names = AsyncMock(return_value=stages or {})
    repo.get_actor_names = AsyncMock(return_value=users or {})
    return repo


class TestProjectActivityWindow:
    """Окно активности проекта начинается с первого действия в проекте"""

    @pytest.mark.asyncio
    async def test_should_start_window_at_first_activity_not_creation(self):
        # given
        # Проект создали 1 сентября, работа началась только 10-го.
        repo = _setup_mock_repo(
            [],
            project_created_at=date(2026, 9, 1),
            project_first_activity_at=date(2026, 9, 10),
        )
        service = AuditService(repo)

        # when
        result = await service.get_project_activity(7)

        # then
        assert result.since == date(2026, 9, 10)
        # Дата создания не опрашивается, раз активность уже есть.
        repo.get_project_created_at.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_fall_back_to_creation_date_without_activity(self):
        # given
        repo = _setup_mock_repo([], project_created_at=date(2026, 9, 1), project_first_activity_at=None)
        service = AuditService(repo)

        # when
        result = await service.get_project_activity(7)

        # then
        assert result.since == date(2026, 9, 1)

    @pytest.mark.asyncio
    async def test_should_fall_back_to_today_without_activity_and_missing_project(self):
        # given
        repo = _setup_mock_repo([], project_created_at=None, project_first_activity_at=None)
        service = AuditService(repo)

        # when
        result = await service.get_project_activity(404)

        # then
        assert result.since == datetime.now(UTC).date()

    @pytest.mark.asyncio
    async def test_should_keep_all_activity_in_summary_when_since_is_first_activity(self):
        # given
        # since — первая активность, поэтому фильтр по нему не должен
        # отсечь ни один лог, даже если проект создали намного раньше.
        logs = [
            _make_log("project", "INSERT", 1, datetime(2026, 9, 20, tzinfo=UTC), new_values={"name": "X"}, log_id=1),
            _make_log("project", "UPDATE", 1, datetime(2026, 9, 25, tzinfo=UTC), new_values={"name": "X"}, log_id=2),
        ]
        repo = _setup_mock_repo(
            logs,
            project_created_at=date(2026, 1, 1),
            project_first_activity_at=date(2026, 9, 20),
        )
        service = AuditService(repo)

        # when
        result = await service.get_project_activity(7)

        # then
        assert len(result.summary) == 2


class TestActivityWindow:
    """Окно активности начинается с даты регистрации пользователя"""

    @pytest.mark.asyncio
    async def test_should_start_window_at_registration_date(self):
        # given
        registered_at = date(2026, 9, 1)
        repo = _setup_mock_repo([], registered_at=registered_at)
        service = AuditService(repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.since == registered_at
        repo.get_logs_by_user_id.assert_awaited_once_with(1, datetime(2026, 9, 1, 0, 0, tzinfo=UTC))

    @pytest.mark.asyncio
    async def test_should_fall_back_to_year_window_when_user_row_missing(self):
        # given
        repo = _setup_mock_repo([], registered_at=None)
        service = AuditService(repo)

        # when
        result = await service.get_activity(1)

        # then
        expected = datetime.now(UTC).date() - timedelta(days=ACTIVITY_DAYS_WINDOW)
        assert result.since == expected

    @pytest.mark.asyncio
    async def test_should_aggregate_activity_by_day(self):
        # given
        now = datetime.now(UTC)
        day1 = now - timedelta(days=1)
        day2 = now - timedelta(days=2)
        logs = [
            _make_log("project", "INSERT", 1, day1, new_values={"name": "Expedition"}, log_id=1),
            _make_log("project", "UPDATE", 1, day1, new_values={"name": "Expedition"}, log_id=2),
            _make_log("resume", "INSERT", 5, day2, new_values={"header": "Researcher"}, log_id=3),
            _make_log("user", "UPDATE", 99, day1, log_id=4),
        ]
        repo = _setup_mock_repo(logs, projects={1: "Expedition"}, resumes={5: "Researcher"})
        service = AuditService(repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.total == 4
        counts = {day.date: day.count for day in result.summary}
        assert counts[day1.date()] == COUNT_DAY1
        assert counts[day2.date()] == COUNT_DAY2

        repo.get_project_names.assert_awaited_once_with({1})
        repo.get_resume_names.assert_awaited_once_with({5})

    @pytest.mark.asyncio
    async def test_should_paginate_feed_and_keep_full_summary(self):
        # given
        now = datetime.now(UTC)
        logs = [_make_log("project", "INSERT", i, now, new_values={"name": f"P{i}"}, log_id=i) for i in range(1, 6)]
        repo = _setup_mock_repo(logs, projects={i: f"P{i}" for i in range(1, 6)})
        service = AuditService(repo)

        # when
        result = await service.get_activity(1, page=2, limit=2)

        # then
        assert result.total == 5
        assert result.page == 2
        assert result.total_pages == 3
        assert len(result.items) == 2
        # агрегат по дням не зависит от страницы ленты
        assert sum(day.count for day in result.summary) == 5

    @pytest.mark.asyncio
    async def test_should_attach_actor_to_items(self):
        # given
        repo = _setup_mock_repo(
            [_make_log("project", "INSERT", 1, datetime.now(UTC), new_values={"name": "Expedition"})],
            users={1: "Иванов Иван"},
        )
        service = AuditService(repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].actor is not None
        assert result.items[0].actor.id == 1
        assert result.items[0].actor.name == "Иванов Иван"

    @pytest.mark.asyncio
    async def test_should_leave_actor_empty_for_system_actions(self):
        # given
        repo = _setup_mock_repo(
            [_make_log("project", "INSERT", 1, datetime.now(UTC), new_values={"name": "Expedition"}, performed_by=None)]
        )
        service = AuditService(repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].actor is None


class TestActivityDayFilter:
    """Клик по дню в графике сужает ленту, но не сам график"""

    @pytest.mark.asyncio
    async def test_should_pass_selected_day_to_repository(self):
        # given
        repo = _setup_mock_repo([])
        service = AuditService(repo)

        # when
        await service.get_activity(1, day=date(2026, 9, 26))

        # then
        repo.get_logs_by_user_id.assert_any_await(1, datetime(2026, 9, 1, 0, 0, tzinfo=UTC), day=date(2026, 9, 26))

    @pytest.mark.asyncio
    async def test_should_not_filter_when_day_is_absent(self):
        # given
        repo = _setup_mock_repo([])
        service = AuditService(repo)

        # when
        await service.get_activity(1)

        # then
        repo.get_logs_by_user_id.assert_awaited_once_with(1, datetime(2026, 9, 1, 0, 0, tzinfo=UTC))

    @pytest.mark.asyncio
    async def test_should_keep_summary_full_when_day_selected(self):
        # given
        # summary считается по полной выборке: иначе график схлопнется в
        # одну колонку и перестанет быть годным при выборе дня.
        repo = _setup_mock_repo(
            [
                _make_log(
                    "project", "INSERT", 1, datetime(2026, 9, 24, 10, tzinfo=UTC), new_values={"name": "A"}, log_id=1
                ),
                _make_log(
                    "project", "INSERT", 1, datetime(2026, 9, 25, 10, tzinfo=UTC), new_values={"name": "B"}, log_id=2
                ),
            ]
        )
        service = AuditService(repo)

        # when
        result = await service.get_activity(1, day=date(2026, 9, 25))

        # then
        # Мок отдаёт одни и те же логи для обоих вызовов, поэтому проверяем
        # именно число обращений: summary-выборка и выборка ленты.
        assert repo.get_logs_by_user_id.await_count == 2
        assert len(result.summary) == 2

    @pytest.mark.asyncio
    async def test_should_pass_day_to_project_query(self):
        # given
        repo = _setup_mock_repo([])
        service = AuditService(repo)

        # when
        await service.get_project_activity(7, day=date(2026, 9, 26))

        # then
        repo.get_logs_by_project_id.assert_awaited_once_with(7, 0, 50, day=date(2026, 9, 26))


class TestProjectActivity:
    """Лента активности проекта"""

    @pytest.mark.asyncio
    async def test_should_return_page_of_project_logs_with_actor(self):
        # given
        now = datetime.now(UTC)
        logs = [
            _make_log(
                "task",
                "INSERT",
                3,
                now,
                new_values={"title": "Собрать прототип", "project_id": 7},
                log_id=1,
                performed_by=4,
                project_id=7,
            ),
        ]
        repo = _setup_mock_repo(
            logs,
            project_created_at=date(2026, 9, 1),
            project_total=1,
            tasks={3: "Собрать прототип"},
            users={4: "Петрова Ана"},
        )
        service = AuditService(repo)

        # when
        result = await service.get_project_activity(7)

        # then
        assert result.total == 1
        assert result.since == date(2026, 9, 1)
        assert result.items[0].description == "Создал задачу «Собрать прототип»"
        assert result.items[0].actor is not None
        assert result.items[0].actor.name == "Петрова Ана"
        repo.get_logs_by_project_id.assert_awaited_once_with(7, 0, 50, day=None)

    @pytest.mark.asyncio
    async def test_should_offset_page_in_project_query(self):
        # given
        repo = _setup_mock_repo([], project_total=0)
        service = AuditService(repo)

        # when
        await service.get_project_activity(7, page=3, limit=10)

        # then
        repo.get_logs_by_project_id.assert_awaited_once_with(7, 20, 10, day=None)

    @pytest.mark.asyncio
    async def test_should_start_project_window_at_creation_date(self):
        # given
        created_at = date(2026, 5, 4)
        repo = _setup_mock_repo([], project_created_at=created_at)
        service = AuditService(repo)

        # when
        result = await service.get_project_activity(7)

        # then
        assert result.since == created_at
        repo.get_performed_at_by_project_id.assert_awaited_once_with(7, datetime(2026, 5, 4, 0, 0, tzinfo=UTC))


class TestProjectDescriptions:
    """Формулировки действий внутри проекта"""

    @staticmethod
    async def _describe(log: AuditLog, **names: object) -> str:
        repo = _setup_mock_repo([log], **names)  # type: ignore[arg-type]
        service = AuditService(repo)
        result = await service.get_project_activity(log.project_id or 7)
        return result.items[0].description

    @pytest.mark.asyncio
    async def test_should_describe_task_move_with_column_name(self):
        # given
        log = _make_log(
            "task",
            "UPDATE",
            3,
            datetime.now(UTC),
            old_values={"title": "Дизайн", "column_id": 1, "position": 0},
            new_values={"title": "Дизайн", "column_id": 2, "position": 1},
            project_id=7,
        )

        # then
        assert await self._describe(log, columns={2: "В работе"}) == "Переместил задачу «Дизайн» в «В работе»"

    @pytest.mark.asyncio
    async def test_should_describe_task_update_with_diff(self):
        # given
        log = _make_log(
            "task",
            "UPDATE",
            3,
            datetime.now(UTC),
            old_values={"title": "Дизайн", "priority": "low"},
            new_values={"title": "Дизайн", "priority": "high"},
            project_id=7,
        )

        # then
        assert await self._describe(log) == "Обновил задачу «Дизайн»: Приоритет: «low» → «high»"

    @pytest.mark.asyncio
    async def test_should_ignore_position_only_change_in_task_diff(self):
        # given
        log = _make_log(
            "task",
            "UPDATE",
            3,
            datetime.now(UTC),
            old_values={"title": "Дизайн", "position": 0},
            new_values={"title": "Дизайн", "position": 5},
            project_id=7,
        )

        # then
        assert await self._describe(log) == "Обновил задачу «Дизайн»"

    @pytest.mark.asyncio
    async def test_should_describe_subtask_completion(self):
        # given
        log = _make_log(
            "subtask",
            "UPDATE",
            9,
            datetime.now(UTC),
            old_values={"title": "Нарисовать макет", "task_id": 3, "is_completed": False},
            new_values={"title": "Нарисовать макет", "task_id": 3, "is_completed": True},
            project_id=7,
        )
        # then
        assert await self._describe(log, tasks={3: "Дизайн"}) == (
            "Отметил подзадачу «Нарисовать макет» к задаче «Дизайн» выполненной"
        )

    @pytest.mark.asyncio
    async def test_should_describe_subtask_unchecked(self):
        # given
        log = _make_log(
            "subtask",
            "UPDATE",
            9,
            datetime.now(UTC),
            old_values={"title": "Макет", "task_id": 3, "is_completed": True},
            new_values={"title": "Макет", "task_id": 3, "is_completed": False},
            project_id=7,
        )

        # then
        assert await self._describe(log) == "Снял отметку о выполнении с подзадачи «Макет»"

    @pytest.mark.asyncio
    async def test_should_describe_column_lifecycle(self):
        # given
        created = _make_log("column", "INSERT", 2, datetime.now(UTC), new_values={"name": "Ревью"}, project_id=7)
        deleted = _make_log("column", "DELETE", 2, datetime.now(UTC), old_values={"name": "Ревью"}, project_id=7)

        # then
        assert await self._describe(created) == "Создал колонку «Ревью»"
        assert await self._describe(deleted) == "Удалил колонку «Ревью»"

    @pytest.mark.asyncio
    async def test_should_describe_stage_transition_actions(self):
        # given
        advance = _make_log(
            "stage_transition",
            "INSERT",
            1,
            datetime.now(UTC),
            new_values={"action": "advance", "stage_id": 4},
            project_id=7,
        )
        reject = _make_log(
            "stage_transition",
            "INSERT",
            2,
            datetime.now(UTC),
            new_values={"action": "reject", "stage_id": 4, "comment": "Нужны схемы"},
            project_id=7,
        )
        # then
        assert await self._describe(advance, stages={4: "Разработка"}) == "Перешёл на этап «Разработка»"
        assert await self._describe(reject, stages={4: "Разработка"}) == "Отклонил этап «Разработка»: Нужны схемы"

    @pytest.mark.asyncio
    async def test_should_describe_specification_status_changes(self):
        # given
        submitted = _make_log(
            "specification",
            "UPDATE",
            1,
            datetime.now(UTC),
            old_values={"status": "draft"},
            new_values={"status": "submitted"},
            project_id=7,
        )
        rejected = _make_log(
            "specification",
            "UPDATE",
            1,
            datetime.now(UTC),
            old_values={"status": "submitted"},
            new_values={"status": "draft", "rejection_comment": "Дополните раздел 2"},
            project_id=7,
        )
        edited = _make_log(
            "specification",
            "UPDATE",
            1,
            datetime.now(UTC),
            old_values={"goal": "старая цель", "status": "draft"},
            new_values={"goal": "новая цель", "status": "draft"},
            project_id=7,
        )

        # then
        assert await self._describe(submitted) == "Отправил техническое задание на согласование"
        assert await self._describe(rejected) == "Вернул техническое задание в черновики: Дополните раздел 2"
        assert await self._describe(edited) == "Обновил техническое задание: Цель: «старая цель» → «новая цель»"

    @pytest.mark.asyncio
    async def test_should_describe_specification_comment(self):
        # given
        log = _make_log(
            "specification_comment",
            "INSERT",
            5,
            datetime.now(UTC),
            new_values={"text": "Нужно уточнить сроки"},
            project_id=7,
        )

        # then
        assert await self._describe(log) == "Оставил комментарий к техническому заданию: Нужно уточнить сроки"

    @pytest.mark.asyncio
    async def test_should_describe_assignee_changes(self):
        # given
        log = _make_log(
            "task_assignee",
            "UPDATE",
            3,
            datetime.now(UTC),
            new_values={"task_id": 3, "added": [4], "removed": [5, 6]},
            project_id=7,
        )
        # then
        assert await self._describe(
            log, tasks={3: "Дизайн"}, users={4: "Петрова Ана", 5: "Сидоров П", 6: "Иванов И"}
        ) == (
            "добавил исполнителя задачи «Дизайн»: Петрова Ана; снял исполнителей задачи «Дизайн»: Сидоров П, Иванов И"
        )

    @pytest.mark.asyncio
    async def test_should_describe_project_participation(self):
        # given
        joined = _make_log(
            "project_participation",
            "INSERT",
            1,
            datetime.now(UTC),
            new_values={"participant_id": 4},
            project_id=7,
        )
        left = _make_log(
            "project_participation",
            "DELETE",
            1,
            datetime.now(UTC),
            old_values={"participant_id": 4},
            project_id=7,
        )
        # then
        assert await self._describe(joined, users={4: "Петрова Ана"}) == "Добавил в проект Петрова Ана"
        assert await self._describe(left, users={4: "Петрова Ана"}) == "Исключил из проекта Петрова Ана"

    @pytest.mark.asyncio
    async def test_should_fall_back_to_generic_description_for_unknown_entity(self):
        # given
        log = _make_log("mystery", "INSERT", 1, datetime.now(UTC), project_id=7)

        # then
        assert await self._describe(log) == "Выполнил действие mystery:INSERT"


class TestLogTaskAssignees:
    """Ручная запись смены исполнителей"""

    @pytest.mark.asyncio
    async def test_should_skip_logging_when_nothing_changed(self):
        # given
        repo = _setup_mock_repo([])
        service = AuditService(repo)
        task = Mock(id=3, project_id=7)

        # when
        await service.log_task_assignees(task, added=[], removed=[])

        # then
        repo.create_log.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_write_added_and_removed_assignees(self):
        # given
        repo = _setup_mock_repo([])
        service = AuditService(repo)
        task = Mock(id=3, project_id=7)

        # when
        await service.log_task_assignees(task, added=[4], removed=[5])

        # then
        kwargs = repo.create_log.await_args.kwargs
        assert kwargs["entity_type"] == "task_assignee"
        assert kwargs["entity_id"] == 3
        assert kwargs["project_id"] == 7
        assert kwargs["new_values"] == {"task_id": 3, "added": [4], "removed": [5]}


class TestDescriptions:
    """Формулировки действий в ленте профиля"""

    @pytest.mark.asyncio
    async def test_should_describe_items_with_entity_names(self):
        # given
        now = datetime.now(UTC)
        logs = [
            _make_log("project", "INSERT", 1, now, new_values={"name": "Expedition"}, log_id=1),
            _make_log("resume", "UPDATE", 5, now, new_values={"header": "Researcher"}, log_id=2),
            _make_log("user", "UPDATE", 99, now, log_id=3),
        ]
        repo = _setup_mock_repo(logs, projects={1: "Expedition"}, resumes={5: "Researcher"})
        service = AuditService(repo)

        # when
        result = await service.get_activity(1)

        # then
        assert [item.description for item in result.items] == [
            "Создал проект «Expedition»",
            "Обновил резюме «Researcher»",
            "Обновил профиль",
        ]

    @pytest.mark.asyncio
    async def test_should_describe_response_actions(self):
        # given
        now = datetime.now(UTC)
        logs = [
            _make_log(
                "response",
                "INSERT",
                10,
                now,
                new_values={"project_id": 7, "type": "response", "status": "pending"},
                log_id=1,
            ),
            _make_log(
                "response",
                "UPDATE",
                11,
                now,
                new_values={"project_id": 7, "type": "invitation", "status": "accepted"},
                log_id=2,
            ),
            _make_log(
                "response",
                "UPDATE",
                12,
                now,
                new_values={"project_id": 7, "type": "response", "status": "withdrawn"},
                log_id=3,
            ),
        ]
        repo = _setup_mock_repo(logs, projects={7: "Cosmos"})
        service = AuditService(repo)

        # when
        result = await service.get_activity(1)

        # then
        assert [item.description for item in result.items] == [
            "Откликнулся на проект «Cosmos»",
            "Принял приглашение в проект «Cosmos»",
            "Отозвал отклик в проект «Cosmos»",
        ]

    @pytest.mark.asyncio
    async def test_should_return_empty_activity_when_no_logs(self):
        # given
        service = AuditService(_setup_mock_repo([]))

        # when
        result = await service.get_activity(1)

        # then
        assert result.total == 0
        assert result.total_pages == 0
        assert result.summary == []
        assert result.items == []

    @pytest.mark.asyncio
    async def test_should_accept_json_string_values(self):
        # given
        log = _make_log(
            "response",
            "INSERT",
            10,
            datetime.now(UTC),
            new_values=json.dumps({"project_id": 7, "type": "response", "status": "pending"}),
        )
        service = AuditService(_setup_mock_repo([log], projects={7: "Cosmos"}))

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == "Откликнулся на проект «Cosmos»"

    @pytest.mark.asyncio
    async def test_should_show_field_diff_for_project_update(self):
        # given
        log = _make_log(
            "project",
            "UPDATE",
            1,
            datetime.now(UTC),
            new_values={"name": "ваывавыа2", "description": "новое описание"},
            old_values={"name": "ваывавыа", "description": "старое описание"},
        )
        service = AuditService(_setup_mock_repo([log], projects={1: "ваывавыа2"}))

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == (
            "Обновил проект «ваывавыа2»: "
            "Название: «ваывавыа» → «ваывавыа2», Описание: «старое описание» → «новое описание»"
        )

    @pytest.mark.asyncio
    async def test_should_show_none_to_value_change(self):
        # given
        log = _make_log(
            "project",
            "UPDATE",
            1,
            datetime.now(UTC),
            new_values={"name": "Проект", "theme": "Исследование космоса"},
            old_values={"name": "Проект", "theme": None},
        )
        service = AuditService(_setup_mock_repo([log], projects={1: "Проект"}))

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == "Обновил проект «Проект»: Тема: — → «Исследование космоса»"

    @pytest.mark.asyncio
    async def test_should_limit_diff_to_three_fields_and_skip_updates_at(self):
        # given
        log = _make_log(
            "project",
            "UPDATE",
            1,
            datetime.now(UTC),
            new_values={
                "name": "B",
                "theme": "Тема",
                "description": "new",
                "progress": 50,
                "updated_at": "2026-08-02T10:00:00+00:00",
            },
            old_values={
                "name": "A",
                "theme": None,
                "description": "old",
                "progress": 10,
                "updated_at": "2026-08-01T10:00:00+00:00",
            },
        )
        service = AuditService(_setup_mock_repo([log], projects={1: "B"}))

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == (
            "Обновил проект «B»: Название: «A» → «B», Тема: — → «Тема», Описание: «old» → «new», и ещё 1"
        )
        assert "updated_at" not in result.items[0].description

    @pytest.mark.asyncio
    async def test_should_show_status_diff_for_response_update(self):
        # given
        log = _make_log(
            "response",
            "UPDATE",
            11,
            datetime.now(UTC),
            new_values={"project_id": 7, "type": "invitation", "status": "accepted"},
            old_values={"project_id": 7, "type": "invitation", "status": "pending"},
        )
        service = AuditService(_setup_mock_repo([log], projects={7: "Cosmos"}))

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == "Принял приглашение в проект «Cosmos»: Статус: «pending» → «accepted»"

    @pytest.mark.asyncio
    async def test_should_show_profile_update_diff(self):
        # given
        log = _make_log(
            "user",
            "UPDATE",
            1,
            datetime.now(UTC),
            new_values={"first_name": "Иван", "phone": "89999999999", "updated_at": "2026-08-02T10:00:00+00:00"},
            old_values={"first_name": "Иван", "phone": "89120000000", "updated_at": "2026-08-01T10:00:00+00:00"},
        )
        service = AuditService(_setup_mock_repo([log]))

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == "Обновил профиль: Телефон: «89120000000» → «89999999999»"


class TestRichTextRendering:
    """Описания и diff не должны протекать HTML-разметкой редактора в ленту"""

    @pytest.mark.asyncio
    async def test_should_strip_html_from_project_description_diff(self):
        # given
        log = _make_log(
            "project",
            "UPDATE",
            1,
            datetime.now(UTC),
            new_values={"name": "Проект", "description": "<p>Новая <b>цель</b></p>"},
            old_values={"name": "Проект", "description": "<p>Старая цель</p>"},
        )
        service = AuditService(_setup_mock_repo([log], projects={1: "Проект"}))

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == ("Обновил проект «Проект»: Описание: «Старая цель» → «Новая цель»")

    @pytest.mark.asyncio
    async def test_should_decode_html_entities_and_collapse_whitespace(self):
        # given
        log = _make_log(
            "project",
            "UPDATE",
            1,
            datetime.now(UTC),
            new_values={"name": "Проект", "description": "<p>a&nbsp;&amp;<br/>b</p>"},
            old_values={"name": "Проект", "description": "x"},
        )
        service = AuditService(_setup_mock_repo([log], projects={1: "Проект"}))

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == ("Обновил проект «Проект»: Описание: «x» → «a & b»")

    @pytest.mark.asyncio
    async def test_should_strip_html_from_specification_comment(self):
        # given
        log = _make_log(
            "specification_comment",
            "INSERT",
            5,
            datetime.now(UTC),
            new_values={"text": "<p>Нужно <i>уточнить</i> сроки</p>"},
            project_id=7,
        )
        repo = _setup_mock_repo([log])
        service = AuditService(repo)

        # when
        result = await service.get_project_activity(7)

        # then
        assert result.items[0].description == ("Оставил комментарий к техническому заданию: Нужно уточнить сроки")


class TestFieldLabels:
    """Поля аудита не должны светиться сырыми именами колонок"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("column", "expected"),
        [
            ("middle_name", "Отчество"),
            ("column_id", "Колонка"),
            ("wip_limit", "Лимит WIP"),
            ("goal", "Цель"),
            ("functional_requirements", "Функциональные требования"),
        ],
    )
    async def test_should_use_human_label(self, column: str, expected: str) -> None:
        # given
        log = _make_log(
            "project",
            "UPDATE",
            1,
            datetime.now(UTC),
            new_values={"name": "Проект", column: "новое"},
            old_values={"name": "Проект", column: "старое"},
        )
        service = AuditService(_setup_mock_repo([log], projects={1: "Проект"}))

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == (f"Обновил проект «Проект»: {expected}: «старое» → «новое»")


def test_start_of_day_is_midnight_utc():
    # given
    value = date(2026, 9, 1)

    # then
    assert datetime.combine(value, time.min, tzinfo=UTC) == datetime(2026, 9, 1, tzinfo=UTC)
