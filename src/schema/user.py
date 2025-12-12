
from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """Базовая схема пользователя"""
    email: EmailStr | None = None
    first_name: str
    middle_name: str
    last_name: str | None = None


class UserCreate(UserBase):
    """Схема для создания пользователя"""
    password_string: str
    isu_number: int | None = None


class UserFull(UserBase):
    """Полная схема пользователя"""
    id: int
    isu_number: int | None = None
    tg_nickname: str | None = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Схема для обновления пользователя"""
    email: EmailStr | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    isu_number: int | None = None
    tg_nickname: str | None = None


class UserResponse(BaseModel):
    """Схема ответа с пользователем"""
    id: int
    email: EmailStr

    class Config:
        from_attributes = True


class UserListItem(BaseModel):
    """Схема элемента списка пользователей"""
    id: int
    email: EmailStr
    first_name: str
    middle_name: str
    last_name: str | None = None
    isu_number: int | None = None
    tg_nickname: str | None = None

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """Схема ответа со списком пользователей"""
    items: list[UserListItem]
    total: int
    page: int
    limit: int
    total_pages: int
