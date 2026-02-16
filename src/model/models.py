from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Time, func
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
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="student")

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
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User | None] = relationship()

    def __repr__(self) -> str:
        return f"AuditLog(id={self.id}, entity_type={self.entity_type!r}, entity_id={self.entity_id}, action={self.action!r})"


class DefenseProjectType(Base):
    __tablename__ = "defense_project_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    slots: Mapped[list["DefenseSlot"]] = relationship(back_populates="project_type")

    grading_criteria: Mapped[list["GradingCriteria"]] = relationship(
        back_populates="project_type",
        cascade="all, delete-orphan"
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"DefenseProjectType(id={self.id!r}, name={self.name!r})"


class DefenseDay(Base):
    __tablename__ = "defense_day"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    date: Mapped[date] = mapped_column(Date, nullable=False)
    max_slots: Mapped[int] = mapped_column(Integer, nullable=False)
    first_slot_time: Mapped[time] = mapped_column(Time, nullable=False)

    slots: Mapped[list["DefenseSlot"]] = relationship(
        back_populates="defense_day",
        cascade="all, delete-orphan",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"DefenseDay(id={self.id!r}, date={self.date!r}, max_slots={self.max_slots!r})"


class DefenseSlot(Base):
    __tablename__ = "defense_slot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    defense_day_id: Mapped[int] = mapped_column(ForeignKey("defense_day.id"), nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    project_type_id: Mapped[int] = mapped_column(ForeignKey("defense_project_type.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)

    capacity: Mapped[int] = mapped_column(Integer, nullable=False)

    defense_day: Mapped[DefenseDay] = relationship(back_populates="slots")
    project_type: Mapped[DefenseProjectType] = relationship(back_populates="slots")
    registrations: Mapped[list["DefenseRegistration"]] = relationship(
        back_populates="slot",
        cascade="all, delete-orphan",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"DefenseSlot(id={self.id!r}, title={self.title!r}, start_at={self.start_at!r})"


class DefenseRegistration(Base):
    __tablename__ = "defense_registration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    slot_id: Mapped[int] = mapped_column(ForeignKey("defense_slot.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)

    slot: Mapped[DefenseSlot] = relationship(back_populates="registrations")
    user: Mapped[User] = relationship()

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"DefenseRegistration(id={self.id!r}, slot_id={self.slot_id!r}, user_id={self.user_id!r})"


class GradingCriteria(Base):
    """Критерии оценивания для разных типов проектов"""
    __tablename__ = "grading_criteria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Связь с типом проекта
    project_type_id: Mapped[int] = mapped_column(
        ForeignKey("defense_project_type.id"),
        nullable=False
    )

    # Данные критерия
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    max_score: Mapped[float] = mapped_column(Integer, nullable=False)  # Используем Integer вместо Float
    weight: Mapped[float] = mapped_column(Integer, nullable=False, default=1)

    # Порядок отображения
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    project_type: Mapped["DefenseProjectType"] = relationship(back_populates="grading_criteria")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"GradingCriteria(id={self.id!r}, name={self.name!r}, max_score={self.max_score!r})"

