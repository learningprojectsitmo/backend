from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from model.workspace import WorkSpace
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.user import User
    from src.model.kanban_models import Column

project_tag = Table(
    "project_tag",
    Base.metadata,
    Column("project_id", Integer, ForeignKey("project.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tag.id"), primary_key=True),
)


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspace.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(nullable=True)
    max_participants: Mapped[int | None] = mapped_column(nullable=True)

    status_id: Mapped[int | None] = mapped_column(ForeignKey("project_status.id"), nullable=True)
    status: Mapped[ProjectStatus | None] = relationship(back_populates="projects")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tags: Mapped[list[Tag]] = relationship(
        secondary=project_tag,
        back_populates="projects",
        lazy="selectin",
    )

    author: Mapped[User] = relationship(back_populates="projects_led")
    workspace: Mapped[WorkSpace | None] = relationship(back_populates="projects")
    responses: Mapped[list['Response']] = relationship(
        # TODO do we want to store responses to a deleted project?
        back_populates="project",
        cascade="all, delete-orphan",
    )

    participants: Mapped[list[ProjectParticipation]] = relationship(back_populates="project")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    columns: Mapped[list[Column]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Column.position"
    )

    def __repr__(self) -> str:
        return f"Project(id={self.id!r}, author_id={self.author_id!r}, workspace_id={self.workspace_id!r}, description={self.description!r})"