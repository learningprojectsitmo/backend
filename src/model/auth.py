from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.user import User


class Session(Base):
    __tablename__ = "session"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)  # UUID для уникальности
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)

    # Информация об устройстве и браузере
    device_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    browser_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    browser_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    operating_system: Mapped[str | None] = mapped_column(String(50), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # desktop, mobile, tablet

    # Сетевая информация
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv4 или IPv6
    country: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Статус сессии
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_current: Mapped[bool] = mapped_column(default=False, nullable=False)  # Текущая сессия пользователя

    # Дополнительная информация
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Отпечаток браузера

    # Refresh token (opaque, хранится только SHA-256 хеш)
    refresh_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    token_family: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Отношения
    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return f"Session(id={self.id!r}, user_id={self.user_id!r}, device_name={self.device_name!r}, is_active={self.is_active!r})"


class PasswordReset(Base):
    __tablename__ = "password_reset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()
