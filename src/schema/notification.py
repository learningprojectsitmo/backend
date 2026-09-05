from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.model.notification import NotificationType


class NotificationResponse(BaseModel):
    id: int
    type: NotificationType
    data: dict
    read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    limit: int
    total_pages: int
    unread_count: int
