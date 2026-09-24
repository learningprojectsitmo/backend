from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.model.settings import SpaceSettings
from src.repository.project_repository import ProjectRepository
from src.repository.settings_repository import SpaceSettingsRepository
from src.schema.settings import SpaceSettingsCreate, SpaceSettingsUpdate
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


class TestSpaceSettingsRequireProjectType:
    def test_create_schema_defaults_to_true(self):
        """Настройка «требовать тип проекта» включена по умолчанию при создании"""
        assert SpaceSettingsCreate(space_id=10, settings_type_id=1).require_project_type_on_create is True

    @pytest.mark.asyncio
    async def test_create_defaults_enables_require_project_type(self):
        """create_defaults создаёт настройки с включённым требованием типа проекта"""
        # given
        settings_repo = Mock(spec=SpaceSettingsRepository)
        created = SpaceSettings(id=3, space_id=10, settings_type_id=1, require_project_type_on_create=True)
        settings_repo.create.return_value = created

        service = SpaceSettingsService(settings_repo)

        # when
        result = await service.create_defaults(10)

        # then
        assert result == created
        settings_repo.create.assert_awaited_once()
        create_data = settings_repo.create.await_args.args[0]
        assert create_data.require_project_type_on_create is True

    @pytest.mark.asyncio
    async def test_update_preserves_require_project_type_when_unset(self):
        """Обновление без поля не трогает требование типа проекта"""
        # given
        settings_repo = Mock(spec=SpaceSettingsRepository)
        existing = SpaceSettings(
            id=1,
            space_id=10,
            settings_type_id=1,
            visibility="public",
            join_policy="open",
            require_project_type_on_create=True,
        )
        settings_repo.get_by_space_id.return_value = existing
        settings_repo.update.return_value = existing

        service = SpaceSettingsService(settings_repo)

        update_data = SpaceSettingsUpdate(default_project_deadline=DEADLINE)

        # when
        result = await service.create_or_update(10, update_data)

        # then
        assert result == existing
        settings_repo.update.assert_awaited_once_with(1, update_data)
