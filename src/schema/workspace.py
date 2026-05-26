from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WorkSpaceCreate(BaseModel):
    """Схема для создания workspace"""

    name: str
    author_id: int | None = None
    status_id: int | None = None
    category_id: int | None = None
    color: str | None = None
    description: str | None = None


class WorkSpaceUpdate(BaseModel):
    """Схема для обновления workspace"""

    name: str | None = None
    status_id: int | None = None
    category_id: int | None = None
    color: str | None = None
    description: str | None = None


class WorkSpaceFull(WorkSpaceCreate):
    """Полная схема workspace"""

    id: int
    author_id: int
    status_id: int
    category_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkSpaceResponse(BaseModel):
    """Схема ответа с workspace"""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class Space(BaseModel):
    """Схема workspace для списка с расширенными данными"""

    id: int
    title: str
    projectsCount: int
    membersCount: int
    color: str
    category: str
    category_id: int | None = None
    description: str | None = None
    icon_url: str | None = None
    author_id: int


class Category(BaseModel):
    """Схема категории workspace"""

    id: int
    name: str
    color: str | None = None


class SpacesListResponse(BaseModel):
    """Схема ответа со списком workspace"""

    categories: list[Category]
    spaces: list[Space]
    page: int | None = None
    limit: int | None = None
    total: int | None = None
    role: str
