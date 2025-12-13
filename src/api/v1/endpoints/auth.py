from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from src.core.container import get_auth_service
from src.core.dependencies import get_current_user
from src.schema.auth import LoginRequest, Token
from src.services.auth_service import AuthService

auth_router = APIRouter(prefix="/auth", tags=["authentication"])


@auth_router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    auth_service: AuthService = Depends(get_auth_service),
) -> Token:
    """Вход в систему и получение токена доступа"""
    return await auth_service.login_for_access_token(form_data)


@auth_router.post("/logout")
async def logout(
    _current_user: Annotated[str, Depends(get_current_user)],
):
    """Выход из системы (простое удаление токена на клиенте)"""
    return {"message": "Successfully logged out"}


@auth_router.get("/me")
async def get_current_user_info(
    current_user: Annotated[str, Depends(get_current_user)],
):
    """Получить информацию о текущем пользователе"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "middle_name": current_user.middle_name,
        "last_name": current_user.last_name,
    }
