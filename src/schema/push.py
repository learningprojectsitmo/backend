from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.model.push import PushPlatform


class PushSubscriptionRequest(BaseModel):
    """Регистрация устройства.

    Токен присылает клиент при каждом запуске приложения и при каждом
    refresh от FCM. Повторная отправка — норма, а не ошибка: сервер
    переиспользует строку и возвращает токен в активные.
    """

    token: str = Field(
        min_length=8,
        max_length=512,
        description="FCM registration token",
    )
    platform: PushPlatform
    device_id: str | None = Field(
        default=None,
        max_length=128,
        description='Для диагностики: "iPhone 15 Pro", "SM-S918B"',
    )
    app_version: str | None = Field(default=None, max_length=32)


class PushSubscriptionResponse(BaseModel):
    id: int
    platform: PushPlatform
    device_id: str | None
    app_version: str | None
    is_active: bool
    last_seen_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PushUnregisterResponse(BaseModel):
    """Ответ на снятие подписки.

    `removed` = 0 — это не ошибка: клиент мог прислать проиграшный или уже
    погашенный токен (например, при выходе, когда устройства чистятся
    массово). Отвечать 404 значило бы заставить клиент разбирать ситуацию,
    которой он не может повлиять.
    """

    removed: int
