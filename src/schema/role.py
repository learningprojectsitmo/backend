from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RoleCreate(BaseModel):
    name: str
    model_config = ConfigDict(from_attributes=True)


class RoleUpdate(BaseModel):
    name: str | None = None


class RoleFull(RoleCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class RoleListResponse(BaseModel):
    items: list[RoleFull]
    total: int
    page: int
    page_size: int
    total_pages: int


class RolePermissionCreate(BaseModel):
    role_id: int
    permission_id: int


class RolePermissionCreateAPI(BaseModel):
    role_id: int
    permission_str: str


class RolePermissionRepr(BaseModel):
    entity_name: str
    allowed_permissions: list[str]


class RolePermissionFull(RolePermissionCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
