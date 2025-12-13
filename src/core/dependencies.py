from __future__ import annotations

from typing import TYPE_CHECKING


from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from core.container import get_auth_service

if TYPE_CHECKING:
    from src.model.models import User
    from src.services.auth_service import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")



async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """Получить текущего пользователя с использованием AuthService (асинхронно)"""
    return await auth_service.get_current_user(token)



async def get_current_user_no_exception(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> User | None:
    """Получить текущего пользователя без исключения (возвращает None если ошибка)"""
    try:
        return await auth_service.get_current_user(token)
    except HTTPException:
        return None


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Получить текущего активного пользователя (для будущего использования)"""
    # В будущем здесь можно добавить проверку активности пользователя
    return current_user


async def get_current_super_user(current_user: User = Depends(get_current_user)) -> User:
    """Получить текущего супер-пользователя (для будущего использования)"""
    # В будущем здесь можно добавить проверку ролей
    return current_user
