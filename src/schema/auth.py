from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from fastapi.security import OAuth2PasswordRequestForm


class Token(BaseModel):
    """Схема токена для аутентификации"""

    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    """Схема для входа в систему"""

    username: str = Field(..., description="Email пользователя")
    password: str = Field(..., description="Пароль пользователя")


# Type alias для обратной совместимости
OAuth2PasswordRequestForm = LoginRequest
