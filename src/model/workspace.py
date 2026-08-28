from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.project import Project
    from src.model.user import User


class WorkSpaceCategories(Base):
    __tablename__ = "workspace_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    # Отношения
    workspaces: Mapped[list[WorkSpace]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"WorkSpaceCategories(id={self.id!r}, name={self.name!r}, created_at={self.created_at!r})"


class WorkSpace(Base):
    __tablename__ = "workspace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey("workspace_status.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("workspace_categories.id"), nullable=True)
    color: Mapped[str] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    # Отношения
    category: Mapped[WorkSpaceCategories | None] = relationship(back_populates="workspaces")
    projects: Mapped[list[Project]] = relationship(back_populates="workspace")

    def __repr__(self) -> str:
        return (
            f"WorkSpace(id={self.id!r}, name={self.name!r}, author_id={self.author_id!r}, "
            f"status_id={self.status_id!r}, category_id={self.category_id!r})"
        )


class WorkSpaceStatus(Base):
    __tablename__ = "workspace_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"WorkSpaceStatus(id={self.id!r}, name={self.name!r}, status_id={self.status_id!r})"


class WorkSpaceParticipation(Base):
    __tablename__ = "workspace_participation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    participant_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), nullable=True, default=2)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    participant: Mapped[User] = relationship(back_populates="workspace_participations")

    def __repr__(self) -> str:
        return f"WorkSpaceParticipation(id={self.id!r}, workspace_id={self.workspace_id!r}, participant_id={self.participant_id!r})"
