from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.model.settings import SpaceSettings
from src.repository.project_repository import ProjectRepository
from src.repository.settings_repository import SpaceSettingsRepository
from src.schema.settings import SpaceSettingsUpdate
from src.services.settings_service import SpaceSettingsService

DEADLINE = datetime(2026, 12, 31, tzinfo=UTC)


class TestSpaceSettingsServiceDeadline:
    @pytest.mark.asyncio
    async def test_should_apply_deadline_to_existing_projects_on_update(self):
        """Ретроактивно применяет дедлайн ко всем проектам пространства при обновлении"""
        # given
        settings_repo = Mock(spec=SpaceSettingsRepository)
        project_repo = Mock(spec=ProjectRepository)
        project_repo.update_deadline_by_workspace = AsyncMock()

        existing = SpaceSettings(id=1, space_id=10, settings_type_id=1, visibility="public", join_policy="open")
        settings_repo.get_by_space_id.return_value = existing
        updated = SpaceSettings(
            id=1,
            space_id=10,
            settings_type_id=1,
            visibility="public",
            join_policy="open",
            default_project_deadline=DEADLINE,
        )
        settings_repo.update.return_value = updated

        service = SpaceSettingsService(settings_repo, project_repository=project_repo)

        update_data = SpaceSettingsUpdate(default_project_deadline=DEADLINE)

        # when
        result = await service.create_or_update(10, update_data)

        # then
        assert result == updated
        settings_repo.update.assert_awaited_once_with(1, update_data)
        project_repo.update_deadline_by_workspace.assert_awaited_once_with(10, DEADLINE)

    @pytest.mark.asyncio
    async def test_should_not_touch_projects_when_deadline_not_in_payload(self):
        """Не обновляет проекты, если дедлайн не передан в настройках"""
        # given
        settings_repo = Mock(spec=SpaceSettingsRepository)
        project_repo = Mock(spec=ProjectRepository)
        project_repo.update_deadline_by_workspace = AsyncMock()

        existing = SpaceSettings(id=1, space_id=10, settings_type_id=1, visibility="public", join_policy="open")
        settings_repo.get_by_space_id.return_value = existing
        settings_repo.update.return_value = existing

        service = SpaceSettingsService(settings_repo, project_repository=project_repo)

        update_data = SpaceSettingsUpdate(visibility="private")

        # when
        await service.create_or_update(10, update_data)

        # then
        project_repo.update_deadline_by_workspace.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_create_settings_with_deadline_when_missing(self):
        """Создаёт настройки и применяет дедлайн к проектам при отсутствии настроек"""
        # given
        settings_repo = Mock(spec=SpaceSettingsRepository)
        project_repo = Mock(spec=ProjectRepository)
        project_repo.update_deadline_by_workspace = AsyncMock()

        settings_repo.get_by_space_id.return_value = None
        created = SpaceSettings(
            id=2,
            space_id=10,
            settings_type_id=1,
            visibility="public",
            join_policy="open",
            default_project_deadline=DEADLINE,
        )
        settings_repo.create.return_value = created

        service = SpaceSettingsService(settings_repo, project_repository=project_repo)

        update_data = SpaceSettingsUpdate(default_project_deadline=DEADLINE)

        # when
        result = await service.create_or_update(10, update_data)

        # then
        assert result == created
        settings_repo.create.assert_awaited_once()
        project_repo.update_deadline_by_workspace.assert_awaited_once_with(10, DEADLINE)
