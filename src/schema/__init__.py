# Общие экспорты схем из всех модулей
from __future__ import annotations

from .auth import Token
from .base import Blank, DeleteResponse, FindBase, FindDateRange, FindResult, PaginatedResponse
from .project import ProjectCreate, ProjectFull, ProjectListItem, ProjectListResponse, ProjectResponse, ProjectUpdate
from .resume import ResumeCreate, ResumeFull, ResumeListResponse, ResumeResponse, ResumeUpdate
from .user import UserBase, UserCreate, UserFull, UserListItem, UserListResponse, UserResponse, UserUpdate
from .defense import (
    DefenseDayCreate,
    DefenseDayFull,
    DefenseDayListItem,
    DefenseDayListResponse,
    DefenseRegistrationCreate,
    DefenseRegistrationFull,
    DefenseSlotBase,
    DefenseSlotCreate,
    DefenseSlotFull,
    DefenseSlotListItem,
    DefenseSlotListResponse,
    ProjectTypeCreate,
    ProjectTypeFull,
    ProjectTypeInfo,
    ProjectTypeListResponse,
)

__all__ = [
    "Blank",
    "DeleteResponse",
    "FindBase",
    "FindDateRange",
    "FindResult",
    "PaginatedResponse",
    "ProjectCreate",
    "ProjectFull",
    "ProjectListItem",
    "ProjectListResponse",
    "ProjectResponse",
    "ProjectUpdate",
    "ResumeCreate",
    "ResumeFull",
    "ResumeListResponse",
    "ResumeResponse",
    "ResumeUpdate",
    "Token",
    "UserBase",
    "UserCreate",
    "UserFull",
    "UserListItem",
    "UserListResponse",
    "UserResponse",
    "UserUpdate",
    "DefenseDayCreate",
    "DefenseDayFull",
    "DefenseDayListItem",
    "DefenseDayListResponse",
    "DefenseSlotBase",
    "DefenseSlotCreate",
    "DefenseSlotFull",
    "DefenseSlotListItem",
    "DefenseSlotListResponse",
    "DefenseRegistrationCreate",
    "DefenseRegistrationFull",
    "ProjectTypeCreate",
    "ProjectTypeFull",
    "ProjectTypeInfo",
    "ProjectTypeListResponse",
]
