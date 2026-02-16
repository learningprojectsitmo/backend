from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from src.util.validator import TelegramValidator

class UserBase(BaseModel):
    """Базовая схема пользователя"""

    email: EmailStr | None = None
    first_name: str
    middle_name: str
    last_name: str | None = None
    role_id: int


class UserCreate(UserBase):
    """Схема для создания пользователя"""

    password_string: str
    isu_number: int | None = None


class UserFull(UserBase):
    """Полная схема пользователя"""

    id: int
    isu_number: int | None = None
    tg_nickname: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator('tg_nickname')
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
    role_id: int | None = None

    @field_validator('tg_nickname')
    @classmethod
    def validate_tg_nickname(cls, v):
        return TelegramValidator.validate_tg_nickname_optional(v)


class UserResponse(BaseModel):
    """Схема ответа с пользователем"""

    id: int
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

    @field_validator('tg_nickname')
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
