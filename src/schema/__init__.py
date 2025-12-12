# Общие экспорты схем из всех модулей
from .auth import Token
from .base import Blank, DeleteResponse, FindBase, FindDateRange, FindResult, PaginatedResponse
from .project import ProjectCreate, ProjectFull, ProjectListItem, ProjectListResponse, ProjectResponse, ProjectUpdate
from .resume import ResumeCreate, ResumeFull, ResumeListResponse, ResumeResponse, ResumeUpdate
from .user import UserBase, UserCreate, UserFull, UserListItem, UserListResponse, UserResponse, UserUpdate

__all__ = [
    # Auth
    "Token",
    # Base
    "PaginatedResponse", "DeleteResponse", "Blank", "FindBase", "FindResult", "FindDateRange",
    # User
    "UserBase", "UserCreate", "UserFull", "UserUpdate",
    "UserResponse", "UserListItem", "UserListResponse",
    # Project
    "ProjectCreate", "ProjectUpdate", "ProjectFull",
    "ProjectResponse", "ProjectListItem", "ProjectListResponse",
    # Resume
    "ResumeCreate", "ResumeUpdate", "ResumeFull",
    "ResumeResponse", "ResumeListResponse"
]
