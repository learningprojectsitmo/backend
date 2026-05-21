from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SettingsTypeSchema(BaseModel):
    """Схема типа настроек"""

    id: int
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class SpaceSettingsCreate(BaseModel):
    """Схема для создания настроек пространства"""

    space_id: int
    settings_type_id: int = 1
    visibility: str = "public"
    join_policy: str = "open"
    default_role_id: int | None = None
    icon_url: str | None = None


class SpaceSettingsUpdate(BaseModel):
    """Схема для обновления настроек пространства"""

    visibility: str | None = None
    join_policy: str | None = None
    default_role_id: int | None = None
    icon_url: str | None = None


class SpaceSettingsFull(BaseModel):
    """Полная схема настроек пространства"""

    id: int
    space_id: int
    settings_type_id: int
    visibility: str
    join_policy: str
    default_role_id: int | None = None
    icon_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
