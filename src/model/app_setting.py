from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class AppSetting(Base):
    """Глобальная настройка инстанса.

    Ключ и тип значения описаны в реестре (`src/core/app_settings_registry.py`),
    а сама таблица хранит только переопределения администратора: отсутствие
    строки означает «действует дефолт из реестра». Поэтому новую настройку
    можно завести без миграции и без сидирования данных.
    """

    __tablename__ = "app_setting"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Уникальность объявлена в модели, а не только в миграции: иначе
    # autogenerate считает constraint внешним и предлагает его удалить.
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)

    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"AppSetting(id={self.id!r}, key={self.key!r}, value={self.value!r})"
