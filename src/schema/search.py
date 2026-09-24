from __future__ import annotations

from pydantic import BaseModel


class SearchProjectItem(BaseModel):
    """Элемент поиска проектов"""

    id: int
    name: str
    description: str | None = None
    workspace_id: int | None = None
    workspace_name: str | None = None
    status: str | None = None
    progress: int = 0


class SearchSpaceItem(BaseModel):
    """Элемент поиска пространств"""

    id: int
    title: str
    description: str | None = None
    category: str | None = None
    projects_count: int = 0
    members_count: int = 0


class SearchUserItem(BaseModel):
    """Элемент поиска участников"""

    id: int
    first_name: str | None = None
    last_name: str | None = None
    middle_name: str | None = None
    email: str | None = None
    role: str | None = None


class SearchResponse(BaseModel):
    """Агрегированный ответ глобального поиска"""

    projects: list[SearchProjectItem] = []
    spaces: list[SearchSpaceItem] = []
    users: list[SearchUserItem] = []
