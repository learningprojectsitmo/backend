from __future__ import annotations

from datetime import datetime
import enum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func, Enum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    first_name: Mapped[str] = mapped_column(String(30), nullable=False)        #Имя
    last_name: Mapped[str | None] = mapped_column(String(30), nullable=True)   #Фамилия
    middle_name: Mapped[str] = mapped_column(String(40), nullable=False)       #Отчество

    email: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    isu_number: Mapped[int | None] = mapped_column(nullable=True)
    tg_nickname: Mapped[str | None] = mapped_column(String(40), nullable=True)

    password_hashed: Mapped[str] = mapped_column(String, nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), nullable=False)

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


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), nullable=False)

    def __repr__(self) -> str:
        return f"Role(id={self.id!r}, role_name={self.name!r}"


class Permission(Base):
    __tablename__ = "permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), nullable=False)

    def __repr__(self) -> str:
        return f"Permission(id={self.id!r}, permission_name={self.name!r}"


class RolePermission(Base):
    __tablename__ = "role_permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"), nullable=False)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permission.id"), nullable=False)

    def __repr__(self) -> str:
        return f"Role_id({self.role_id!r}, perm_id={self.permission_id!r}"


class UserPermission(Base):
    __tablename__ = "user_permission"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permission.id"), nullable=False)

    def __repr__(self) -> str:
        return f"User_id({self.user_id!r}, perm_id={self.permission_id!r}"


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
    max_participants: Mapped[int | None] = mapped_column(nullable=True)

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

    tasks: Mapped[list["Task"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Task.status, Task.order"
    )

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


class PasswordReset(Base):
    __tablename__ = "password_reset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()


#Мб добавить больше колонок/статусов
class TaskStatus(str, enum.Enum):
    """Статусы задач для канбан-доски"""
    NOT_STARTED = "not_started"  # Не начато
    IN_PROGRESS = "in_progress"  # В процессе
    REVIEW = "review"            # Ревью
    DONE = "done"                 # Готово

#Возможно не понадобится
class TaskPriority(str, enum.Enum):
    """Приоритеты задач"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# Таблица для связи многие-ко-многим (задача - ответственные)
class TaskAssignee(Base):
    __tablename__ = "task_assignee"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    task: Mapped["Task"] = relationship(back_populates="assignees")
    user: Mapped["User"] = relationship()


class Task(Base):
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Основные поля
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    
    # Статус и приоритет
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.NOT_STARTED, nullable=False)
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False)
    
    # Порядок сортировки в колонке (для drag-and-drop)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Связи
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    
    # Временные метки
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Теги (храним как JSON строку или список)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # "backend,frontend,bug"
    
    # Отношения
    project: Mapped["Project"] = relationship(back_populates="tasks")
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    
    # Множество ответственных (бакалавры)
    assignees: Mapped[list["TaskAssignee"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"Task(id={self.id!r}, title={self.title!r}, status={self.status!r}, project_id={self.project_id!r})"


class TaskHistory(Base):
    """История изменений задачи (для уведомлений)"""
    __tablename__ = "task_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), nullable=False)
    
    # Что изменилось
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    old_status: Mapped[TaskStatus | None] = mapped_column(Enum(TaskStatus), nullable=True)
    new_status: Mapped[TaskStatus | None] = mapped_column(Enum(TaskStatus), nullable=True)
    
    # Доп. информация об изменении
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)  # status, title, description, assignees
    
    # Временная метка
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Отношения
    task: Mapped["Task"] = relationship()
    changed_by: Mapped["User"] = relationship(foreign_keys=[changed_by_id])
    
    def __repr__(self) -> str:
        return f"TaskHistory(id={self.id!r}, task_id={self.task_id!r}, changed_by={self.changed_by_id!r}, {self.old_status}->{self.new_status})"


class ColumnTemplate(Base):
    """Шаблоны колонок (для магистрантов/преподавателей)"""
    __tablename__ = "column_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    
    # Настройки колонки
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # Название колонки
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="gray")  # Цвет (hex или имя)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Порядок сортировки
    
    # С каким статусом задачи связана колонка
    task_status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), nullable=False)
    
    # Кто может изменять статус в этой колонке
    allowed_roles: Mapped[str] = mapped_column(String(100), nullable=False, default="bachelor")  # "bachelor,master,teacher"
    
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    # Отношения
    project: Mapped["Project"] = relationship()
    
    def __repr__(self) -> str:
        return f"ColumnTemplate(id={self.id!r}, name={self.name!r}, status={self.task_status!r})"