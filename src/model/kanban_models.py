from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.models import Project, User


class Column(Base):
    """Колонка канбан-доски"""

    __tablename__ = "column"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)

    # Настройки колонки
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # Название колонки
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="gray")  # Цвет (hex или имя)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Порядок колонки
    wip_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Лимит задач (опционально)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Отношения
    project: Mapped[Project] = relationship(back_populates="columns")
    tasks: Mapped[list[Task]] = relationship(
        back_populates="column", cascade="all, delete-orphan", order_by="Task.position"
    )

    def __repr__(self) -> str:
        return f"Column(id={self.id!r}, name={self.name!r}, project_id={self.project_id!r}, position={self.position!r})"


class Task(Base):
    """Задача внутри колонки канбан-доски"""

    __tablename__ = "task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Привязка к колонке (обязательно!)
    column_id: Mapped[int] = mapped_column(ForeignKey("column.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id"), nullable=False
    )  # Денормализация для быстрых запросов

    # Основные поля
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)  # id того, кто создал задачу

    # Дополнительные поля
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "low", "medium", "high", "urgent"
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Порядок сортировки внутри колонки
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # "backend,frontend,bug"

    # Множество ответственных
    assignees: Mapped[list[User]] = relationship(secondary="task_assignee", back_populates="tasks")

    # Множество подзадач
    subtasks: Mapped[list[Subtask]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="Subtask.position"
    )

    # Временные метки
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Отношения
    column: Mapped[Column] = relationship(back_populates="tasks")
    project: Mapped[Project] = relationship()
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"Task(id={self.id!r}, title={self.title!r}, column_id={self.column_id!r})"


class TaskAssignee(Base):
    """Связь задачи с ответственными"""

    __tablename__ = "task_assignee"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"TaskAssignee(task_id={self.task_id!r}, user_id={self.user_id!r})"


class TaskHistory(Base):
    """История изменений задачи"""

    __tablename__ = "task_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), nullable=False)

    # Что изменилось
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    old_column_id: Mapped[int | None] = mapped_column(ForeignKey("column.id"), nullable=True)
    new_column_id: Mapped[int | None] = mapped_column(ForeignKey("column.id"), nullable=True)

    # Дополнительная информация
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "move", "title", "description", "assignees"
    change_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Дополнительные данные

    # Временная метка
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Отношения
    task: Mapped[Task] = relationship()
    changed_by: Mapped[User] = relationship(foreign_keys=[changed_by_id])
    old_column: Mapped[Column] = relationship(foreign_keys=[old_column_id])
    new_column: Mapped[Column] = relationship(foreign_keys=[new_column_id])

    def __repr__(self) -> str:
        return f"TaskHistory(id={self.id!r}, task_id={self.task_id!r}, change_type={self.change_type!r})"


class Subtask(Base):
    """Подзадача внутри задачи канбан-доски"""

    __tablename__ = "subtask"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id", ondelete="CASCADE"), nullable=False)

    # Основные поля
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Дополнительные поля
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Отношения
    task: Mapped[Task] = relationship(back_populates="subtasks")
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"Subtask(id={self.id!r}, title={self.title!r}, task_id={self.task_id!r})"
