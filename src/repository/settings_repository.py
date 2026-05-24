from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.settings import SpaceSettings
from src.repository.base_repository import BaseRepository
from src.schema.settings import SpaceSettingsCreate, SpaceSettingsUpdate


class SpaceSettingsRepository(BaseRepository[SpaceSettings, SpaceSettingsCreate, SpaceSettingsUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = SpaceSettings

    async def get_by_space_id(self, space_id: int) -> SpaceSettings | None:
        """Получить настройки по ID пространства"""
        result = await self.uow.session.execute(select(SpaceSettings).where(SpaceSettings.space_id == space_id))
        return result.scalar_one_or_none()
