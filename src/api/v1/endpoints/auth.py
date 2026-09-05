from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from src.core.container import get_auth_service, get_user_service
from src.core.dependencies import get_current_user
from src.core.logging_config import api_logger
from src.model.user import User
from src.schema.auth import (
    PasswordResetConfirm,
    PasswordResetEmailResponse,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetSuccessfulResponse,
    RefreshRequest,
    Token,
)
from src.schema.user import NewUserResponse, SignupRequest
from src.services.auth_service import AuthService
from src.services.user_service import UserService

REFRESH_COOKIE_KEY = "refresh_token"
REFRESH_COOKIE_PATH = "/v1/auth"


def _set_refresh_cookie(response: Response, raw_refresh: str, max_age: int) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_KEY,
        value=raw_refresh,
        httponly=True,
        secure=False,  # True в production с HTTPS
        samesite="lax",
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_KEY, path=REFRESH_COOKIE_PATH)


auth_router = APIRouter(prefix="/auth", tags=["authentication"])


# ───────── login ─────────


@auth_router.post("/login", response_model=Token)
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    remember_me: bool = Form(default=True),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Вход в систему. Access token в JSON, refresh token в HttpOnly cookie."""
    client_ip = request.client.host if request.client else "unknown"

    try:
        token, raw_refresh = await auth_service.login_for_access_token(
            email=form_data.username,
            password=form_data.password,
            remember_me=remember_me,
            request=request,
        )

        max_age = 30 * 86400 if remember_me else 86400
        response = Response(
            content=token.model_dump_json(),
            media_type="application/json",
            status_code=200,
        )
        _set_refresh_cookie(response, raw_refresh, max_age)

    except Exception as e:
        api_logger.log_error(method="POST", path="/auth/login", error=e, user_id=None)
        raise
    else:
        api_logger.log_request(
            method="POST",
            path="/auth/login",
            user_id=None,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
        )
        return response


# ───────── /token shim for Swagger Authorize ─────────


@auth_router.post("/token", response_model=Token, include_in_schema=False)
async def token_for_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """OAuth2-compliant endpoint for Swagger Authorize button only"""
    token, raw_refresh = await auth_service.login_for_access_token(
        email=form_data.username,
        password=form_data.password,
        remember_me=True,
    )
    max_age = 30 * 86400
    response = Response(
        content=token.model_dump_json(),
        media_type="application/json",
        status_code=200,
    )
    _set_refresh_cookie(response, raw_refresh, max_age)
    return response


# ───────── refresh ─────────


@auth_router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    data: RefreshRequest | None = None,
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Обновить access-токен.

    Refresh-токен читается из:
    1. HttpOnly cookie `refresh_token` (автоматически браузером)
    2. JSON body `refresh_token` (для мобильных/Swagger)
    """
    client_ip = request.client.host if request.client else "unknown"
    raw_refresh = data.refresh_token if data else None
    if not raw_refresh:
        raw_refresh = request.cookies.get(REFRESH_COOKIE_KEY)

    if not raw_refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")

    try:
        token, new_raw, max_age = await auth_service.refresh_access_token(raw_refresh)

        response = Response(
            content=token.model_dump_json(),
            media_type="application/json",
            status_code=200,
        )
        _set_refresh_cookie(response, new_raw, max_age)

    except Exception as e:
        api_logger.log_error(method="POST", path="/auth/refresh", error=e, user_id=None)
        raise
    else:
        api_logger.log_request(
            method="POST",
            path="/auth/refresh",
            user_id=None,
            ip_address=client_ip,
            status_code=200,
            response_time=0.0,
        )
        return response


# ───────── signup with email ─────────

router = APIRouter(prefix="/signup", tags=["signup"])


@router.post("/request", response_model=NewUserResponse, status_code=status.HTTP_201_CREATED)
async def create_signup_request(
    user_data: SignupRequest,
    user_service: UserService = Depends(get_user_service),
) -> NewUserResponse:
    """Создать запрос на регистрацию и отправить код подтверждения"""

    newuser_id = await user_service.request_signup(user_data)
    return NewUserResponse(id=newuser_id, email=user_data.email)


