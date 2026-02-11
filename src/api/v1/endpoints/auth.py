from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from src.core.container import get_auth_service
from src.core.dependencies import get_current_user
from src.core.logging_config import api_logger
from src.model.models import User
from src.schema.auth import (
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetSuccessfulResponse,
    Token,
)
from src.services.auth_service import AuthService

auth_router = APIRouter(prefix="/auth", tags=["authentication"])


@auth_router.post("/token", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(OAuth2PasswordRequestForm),
    auth_service: AuthService = Depends(get_auth_service),
) -> Token:
    """Вход в систему и получение токена доступа"""
    # Логируем начало запроса
    client_ip = request.client.host if request.client else "unknown"

    try:
        result = await auth_service.login_for_access_token(form_data, request)
        # Логируем успешный запрос
        api_logger.log_request(
            method="POST",
            path="/auth/token",
            user_id=None,  # Пользователь еще не аутентифицирован
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,  # Можно добавить измерение времени
        )
    except Exception as e:
        # Логируем ошибку
        api_logger.log_error(method="POST", path="/auth/token", error=e, user_id=None)
        raise
    else:
        return result


@auth_router.post("/logout")
async def logout(
    request: Request,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    """Выход из системы (простое удаление токена на клиенте)"""
    client_ip = request.client.host if request.client else "unknown"

    api_logger.log_request(
        method="POST",
        path="/auth/logout",
        user_id=None,  # Пользователь еще не определен из _current_user
        ip_address=client_ip,
        status_code=200,
        response_time=0.0,
    )

    return {"message": "Successfully logged out"}


@auth_router.get("/me")
async def get_current_user_info(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Получить информацию о текущем пользователе"""
    client_ip = request.client.host if request.client else "unknown"

    api_logger.log_request(
        method="GET", path="/auth/me", user_id=current_user.id, ip_address=client_ip, status_code=200, response_time=0.0
    )

    return {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "middle_name": current_user.middle_name,
        "last_name": current_user.last_name,
    }


@auth_router.post("/password-reset/request", response_model=PasswordResetResponse)
async def request_password_reset(
    data: PasswordResetRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> PasswordResetResponse:
    """Запрос на сброс пароля"""

    await auth_service.request_password_reset(data.email)

    return PasswordResetResponse()


@auth_router.post("/password-reset/confirm", response_model=PasswordResetSuccessfulResponse)
async def confirm_password_reset(
    data: PasswordResetConfirm,
    auth_service: AuthService = Depends(get_auth_service),
) -> PasswordResetConfirm:
    """Подтвердить сброс пароля"""
    sucess = await auth_service.confirm_password_reset(data.token, data.new_password)

    if not sucess:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
    return PasswordResetSuccessfulResponse()
