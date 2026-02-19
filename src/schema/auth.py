from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr


class Token(BaseModel):
    """Схема токена для аутентификации"""

    access_token: str
    token_type: str


class PasswordResetRequest(BaseModel):
    """Схема для запроса сброса пароля"""

    email: EmailStr


class PasswordResetResponse(BaseModel):
    """Схема для ответа при запросе сброса"""

    message: str = "The email has been sent"


class PasswordResetSuccessfulResponse(BaseModel):
    """Схема для успешного ответа при запросе сброса пароля"""

    message: str = "Password reset successfully"


class PasswordResetConfirm(BaseModel):
    """Схема для подтверждения нового пароля"""

    token: str
    new_password: str


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
    limit: int
    total_pages: int


class EntityCreate(BaseModel):
    name: str
    model_config = ConfigDict(from_attributes=True)

class EntityUpdate(BaseModel):
    name: str | None = None

class EntityFull(EntityCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class EntityListResponse(BaseModel):
    items: list[EntityFull]
    total: int
    page: int
    limit: int
    total_pages: int


class PermissionCreate(BaseModel):
    entity_id: int
    can_create: bool
    can_read: bool
    can_update: bool
    can_delete: bool
    model_config = ConfigDict(from_attributes=True)

class PermissionUpdate(BaseModel):
    can_create: bool | None = None
    can_read: bool | None = None
    can_update: bool | None = None
    can_delete: bool | None = None

class PermissionFull(PermissionCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class PermissionListResponse(BaseModel):
    items: list[PermissionFull]
    total: int
    page: int
    limit: int
    total_pages: int

class UserPermissionCreate(BaseModel):
    user_id: int
    permission_id: int

class UserPermissionFull(UserPermissionCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class RolePermissionCreate(BaseModel):
    role_id: int
    permission_id: int

class RolePermissionFull(RolePermissionCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
