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
    # Задачи
    TaskBase, TaskCreate, TaskUpdate, TaskMove, TaskReorder,
    TaskResponse, TaskListResponse, TaskHistoryResponse,
    TaskFilter,
    # Колонки
    ColumnBase, ColumnCreate, ColumnUpdate,
    ColumnResponse, ColumnListResponse, ColumnWithTasksResponse,
    # Проекты
    ProjectBoardResponse,
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
    # Канбан - колонки
    "ColumnBase",
    "ColumnCreate",
    "ColumnUpdate",
    "ColumnResponse",
    "ColumnListResponse",
    "ColumnWithTasksResponse",
    # Канбан - проекты
    "ProjectBoardResponse",
]