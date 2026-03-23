from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PermissionCreate(BaseModel):
    name: str
    model_config = ConfigDict(from_attributes=True)


class PermissionFull(PermissionCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class PermissionListResponse(BaseModel):
    items: list[PermissionFull]
    total: int
    page: int
    page_size: int
    total_pages: int
