from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """Базовая схема audit log"""

    entity_type: str
    entity_id: int
    action: str
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    performed_by: int | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    performed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityDay(BaseModel):
    """Количество действий за день (для heatmap)"""

    date: date
    count: int


class ActivityItem(BaseModel):
    """Отдельное действие пользователя (для ленты)"""

    id: int
    kind: str  # например "project:INSERT", "response:UPDATE"
    description: str
    performed_at: datetime


class ActivityResponse(BaseModel):
    """Активность пользователя: агрегат по дням + лента действий"""

    total: int
    summary: list[ActivityDay]
    items: list[ActivityItem]
