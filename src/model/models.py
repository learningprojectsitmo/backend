from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    first_name: Mapped[str] = mapped_column(String(30), nullable=False)
    middle_name: Mapped[str] = mapped_column(String(40), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(30), nullable=True)

    email: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    isu_number: Mapped[int | None] = mapped_column(nullable=True)
    tg_nickname: Mapped[str | None] = mapped_column(String(40), nullable=True)

    password_hashed: Mapped[str] = mapped_column(String, nullable=False)

    resumes: Mapped[list[Resume]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    responses: Mapped[list[Response]] = relationship(
        back_populates="respondent",
        cascade="all, delete-orphan",
    )
    projects_led: Mapped[list[Project]] = relationship(
        # The project will not be deleted when its author gets deleted
        back_populates="author",
    )
    projects_in: Mapped[list[ProjectParticipation]] = relationship(
        back_populates="participant",
        cascade="all, delete-orphan",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, first_name={self.first_name!r}, isu_number={self.isu_number!r})"


class Resume(Base):
    __tablename__ = "resume"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    header: Mapped[str] = mapped_column(nullable=False)
    resume_text: Mapped[str | None] = mapped_column(nullable=True)

    user: Mapped[User] = relationship(back_populates="resumes")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # skills (particular, like docker, git etc.)
    # roles (general, like backend, Project Management etc.)

    def __repr__(self) -> str:
        return f"Resume(id={self.id!r}, author_id={self.author_id!r}, header={self.header!r})"


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    description: Mapped[str | None] = mapped_column(nullable=True)
    max_participants: Mapped[str | None] = mapped_column(nullable=True)

    author: Mapped[User] = relationship(back_populates="projects_led")
    responses: Mapped[list[Response]] = relationship(
        # TODO do we want to store responses to a deleted project?
        back_populates="project",
        cascade="all, delete-orphan",
    )

    # status_id (for later, need to create the Status table first)
    # skills (particular, like docker, git etc.)
    # roles (general, like backend, Project Management etc.)
    participants: Mapped[list[ProjectParticipation]] = relationship(back_populates="project")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"Project(id={self.id!r}, author_id={self.author_id!r}, description={self.description!r})"


class ProjectParticipation(Base):
    __tablename__ = "project_participation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    participant_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)

    project: Mapped[Project] = relationship(back_populates="participants")
    participant: Mapped[User] = relationship(back_populates="projects_in")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Response(Base):
    __tablename__ = "response"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    respondent_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    note: Mapped[str] = mapped_column(String(200), nullable=True)

    # TODO not all relationships are needed. Remove unneeded
    respondent: Mapped[User] = relationship(back_populates="responses")
    project: Mapped[Project] = relationship(back_populates="responses")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"Response(id={self.id!r}, respondent_id={self.respondent_id!r}, note={self.note!r})"


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

    # Отношения
    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return f"Session(id={self.id!r}, user_id={self.user_id!r}, device_name={self.device_name!r}, is_active={self.is_active!r})"

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id: Mapped[Integer] = mapped_column(Integer, primary_key=True, autoincrement=True)

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)  # user, project, resume, etc
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # INSERT, UPDATE
    old_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    performed_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )

    user: Mapped[User | None] = relationship()
    def __repr__(self) -> str:
        return f"AuditLog(id={self.id}, entity_type={self.entity_type!r}, entity_id={self.entity_id}, action={self.action!r})"