@router.post("/{newuser_id}/resend-code", response_model=NewUserResponse)
async def resend_signup_code(
    newuser_id: int,
    user_service: UserService = Depends(get_user_service),
) -> NewUserResponse:
    """Отправить новый код подтверждения"""

    newuser_id = await user_service.resend_signup_code(newuser_id)
    return NewUserResponse(id=newuser_id, email="")


@router.post("/{newuser_id}/verify", response_model=Token)
async def verify_signup_code(
    newuser_id: int,
    code: int,
    request: Request,
    user_service: UserService = Depends(get_user_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Подтвердить регистрацию кодом и выполнить авто-вход (выдать токены)."""

    user = await user_service.confirm_signup(newuser_id, code)

    token, raw_refresh = await auth_service.create_session_and_tokens(user=user, request=request)
    max_age = 30 * 86400

    response = Response(
        content=token.model_dump_json(),
        media_type="application/json",
        status_code=200,
    )
    _set_refresh_cookie(response, raw_refresh, max_age)
    return response


# ───────── logout ─────────


@auth_router.post("/logout")
async def logout(
    request: Request,
    _current_user: Annotated[User, Depends(get_current_user)],
    auth_service: AuthService = Depends(get_auth_service),
) -> Response:
    """Выход из системы — завершает сессию и очищает refresh cookie."""
    client_ip = request.client.host if request.client else "unknown"

    raw_refresh = request.cookies.get(REFRESH_COOKIE_KEY)
    if raw_refresh:
        await auth_service.logout_by_refresh_token(raw_refresh)

    api_logger.log_request(
        method="POST",
        path="/auth/logout",
        user_id=None,
        ip_address=client_ip,
        status_code=200,
        response_time=0.0,
    )

    response = Response(
        content='{"message": "Successfully logged out"}',
        media_type="application/json",
        status_code=200,
    )
    _clear_refresh_cookie(response)
    return response


# ───────── me ─────────


@auth_router.get("/me")
async def get_current_user_info(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, object]:
    """Получить информацию о текущем пользователе.
    Принимает access token в Authorization: Bearer, либо refresh_token в cookie.
    При аутентификации через refresh_token возвращает новый access_token.
    """
    client_ip = request.client.host if request.client else "unknown"
    from_refresh = False

    # Пробуем access token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ")
        current_user = await auth_service.get_current_user(token)
    else:
        # Пробуем refresh token из cookie
        raw_refresh = request.cookies.get(REFRESH_COOKIE_KEY)
        if not raw_refresh:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        current_user = await auth_service.get_user_by_refresh_token(raw_refresh)
        from_refresh = True

    permissions = await auth_service.get_all_user_permissions(current_user)

    api_logger.log_request(
        method="GET",
        path="/auth/me",
        user_id=current_user.id,
        ip_address=client_ip,
        status_code=200,
        response_time=0.0,
    )

    result: dict[str, object] = {
        "id": current_user.id,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "middle_name": current_user.middle_name,
        "last_name": current_user.last_name,
        "tg_nickname": current_user.tg_nickname,
        "vk_nickname": current_user.vk_nickname,
        "show_my_contacts": current_user.show_my_contacts,
        "permissions": permissions,
    }

    if from_refresh:
        access_token = auth_service.create_access_token(data={"sub": current_user.email, "user_id": current_user.id})
        result["access_token"] = access_token

    return result


# ───────── password reset ─────────


@auth_router.post("/password-reset/request", response_model=PasswordResetResponse)
async def request_password_reset(
    data: PasswordResetRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> PasswordResetResponse:
    await auth_service.request_password_reset(data.email)
    return PasswordResetResponse()


@auth_router.get("/password-reset/validate", response_model=PasswordResetEmailResponse)
async def validate_password_reset_token(
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service),
) -> PasswordResetEmailResponse:
    email = await auth_service.get_reset_email_by_token(token)
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
    return PasswordResetEmailResponse(email=email)


@auth_router.post("/password-reset/confirm", response_model=PasswordResetSuccessfulResponse)
async def confirm_password_reset(
    data: PasswordResetConfirm,
    auth_service: AuthService = Depends(get_auth_service),
) -> PasswordResetSuccessfulResponse:
    sucess = await auth_service.confirm_password_reset(data.token, data.new_password)
    if not sucess:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
    return PasswordResetSuccessfulResponse()
