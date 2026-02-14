from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request

from core.container import get_auth_service
from src.core.audit_context import set_audit_context
from src.core.logging_config import get_logger
from src.core.security import oauth2_scheme

if TYPE_CHECKING:
    from src.model.models import User
    from src.services.auth_service import AuthService


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """Получить текущего пользователя с использованием AuthService (асинхронно)"""
    logger = get_logger(__name__)

    try:
        user = await auth_service.get_current_user(token)
    except HTTPException as e:
        logger.warning(f"Failed to get current user - Status: {e.status_code}, Detail: {e.detail}")
        raise
    else:
        logger.debug(f"Successfully retrieved current user: {user.email} (ID: {user.id})")
        return user


async def require_teacher(current_user: User = Depends(get_current_user)) -> User:
    """Проверить, что текущий пользователь — преподаватель."""
    if current_user.role != "teacher":
        raise HTTPException(
            status_code=403,
            detail="Only teachers can perform this action",
        )
    return current_user


async def get_current_user_no_exception(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> User | None:
    """Получить текущего пользователя без исключения (возвращает None если ошибка)"""
    logger = get_logger(__name__)

    try:
        user = await auth_service.get_current_user(token)
    except HTTPException as e:
        logger.debug(f"Failed to get current user (no exception) - Status: {e.status_code}")
        return None
    else:
        logger.debug(f"Successfully retrieved current user (no exception): {user.email} (ID: {user.id})")
        return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Получить текущего активного пользователя (для будущего использования)"""
    # В будущем здесь можно добавить проверку активности пользователя
    return current_user


async def get_current_super_user(current_user: User = Depends(get_current_user)) -> User:
    """Получить текущего супер-пользователя (для будущего использования)"""
    # В будущем здесь можно добавить проверку ролей
    return current_user


async def setup_audit(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Установить контекстных переменных для аудита пользователей"""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    user_id = current_user.id

    set_audit_context(user_id=user_id, ip_address=ip_address, user_agent=user_agent)
