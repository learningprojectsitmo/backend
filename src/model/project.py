from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Table, UniqueConstraint, func
from sqlalchemy import Column as SAColumn
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.kanban_models import Column
    from src.model.resume import Resume
    from src.model.user import User
    from src.model.workspace import WorkSpace

project_tag = Table(
    "project_tag",
    Base.metadata,
    SAColumn("project_id", Integer, ForeignKey("project.id"), primary_key=True),
    SAColumn("tag_id", Integer, ForeignKey("tag.id"), primary_key=True),
)


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspace.id"), nullable=True)
    theme: Mapped[str | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(nullable=True)
    max_participants: Mapped[int | None] = mapped_column(nullable=True)

    status_id: Mapped[int | None] = mapped_column(ForeignKey("project_status.id"), nullable=True)
    status: Mapped[ProjectStatus | None] = relationship(back_populates="projects")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project_type_id: Mapped[int | None] = mapped_column(ForeignKey("project_type.id"), nullable=True)
    current_stage_id: Mapped[int | None] = mapped_column(ForeignKey("project_stage.id"), nullable=True)
    stage_pending_approval: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="0")

    project_type: Mapped[ProjectType | None] = relationship(back_populates="projects")
    current_stage: Mapped[ProjectStage | None] = relationship(foreign_keys=[current_stage_id])
    stage_transitions: Mapped[list[StageTransition]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )

    tags: Mapped[list[Tag]] = relationship(
        secondary=project_tag,
        back_populates="projects",
        lazy="selectin",
    )

    author: Mapped[User] = relationship(back_populates="projects_led")
    workspace: Mapped[WorkSpace | None] = relationship(back_populates="projects")
    responses: Mapped[list[Response]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    participants: Mapped[list[ProjectParticipation]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    vacancies: Mapped[list[ProjectVacancy]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    columns: Mapped[list[Column]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Column.position",
    )

    def __repr__(self) -> str:
        return (
            f"Project(id={self.id!r}, author_id={self.author_id!r}, "
            f"workspace_id={self.workspace_id!r}, description={self.description!r})"
        )


class ProjectStatus(Base):
    __tablename__ = "project_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    projects: Mapped[list[Project]] = relationship(back_populates="status")

    def __repr__(self) -> str:
        return f"ProjectStatus(id={self.id!r}, name={self.name!r}, color={self.color!r})"


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    projects: Mapped[list[Project]] = relationship(
        secondary=project_tag,
        back_populates="tags",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"Tag(id={self.id!r}, name={self.name!r})"


class ProjectParticipation(Base):
    __tablename__ = "project_participation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    participant_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="participants")
    participant: Mapped[User] = relationship(back_populates="projects_in")

    def __repr__(self) -> str:
        return (
            f"ProjectParticipation(id={self.id!r}, project_id={self.project_id!r}, "
            f"participant_id={self.participant_id!r})"
        )


class Response(Base):
    __tablename__ = "response"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    respondent_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    vacancy_id: Mapped[int | None] = mapped_column(ForeignKey("project_vacancy.id"), nullable=True)
    inviter_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resume.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="response")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    respondent: Mapped[User] = relationship(foreign_keys=[respondent_id], back_populates="responses")
    inviter: Mapped[User | None] = relationship(foreign_keys=[inviter_id])
    project: Mapped[Project] = relationship(back_populates="responses")
    vacancy: Mapped[ProjectVacancy | None] = relationship(back_populates="responses")
    resume: Mapped[Resume | None] = relationship(foreign_keys=[resume_id])

    def __repr__(self) -> str:
        return f"Response(id={self.id!r}, respondent_id={self.respondent_id!r}, project_id={self.project_id!r})"


class ProjectVacancy(Base):
    __tablename__ = "project_vacancy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    tasks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    required_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    project: Mapped[Project] = relationship(back_populates="vacancies")
    responses: Mapped[list[Response]] = relationship(back_populates="vacancy")

    def __repr__(self) -> str:
        return (
            f"ProjectVacancy(id={self.id!r}, project_id={self.project_id!r}, "
            f"title={self.title!r}, required_count={self.required_count!r})"
        )


class ProjectType(Base):
    __tablename__ = "project_type"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_project_type_workspace_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspace.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    workspace: Mapped[WorkSpace | None] = relationship(back_populates="project_types")
    stages: Mapped[list[ProjectStage]] = relationship(
        back_populates="project_type",
        cascade="all, delete-orphan",
        order_by="ProjectStage.order",
    )
    projects: Mapped[list[Project]] = relationship(back_populates="project_type")

    def __repr__(self) -> str:
        return f"ProjectType(id={self.id!r}, name={self.name!r})"


class ProjectStage(Base):
    __tablename__ = "project_stage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    project_type_id: Mapped[int] = mapped_column(ForeignKey("project_type.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project_type: Mapped[ProjectType] = relationship(back_populates="stages")

    def __repr__(self) -> str:
        return (
            f"ProjectStage(id={self.id!r}, name={self.name!r}, order={self.order!r}, "
            f"requires_approval={self.requires_approval!r})"
        )


class StageTransition(Base):
    __tablename__ = "stage_transition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    stage_id: Mapped[int] = mapped_column(ForeignKey("project_stage.id"), nullable=False)
    from_stage_id: Mapped[int | None] = mapped_column(ForeignKey("project_stage.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # advance, approve, reject
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    project: Mapped[Project] = relationship(back_populates="stage_transitions")
    stage: Mapped[ProjectStage] = relationship(foreign_keys=[stage_id])
    from_stage: Mapped[ProjectStage | None] = relationship(foreign_keys=[from_stage_id])
    actor: Mapped[User] = relationship(foreign_keys=[actor_id])

    def __repr__(self) -> str:
        return (
            f"StageTransition(id={self.id!r}, project_id={self.project_id!r}, "
            f"stage_id={self.stage_id!r}, action={self.action!r})"
        )
