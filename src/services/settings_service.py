from __future__ import annotations

from typing import TYPE_CHECKING

from src.model.settings import SpaceSettings
from src.schema.settings import SpaceSettingsCreate, SpaceSettingsUpdate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.project_repository import ProjectRepository
    from src.repository.settings_repository import SpaceSettingsRepository


class SpaceSettingsService(BaseService[SpaceSettings, SpaceSettingsCreate, SpaceSettingsUpdate]):
    def __init__(
        self,
        settings_repository: SpaceSettingsRepository,
        project_repository: ProjectRepository | None = None,
    ):
        super().__init__(settings_repository)
        self._settings_repository = settings_repository
        self._project_repository = project_repository

    async def get_by_space_id(self, space_id: int) -> SpaceSettings | None:
        """Получить настройки пространства"""
        return await self._settings_repository.get_by_space_id(space_id)

    async def create_or_update(self, space_id: int, settings_data: SpaceSettingsUpdate) -> SpaceSettings:
        """Создать или обновить настройки пространства"""
        existing = await self.get_by_space_id(space_id)
        if existing:
            settings = await self._settings_repository.update(existing.id, settings_data)
        else:
            create_data = SpaceSettingsCreate(
                space_id=space_id,
                settings_type_id=1,
                **settings_data.model_dump(exclude_unset=True),
            )
            settings = await self._settings_repository.create(create_data)

        # Ретроактивно применяем дедлайн ко всем проектам пространства
        data = settings_data.model_dump(exclude_unset=True)
        if "default_project_deadline" in data and self._project_repository is not None:
            await self._project_repository.update_deadline_by_workspace(space_id, settings.default_project_deadline)

        return settings

    async def create_defaults(self, space_id: int) -> SpaceSettings:
        """Создать настройки со значениями по умолчанию (пространство приватное)"""
        create_data = SpaceSettingsCreate(
            space_id=space_id,
            settings_type_id=1,
            visibility="private",
        )
        return await self._settings_repository.create(create_data)
