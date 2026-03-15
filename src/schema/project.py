from __future__ import annotations
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    """Схема для создания проекта"""

    name: str
    author_id: int | None = None


class ProjectUpdate(BaseModel):
    """Схема для обновления проекта"""

    name: str | None = None
    author_id: int | None = None
    description: str | None = None
    max_participants: int | None = None
    status: str | None = None
    deadline: datetime | None = None
    progress: int | None = None
    tags: list[str] | None = None 

class ProjectFull(ProjectCreate):
    """Полная схема проекта"""

    id: int
    description: str | None = None
    max_participants: int | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(BaseModel):
    """Схема ответа с проектом"""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ProjectListItem(BaseModel):
    """Схема элемента списка проектов"""
    
    id: int
    name: str
    status: str
    deadline: datetime | None = None
    participants_count: int
    progress: int
    tags: list[str] = []

    model_config = ConfigDict(from_attributes=True)

class ProjectListResponse(BaseModel):
    """Схема ответа со списком проектов"""

    items: list[ProjectListItem]
    total: int
    page: int
    limit: int
    total_pages: int
