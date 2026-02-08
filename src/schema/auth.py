from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Token(BaseModel):
    """Схема токена для аутентификации"""

    access_token: str
    token_type: str


class RoleCreate(BaseModel):
    name: str
    model_config = ConfigDict(from_attributes=True)


class RoleFull(RoleCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class RoleListResponse(BaseModel):
    items: list[RoleFull]
    total: int
    page: int
    limit: int
    total_pages: int


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
    limit: int
    total_pages: int


class UserPermissionFull(BaseModel):
    user_id: int
    permission_id: int
    model_config = ConfigDict(from_attributes=True)


class RolePermissionFull(BaseModel):
    role_id: int
    permission_id: int
    model_config = ConfigDict(from_attributes=True)
