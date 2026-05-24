from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from src.util.validator import TelegramValidator


class UserBase(BaseModel):
    """Базовая схема пользователя"""

    email: EmailStr | None = None
    first_name: str
    middle_name: str
    last_name: str | None = None
    role_id: int
    isu_number: int | None = None
    tg_nickname: str | None = None
    phone: str | None = None
    vk_nickname: str | None = None


class UserCreate(UserBase):
    """Схема для создания пользователя"""

    password: str


class UserCreateHashedPwd(UserBase):
    """Схема для создания пользователя"""

    password_hashed: str


class UserFull(UserBase):
    """Полная схема пользователя"""

    id: int

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tg_nickname")
    @classmethod
    def validate_tg_nickname(cls, v):
        return TelegramValidator.validate_tg_nickname_optional(v)


class UserUpdate(BaseModel):
    """Схема для обновления пользователя"""

    email: EmailStr | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    isu_number: int | None = None
    tg_nickname: str | None = None
    phone: str | None = None
    vk_nickname: str | None = None
    role_id: int | None = None

    @field_validator("tg_nickname")
    @classmethod
    def validate_tg_nickname(cls, v):
        return TelegramValidator.validate_tg_nickname_optional(v)


class UserResponse(BaseModel):
    """Схема ответа с пользователем"""

    id: int
    first_name: str
    last_name: str | None = None
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)


class UserListItem(BaseModel):
    """Схема элемента списка пользователей"""

    id: int
    email: EmailStr
    first_name: str
    middle_name: str
    last_name: str | None = None
    isu_number: int | None = None
    tg_nickname: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tg_nickname")
    @classmethod
    def validate_tg_nickname(cls, v):
        return TelegramValidator.validate_tg_nickname_optional(v)


class UserListResponse(BaseModel):
    """Схема ответа со списком пользователей"""

    items: list[UserListItem]
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


class NewUserCreate(UserCreateHashedPwd):
    """Схема для создания пользователя"""

    code: int
    expires_at: datetime


class NewUserUpdate(BaseModel):
    """Схема для обновления пользователя"""

    code: int
    expires_at: datetime


class NewUserResponse(BaseModel):
    """Схема ответа для временного пользователя"""

    id: int
    email: str

    model_config = ConfigDict(from_attributes=True)
