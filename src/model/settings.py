from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class SettingsType(Base):
    __tablename__ = "settings_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    space_settings: Mapped[list[SpaceSettings]] = relationship(back_populates="settings_type")

    def __repr__(self) -> str:
        return f"SettingsType(id={self.id!r}, name={self.name!r})"


class SpaceSettings(Base):
    __tablename__ = "space_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    settings_type_id: Mapped[int] = mapped_column(ForeignKey("settings_type.id"), nullable=False)
    space_id: Mapped[int] = mapped_column(ForeignKey("workspace.id"), nullable=False, unique=True)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    join_policy: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    default_role_id: Mapped[int | None] = mapped_column(ForeignKey("role.id"), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    allow_multi_project_participation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_multi_project_creation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_project_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    settings_type: Mapped[SettingsType] = relationship(back_populates="space_settings")

    def __repr__(self) -> str:
        return (
            f"SpaceSettings(id={self.id!r}, space_id={self.space_id!r}, "
            f"visibility={self.visibility!r}, join_policy={self.join_policy!r})"
        )
