from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WorkSpaceCreate(BaseModel):
    """Схема для создания workspace"""

    name: str
    author_id: int | None = None
    status_id: int | None = None


class WorkSpaceUpdate(BaseModel):
    """Схема для обновления workspace"""

    name: str | None = None
    status_id: int | None = None


class WorkSpaceFull(WorkSpaceCreate):
    """Полная схема workspace"""

    id: int
    author_id: int
    status_id: int

    model_config = ConfigDict(from_attributes=True)


class WorkSpaceResponse(BaseModel):
    """Схема ответа с workspace"""

    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)
