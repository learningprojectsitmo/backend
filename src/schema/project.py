from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class ParticipantPreview(BaseModel):
    id: int
    full_name: str
    avatar_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProjectStatusItem(BaseModel):
    name: str
    color: str

    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    """Схема для создания проекта"""

    name: str
    author_id: int | None = None
    description: str | None = None
    max_participants: int | None = None
    status_id: int | None = None
    deadline: datetime | None = None
    progress: int | None = None
    tags: list[str] | None = None


class ProjectUpdate(BaseModel):
    """Схема для обновления проекта"""

    name: str | None = None
    author_id: int | None = None
    description: str | None = None
    max_participants: int | None = None
    status_id: int | None = None
    deadline: datetime | None = None
    progress: int | None = None
    tags: list[str] | None = None


class ProjectFull(ProjectCreate):
    """Полная схема проекта"""
    id: int
    status: ProjectStatusItem | None = None
    tags: list[str] = []
    participants_count: int | None = None
    participants_preview: list[ParticipantPreview] = []

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tags", mode="before")
    @classmethod
    def transform_tags(cls, v):
        if isinstance(v, list):
            return [tag.name if hasattr(tag, "name") else tag for tag in v]
        return v

    @field_validator("participants_count", mode="before")
    @classmethod
    def set_participants_count(cls, v, info):
        # Если v — это None, пробуем посчитать длину списка участников из объекта
        if v is None and hasattr(info.data.get('participants'), '__len__'):
             return len(info.data.get('participants'))
        return v or 0


class ProjectResponse(BaseModel):
    """Схема ответа с проектом"""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class ProjectListItem(BaseModel):
    """Схема элемента списка проектов"""

    id: int
    name: str
    status: ProjectStatusItem
    deadline: datetime | None = None
    participants_count: int
    progress: int
    tags: list[str] = []
    participants_preview: list[ParticipantPreview] = []

    model_config = ConfigDict(from_attributes=True)


class ProjectListResponse(BaseModel):
    """Схема ответа со списком проектов"""

    items: list[ProjectListItem]
    total: int
    page: int
    limit: int
    total_pages: int
