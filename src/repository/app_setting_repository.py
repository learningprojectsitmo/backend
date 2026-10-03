from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.app_setting import AppSetting
from src.repository.base_repository import BaseRepository
from src.schema.app_setting import AppSettingPatch


class AppSettingRepository(BaseRepository[AppSetting, AppSettingPatch, AppSettingPatch]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = AppSetting

    async def get_by_key(self, key: str) -> AppSetting | None:
        """Получить переопределение настройки по ключу"""
        result = await self.uow.session.execute(select(AppSetting).where(AppSetting.key == key))
        return result.scalar_one_or_none()

    async def get_by_keys(self, keys: Sequence[str]) -> list[AppSetting]:
        """Получить переопределения сразу по набору ключей (один SELECT на чтение)"""
        if not keys:
            return []
        result = await self.uow.session.execute(select(AppSetting).where(AppSetting.key.in_(list(keys))))
        return list(result.scalars().all())
