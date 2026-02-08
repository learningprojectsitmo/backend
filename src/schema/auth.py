from __future__ import annotations

from pydantic import BaseModel, EmailStr


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
