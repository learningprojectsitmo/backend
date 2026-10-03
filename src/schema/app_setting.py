from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

# Публичный ответ намеренно не типизирован по полям: набор публичных ключей
# задаёт реестр (app_settings_registry.APP_SETTINGS), а не схема. Иначе каждый
# новый публичный ключ пришлось бы дублировать здесь — ровно та миграция,
# ради которой registry и введён.
#
# Фактический состав ключей: см. `public_keys` в AppSettingService.


class AppSettingPatch(BaseModel):
    """Частичное обновление глобальных настроек.

    Ключи и их типы проверяются сервисом по реестру; здесь только отсекаем
    не-объекты, чтобы FastAPI отдал 422 на мусорный body до бизнес-логики.
    """

    model_config = ConfigDict(extra="allow")


class AppSettingItem(BaseModel):
    """Одна настройка реестра с её текущим значением."""

    key: str
    value: Any
    kind: str
    title: str
    description: str
    updated_at: datetime | None = None
    updated_by_id: int | None = None


class AppSettingsAdminResponse(BaseModel):
    """Полный список глобальных настроек для админ-панели."""

    items: list[AppSettingItem]
