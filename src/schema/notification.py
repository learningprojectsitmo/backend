from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificationType(StrEnum):
    """Типы уведомлений"""

    PROJECT_INVITATION = "project_invitation"
    PROJECT_REMOVAL = "project_removal"
    JOIN_REQUEST = "join_request"
    JOIN_REQUEST_APPROVED = "join_request_approved"
    JOIN_REQUEST_REJECTED = "join_request_rejected"
    PROJECT_ANNOUNCEMENT = "project_announcement"
    SYSTEM_ALERT = "system_alert"


class NotificationSendToUserRequest(BaseModel):
    """Запрос на отправку уведомления пользователю"""

    user_id: int | None = None
    project_id: int | None = None
    template_key: NotificationType
    payload: dict[str, Any] = Field(default_factory=dict)


class NotificationSendToProjectRequest(BaseModel):
    """Запрос на отправку уведомления участникам проекта"""

    project_id: int
    template_key: NotificationType
    payload: dict[str, Any] = Field(default_factory=dict)
    include_author: bool = True


class NotificationTemplate(BaseModel):
    """Описание обязательных полей шаблона"""

    required: list[str]


class NotificationSettingsUpdate(BaseModel):
    """Обновление настроек уведомлений"""

    email_enabled: bool | None = None
    telegram_enabled: bool | None = None
    in_app_enabled: bool | None = None

    project_invitation_enabled: bool | None = None
    join_request_enabled: bool | None = None
    join_response_enabled: bool | None = None
    project_announcement_enabled: bool | None = None
    system_alert_enabled: bool | None = None


class NotificationSettingsResponse(BaseModel):
    """Ответ с настройками уведомлений"""

    user_id: int
    email_enabled: bool
    telegram_enabled: bool
    in_app_enabled: bool

    project_invitation_enabled: bool
    join_request_enabled: bool
    join_response_enabled: bool
    project_announcement_enabled: bool
    system_alert_enabled: bool

    model_config = ConfigDict(from_attributes=True)


class NotificationResponse(BaseModel):
    """Ответ с данными уведомления"""

    id: str
    recipient_id: int
    sender_id: int | None = None
    project_id: int | None = None
    type: NotificationType
    status: str
    title: str
    body: str
    channels: list[str]
    created_at: datetime
    sent_at: datetime | None = None
    read_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    """Ответ со списком уведомлений и пагинацией"""

    items: list[NotificationResponse]
    total: int
    page: int
    limit: int
    total_pages: int
