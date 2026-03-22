# Общие экспорты схем из всех модулей
from __future__ import annotations

from .auth import Token
from .base import Blank, DeleteResponse, FindBase, FindDateRange, FindResult, PaginatedResponse
from .project import ProjectCreate, ProjectFull, ProjectListItem, ProjectListResponse, ProjectResponse, ProjectUpdate
from .resume import ResumeCreate, ResumeFull, ResumeListResponse, ResumeResponse, ResumeUpdate
from .user import UserBase, UserCreate, UserFull, UserListItem, UserListResponse, UserResponse, UserUpdate
from .kanban import (
    # Базовые типы
    TaskPriority,
    # Проекты
    ProjectBoardResponse,
    # Колонки
    ColumnBase, ColumnCreate, ColumnUpdate,
    ColumnResponse, ColumnListResponse, ColumnWithTasksAndSubtasksResponse,
    # Задачи
    TaskBase, TaskCreate, TaskUpdate, TaskMove, TaskReorder,
    TaskResponse, TaskListResponse, TaskHistoryResponse,
    TaskFilter,
    # Подзадачи
    SubtaskBase, SubtaskCreate, SubtaskUpdate,
    SubtaskReorder, SubtaskResponse, SubtaskListResponse,
)

__all__ = [
    # Базовые схемы
    "Blank",
    "DeleteResponse",
    "FindBase",
    "FindDateRange",
    "FindResult",
    "PaginatedResponse",
    # Проекты
    "ProjectCreate",
    "ProjectFull",
    "ProjectListItem",
    "ProjectListResponse",
    "ProjectResponse",
    "ProjectUpdate",
    # Резюме
    "ResumeCreate",
    "ResumeFull",
    "ResumeListResponse",
    "ResumeResponse",
    "ResumeUpdate",
    # Авторизация
    "Token",
    # Пользователи
    "UserBase",
    "UserCreate",
    "UserFull",
    "UserListItem",
    "UserListResponse",
    "UserResponse",
    "UserUpdate",
    # Канбан - базовые типы
    "TaskPriority",
    # Канбан - проекты
    "ProjectBoardResponse",
    # Канбан - колонки
    "ColumnBase",
    "ColumnCreate",
    "ColumnUpdate",
    "ColumnResponse",
    "ColumnListResponse",
    "ColumnWithTasksAndSubtasksResponse",
    # Канбан - задачи
    "TaskBase",
    "TaskCreate",
    "TaskUpdate",
    "TaskMove",
    "TaskReorder",
    "TaskResponse",
    "TaskListResponse",
    "TaskHistoryResponse",
    "TaskFilter",
    # Канбан - подзадачи
    "SubtaskBase",
    "SubtaskCreate",
    "SubtaskUpdate",
    "SubtaskReorder",
    "SubtaskResponse",
    "SubtaskListResponse",
]