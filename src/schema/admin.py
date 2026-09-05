from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AdminSessionItem(BaseModel):
    """Сессия в списке сессий админ-панели"""

    id: str
    user_id: int
    user_name: str = ""
    user_email: str | None = None
    device_name: str | None = None
    browser_name: str | None = None
    browser_version: str | None = None
    operating_system: str | None = None
    device_type: str | None = None
    ip_address: str | None = None
    is_active: bool
    is_current: bool
    created_at: datetime
    last_activity: datetime
    expires_at: datetime | None = None


class AdminSessionsResponse(BaseModel):
    """Список сессий всех пользователей"""

    items: list[AdminSessionItem]
    total: int
    page: int
    limit: int
    total_pages: int


class AdminSessionStats(BaseModel):
    """Статистика сессий по всей системе"""

    total_sessions: int
    active_sessions: int
    expired_sessions: int
    active_users: int


class AdminAuditItem(BaseModel):
    """Запись аудит-лога в админ-панели"""

    id: int
    entity_type: str
    entity_id: int
    action: str
    old_values: dict[str, Any] | None = None
    new_values: dict[str, Any] | None = None
    performed_by: int | None = None
    performed_at: datetime
    user_name: str = ""
    user_email: str | None = None


class AdminAuditListResponse(BaseModel):
    """Список аудит-логов всех пользователей"""

    items: list[AdminAuditItem]
    total: int
    page: int
    limit: int
    total_pages: int


class AdminOverview(BaseModel):
    """Обзорная статистика для админ-панели"""

    total_users: int
    total_roles: int
    total_ideas: int
    total_projects: int
    total_workspaces: int
    total_sessions: int
    active_sessions: int
    active_users: int
    recent_activity: list[AdminAuditItem]
