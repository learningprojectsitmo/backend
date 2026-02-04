from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from src.util.validator import validate_telegram_username


class UserBase(BaseModel):
    """Базовая схема пользователя"""

    email: EmailStr | None = None
    first_name: str = Field(..., min_length=1, max_length=100)
    middle_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    telegram: Optional[str] = Field(
        None,
        min_length=6,
        max_length=33,
        pattern=r'^@\w{5,32}$',
        description="Telegram username в формате @username (5-32 символа, только буквы, цифры и подчеркивания)"
    )

    @field_validator('telegram')
    @classmethod
    def validate_telegram(cls, v: Optional[str]) -> Optional[str]:
        """Валидация Telegram username"""
        return validate_telegram_username(v)


class UserCreate(UserBase):
    """Схема для создания пользователя"""

    password_string: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Пароль (минимум 8 символов)"
    )
    isu_number: int | None = Field(
        None,
        ge=100000,
        le=999999,
        description="ISU номер (6 цифр)"
    )

    @field_validator('telegram')
    @classmethod
    def validate_telegram_on_create(cls, v: Optional[str]) -> Optional[str]:
        """Дополнительная валидация при создании"""
        validated = validate_telegram_username(v)

        if validated:
            username_part = validated[1:].lower()
            forbidden_names = {'admin', 'support', 'help', 'service', 'bot', 'system'}

            if username_part in forbidden_names:
                raise ValueError(f"Username '{validated}' зарезервирован")

        return validated


class UserCreateByISU(BaseModel):
    """Схема для создания пользователя по ИСУ номеру"""

    isu_number: int = Field(
        ...,
        ge=100000,
        le=999999,
        description="ИСУ номер (6 цифр)"
    )
    password_string: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Пароль (минимум 8 символов)"
    )
    telegram: Optional[str] = Field(
        None,
        min_length=6,
        max_length=33,
        pattern=r'^@\w{5,32}$',
        description="Telegram username (опционально)"
    )

    @field_validator('telegram')
    @classmethod
    def validate_telegram(cls, v: Optional[str]) -> Optional[str]:
        return validate_telegram_username(v)


class ISURegistrationResponse(BaseModel):
    """Ответ при регистрации по ИСУ"""
    user: UserResponse
    token: str
    message: str = "Регистрация по ИСУ успешно завершена"


class UserFull(UserBase):
    """Полная схема пользователя"""

    id: int
    isu_number: int | None = None
    tg_nickname: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    """Схема для обновления пользователя"""

    email: EmailStr | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    isu_number: int | None = None
    tg_nickname: str | None = None
    telegram: Optional[str] = Field(
        None,
        min_length=6,
        max_length=33,
        pattern=r'^@\w{5,32}$',
        description="Telegram username в формате @username"
    )

    @field_validator('telegram')
    @classmethod
    def validate_telegram_update(cls, v: Optional[str]) -> Optional[str]:
        """Валидация Telegram при обновлении"""
        return validate_telegram_username(v)


class UserResponse(BaseModel):
    """Схема ответа с пользователем"""

    id: int
    email: EmailStr
    first_name: str
    middle_name: str
    last_name: str | None = None
    telegram: Optional[str] = None
    isu_number: int | None = None
    tg_nickname: str | None = None

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
    telegram: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    """Схема ответа со списком пользователей"""

    items: list[UserListItem]
    total: int
    page: int
    limit: int
    total_pages: int

    model_config = ConfigDict(from_attributes=True)