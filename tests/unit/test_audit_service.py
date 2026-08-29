from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from src.model.audit import AuditLog
from src.repository.audit_repository import AuditRepository
from src.services.audit_service import AuditService

TOTAL_WITHIN_WINDOW = 4
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
) -> AuditLog:
    return AuditLog(
        id=log_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        new_values=new_values,
        old_values=old_values,
        performed_by=1,
        performed_at=performed_at,
    )


def _setup_mock_repo(logs: list[AuditLog]) -> Mock:
    mock_repo = Mock(spec=AuditRepository)
    mock_repo.get_logs_by_user_id = AsyncMock(return_value=logs)
    mock_repo.get_project_names = AsyncMock(return_value={})
    mock_repo.get_resume_names = AsyncMock(return_value={})
    return mock_repo


class TestAuditService:
    """Тесты агрегации активности пользователя"""

    @pytest.mark.asyncio
    async def test_should_aggregate_activity_by_day_within_year_window(self):
        # given
        now = datetime.now(UTC)
        day1 = now - timedelta(days=1)
        day2 = now - timedelta(days=2)
        too_old = now - timedelta(days=400)

        logs = [
            _make_log("project", "INSERT", 1, day1, new_values={"name": "Expedition"}, log_id=1),
            _make_log("project", "UPDATE", 1, day1, new_values={"name": "Expedition"}, log_id=2),
            _make_log("resume", "INSERT", 5, day2, new_values={"header": "Researcher"}, log_id=3),
            _make_log("user", "UPDATE", 99, day1, log_id=4),
            _make_log("project", "INSERT", 2, too_old, new_values={"name": "Old project"}, log_id=5),
        ]
        mock_repo = _setup_mock_repo(logs)
        mock_repo.get_project_names = AsyncMock(return_value={1: "Expedition"})
        mock_repo.get_resume_names = AsyncMock(return_value={5: "Researcher"})
        service = AuditService(mock_repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.total == TOTAL_WITHIN_WINDOW
        counts = {day.date: day.count for day in result.summary}
        assert counts[day1.date()] == COUNT_DAY1
        assert counts[day2.date()] == COUNT_DAY2
        assert too_old.date() not in counts

        mock_repo.get_project_names.assert_awaited_once_with({1})
        mock_repo.get_resume_names.assert_awaited_once_with({5})

    @pytest.mark.asyncio
    async def test_should_describe_items_with_entity_names(self):
        # given
        now = datetime.now(UTC)
        logs = [
            _make_log("project", "INSERT", 1, now, new_values={"name": "Expedition"}, log_id=1),
            _make_log("resume", "UPDATE", 5, now, new_values={"header": "Researcher"}, log_id=2),
            _make_log("user", "UPDATE", 99, now, log_id=3),
        ]
        mock_repo = _setup_mock_repo(logs)
        mock_repo.get_project_names = AsyncMock(return_value={1: "Expedition"})
        mock_repo.get_resume_names = AsyncMock(return_value={5: "Researcher"})
        service = AuditService(mock_repo)

        # when
        result = await service.get_activity(1)

        # then
        descriptions = [item.description for item in result.items]
        assert descriptions == [
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
                "response", "INSERT", 10, now,
                new_values={"project_id": 7, "type": "response", "status": "pending"}, log_id=1,
            ),
            _make_log(
                "response", "UPDATE", 11, now,
                new_values={"project_id": 7, "type": "invitation", "status": "accepted"}, log_id=2,
            ),
            _make_log(
                "response", "UPDATE", 12, now,
                new_values={"project_id": 7, "type": "response", "status": "withdrawn"}, log_id=3,
            ),
        ]
        mock_repo = _setup_mock_repo(logs)
        mock_repo.get_project_names = AsyncMock(return_value={7: "Cosmos"})
        service = AuditService(mock_repo)

        # when
        result = await service.get_activity(1)

        # then
        descriptions = [item.description for item in result.items]
        assert descriptions == [
            "Откликнулся на проект «Cosmos»",
            "Принял приглашение в проект «Cosmos»",
            "Отозвал отклик в проект «Cosmos»",
        ]

    @pytest.mark.asyncio
    async def test_should_return_empty_activity_when_no_logs(self):
        # given
        mock_repo = _setup_mock_repo([])
        service = AuditService(mock_repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.total == 0
        assert result.summary == []
        assert result.items == []

    @pytest.mark.asyncio
    async def test_should_accept_json_string_values(self):
        # given
        now = datetime.now(UTC)
        logs = [
            _make_log(
                "response", "INSERT", 10, now,
                new_values=json.dumps({"project_id": 7, "type": "response", "status": "pending"}), log_id=1,
            ),
        ]
        mock_repo = _setup_mock_repo(logs)
        mock_repo.get_project_names = AsyncMock(return_value={7: "Cosmos"})
        service = AuditService(mock_repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == "Откликнулся на проект «Cosmos»"

    @pytest.mark.asyncio
    async def test_should_show_field_diff_for_project_update(self):
        # given
        now = datetime.now(UTC)
        old_values = {"name": "ваывавыа", "description": "старое описание"}
        new_values = {"name": "ваывавыа2", "description": "новое описание"}
        logs = [
            _make_log(
                "project", "UPDATE", 1, now,
                new_values=new_values, old_values=old_values, log_id=1,
            ),
        ]
        mock_repo = _setup_mock_repo(logs)
        mock_repo.get_project_names = AsyncMock(return_value={1: "ваывавыа2"})
        service = AuditService(mock_repo)

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
        now = datetime.now(UTC)
        old_values = {"name": "Проект", "theme": None}
        new_values = {"name": "Проект", "theme": "Исследование космоса"}
        logs = [
            _make_log("project", "UPDATE", 1, now, new_values=new_values, old_values=old_values, log_id=1),
        ]
        mock_repo = _setup_mock_repo(logs)
        mock_repo.get_project_names = AsyncMock(return_value={1: "Проект"})
        service = AuditService(mock_repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == 'Обновил проект «Проект»: Тема: — → «Исследование космоса»'

    @pytest.mark.asyncio
    async def test_should_limit_diff_to_three_fields_and_skip_updates_at(self):
        # given
        now = datetime.now(UTC)
        old_values = {
            "name": "A", "theme": None, "description": "old", "progress": 10,
            "updated_at": "2026-08-01T10:00:00+00:00",
        }
        new_values = {
            "name": "B", "theme": "Тема", "description": "new", "progress": 50,
            "updated_at": "2026-08-02T10:00:00+00:00",
        }
        logs = [
            _make_log("project", "UPDATE", 1, now, new_values=new_values, old_values=old_values, log_id=1),
        ]
        mock_repo = _setup_mock_repo(logs)
        mock_repo.get_project_names = AsyncMock(return_value={1: "B"})
        service = AuditService(mock_repo)

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
        now = datetime.now(UTC)
        old_values = {"project_id": 7, "type": "invitation", "status": "pending"}
        new_values = {"project_id": 7, "type": "invitation", "status": "accepted"}
        logs = [
            _make_log("response", "UPDATE", 11, now, new_values=new_values, old_values=old_values, log_id=1),
        ]
        mock_repo = _setup_mock_repo(logs)
        mock_repo.get_project_names = AsyncMock(return_value={7: "Cosmos"})
        service = AuditService(mock_repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == (
            "Принял приглашение в проект «Cosmos»: Статус: «pending» → «accepted»"
        )

    @pytest.mark.asyncio
    async def test_should_show_profile_update_diff(self):
        # given
        now = datetime.now(UTC)
        old_values = {"first_name": "Иван", "phone": "89120000000", "updated_at": "2026-08-01T10:00:00+00:00"}
        new_values = {"first_name": "Иван", "phone": "89999999999", "updated_at": "2026-08-02T10:00:00+00:00"}
        logs = [
            _make_log("user", "UPDATE", 1, now, new_values=new_values, old_values=old_values, log_id=1),
        ]
        mock_repo = _setup_mock_repo(logs)
        service = AuditService(mock_repo)

        # when
        result = await service.get_activity(1)

        # then
        assert result.items[0].description == "Обновил профиль: Телефон: «89120000000» → «89999999999»"
