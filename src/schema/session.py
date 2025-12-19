from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SessionBase(BaseModel):
    """Базовая схема сессии"""

    device_name: str | None = None
    browser_name: str | None = None
    browser_version: str | None = None
    operating_system: str | None = None
    device_type: str | None = None
    ip_address: str | None = None
    country: str | None = None
    city: str | None = None
    user_agent: str | None = None
    fingerprint: str | None = None


class SessionCreate(SessionBase):
    """Схема для создания сессии"""

    user_id: int = Field(..., description="ID пользователя")
    expires_at: datetime | None = Field(None, description="Время истечения сессии")


class SessionUpdate(BaseModel):
    """Схема для обновления сессии"""

    device_name: str | None = None
    browser_name: str | None = None
    browser_version: str | None = None
    operating_system: str | None = None
    device_type: str | None = None
    is_active: bool | None = None
    is_current: bool | None = None
    last_activity: datetime | None = None


class SessionResponse(SessionBase):
    """Схема ответа с сессией"""

    id: str
    user_id: int
    created_at: datetime
    last_activity: datetime
    expires_at: datetime | None
    is_active: bool
    is_current: bool

    class Config:
        from_attributes = True


class SessionListItem(SessionResponse):
    """Схема элемента списка сессий"""

    pass


class SessionListResponse(BaseModel):
    """Схема ответа со списком сессий"""

    sessions: list[SessionListItem]
    total: int
    current_session_id: str | None = None


class SessionTerminateRequest(BaseModel):
    """Схема для завершения сессий"""

    session_ids: list[str] = Field(..., description="ID сессий для завершения")
    terminate_all_except_current: bool = Field(False, description="Завершить все сессии кроме текущей")


class SessionTerminateResponse(BaseModel):
    """Схема ответа при завершении сессий"""

    terminated_sessions: list[str]
    message: str


class CurrentSessionInfo(BaseModel):
    """Информация о текущей сессии"""

    session_id: str
    device_info: SessionBase
    created_at: datetime
    last_activity: datetime
    expires_at: datetime | None = None


class SessionStats(BaseModel):
    """Статистика сессий пользователя"""

    total_sessions: int
    active_sessions: int
    current_session: CurrentSessionInfo | None = None
