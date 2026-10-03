from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.app_settings_registry import (
    APP_SETTINGS,
    APP_SETTINGS_BY_KEY,
    PUBLIC_SETTING_KEYS,
    default_values,
    validate_patch,
)
from src.model.app_setting import AppSetting
from src.schema.app_setting import AppSettingItem, AppSettingPatch
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.app_setting_repository import AppSettingRepository


class AppSettingService(BaseService[AppSetting, AppSettingPatch, AppSettingPatch]):
    """Глобальные настройки инстанса.

    Таблица хранит только переопределения администратора: всё, чего в ней нет,
    берётся из реестра. Поэтому «выключено по умолчанию» работает само — не
    нужно ни сидировать строки, ни выполнять миграцию данных при добавлении
    настройки в реестр.
    """

    def __init__(self, app_setting_repository: AppSettingRepository) -> None:
        super().__init__(app_setting_repository)
        self._app_setting_repository = app_setting_repository

    async def get_values(self) -> dict[str, Any]:
        """Все настройки: дефолты реестра, поверх них — строки из БД."""
        values = default_values()
        for row in await self._app_setting_repository.get_by_keys(list(values)):
            # Ключ, которого больше нет в реестре (например, настройку удалили
            # из кода, а строка осталась), игнорируем: отдавать его клиенту
            # нельзя, но и мешать он не должен.
            if row.key in values:
                values[row.key] = row.value
        return values

    async def get_public_values(self) -> dict[str, Any]:
        """Только публичные настройки — для анонимного эндпоинта."""
        values = await self.get_values()
        return {key: values[key] for key in PUBLIC_SETTING_KEYS}

    async def list_items(self) -> list[AppSettingItem]:
        """Реестр целиком с текущими значениями — форма ответа админ-панели."""
        values = await self.get_values()
        rows = {row.key: row for row in await self._app_setting_repository.get_by_keys(list(APP_SETTINGS_BY_KEY))}

        items: list[AppSettingItem] = []
        for definition in APP_SETTINGS:
            row = rows.get(definition.key)
            items.append(
                AppSettingItem(
                    key=definition.key,
                    value=values[definition.key],
                    kind=definition.kind,
                    title=definition.title,
                    description=definition.description,
                    # Строки нет — значит настройку ещё не переключали и
                    # действует дефолт реестра.
                    updated_at=row.updated_at if row else None,
                    updated_by_id=row.updated_by_id if row else None,
                )
            )
        return items

    async def apply_patch(self, patch: dict[str, Any], user_id: int | None) -> list[AppSettingItem]:
        """Частично обновить настройки и вернуть актуальный список.

        Raises:
            UnknownSettingError, InvalidSettingValueError: из реестра.
        """
        validated = validate_patch(patch)
        if not validated:
            return await self.list_items()

        existing = {row.key: row for row in await self._app_setting_repository.get_by_keys(list(validated))}

        for key, value in validated.items():
            row = existing.get(key)
            if row is not None:
                row.value = value
                row.updated_by_id = user_id
            else:
                # Первый переключатель создаёт строку: до этого момента
                # настройка жила только дефолтом из реестра.
                await self._app_setting_repository.create({"key": key, "value": value, "updated_by_id": user_id})

        return await self.list_items()
