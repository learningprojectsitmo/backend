from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.education import Education
    from src.model.ideas import Idea
    from src.model.kanban_models import Task
    from src.model.language import Language
    from src.model.notification import Notification
    from src.model.portfolio import Portfolio
    from src.model.workspace import WorkSpaceParticipation
from src.model.project import Project, ProjectParticipation, Response
from src.model.resume import Resume


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    first_name: Mapped[str] = mapped_column(String(30), nullable=False)  # Имя
    last_name: Mapped[str | None] = mapped_column(String(30), nullable=True)  # Фамилия
    middle_name: Mapped[str] = mapped_column(String(40), nullable=False)  # Отчество

    email: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    isu_number: Mapped[int | None] = mapped_column(nullable=True)
    tg_nickname: Mapped[str | None] = mapped_column(String(40), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    vk_nickname: Mapped[str | None] = mapped_column(String(40), nullable=True)

    password_hashed: Mapped[str] = mapped_column(String, nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), nullable=False)

    role: Mapped[Role] = relationship(back_populates="users")

    resumes: Mapped[list[Resume]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    responses: Mapped[list[Response]] = relationship(
        back_populates="respondent",
        cascade="all, delete-orphan",
        foreign_keys="Response.respondent_id",
    )
    invited_responses: Mapped[list[Response]] = relationship(
        back_populates="inviter",
        cascade="all, delete-orphan",
        foreign_keys="Response.inviter_id",
    )
    projects_led: Mapped[list[Project]] = relationship(
        back_populates="author",
    )
    projects_in: Mapped[list[ProjectParticipation]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
    )
    workspace_participations: Mapped[list[WorkSpaceParticipation]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list[Task]] = relationship(secondary="task_assignee", back_populates="assignees")
    portfolios: Mapped[list[Portfolio]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    educations: Mapped[list[Education]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    languages: Mapped[list[Language]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    ideas: Mapped[list[Idea]] = relationship(
        back_populates="author",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    lang: Mapped[str] = mapped_column(String(10), nullable=False, server_default="ru")
    push_token: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="FCM/APNs push token for mobile")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, first_name={self.first_name!r}, isu_number={self.isu_number!r})"


class Permission(Base):
    __tablename__ = "permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)

    def __repr__(self) -> str:
        return f"Permission(id={self.id!r}, permission_name={self.name!r}"


class UserPermission(Base):
    __tablename__ = "user_permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permission.id"), nullable=False)

    def __repr__(self) -> str:
        return f"User_id({self.user_id!r}, perm_id={self.permission_id!r}"


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    users: Mapped[list[User]] = relationship(back_populates="role")

    def __repr__(self) -> str:
        return f"Role(id={self.id!r}, role_name={self.name!r}"


class RolePermission(Base):
    __tablename__ = "role_permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), nullable=False)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permission.id"), nullable=False)

    def __repr__(self) -> str:
        return f"Role_id({self.role_id!r}, perm_id={self.permission!r}"
