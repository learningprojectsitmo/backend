from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request

from src.core.audit_context import set_audit_context
from src.core.container import get_auth_service, get_exam_csv_uow_factory
from src.core.security import oauth2_scheme
from src.core.uow import IUnitOfWork
from src.model.user import User
from src.repository.password_reset_repository import PasswordResetRepository
from src.repository.role_repository import RolePermissionRepository
from src.repository.session_repository import SessionRepository
from src.repository.user_repository import UserPermissionRepository, UserRepository
from src.services.session_service import SessionService


async def get_exam_csv_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    uow_factory: Callable[[], IUnitOfWork] = Depends(get_exam_csv_uow_factory),
) -> User:
    """Use standard token validation, closing its DB resources before the export starts."""
    async with uow_factory() as uow:
        auth = await get_auth_service(
            UserRepository(uow),
            SessionService(SessionRepository(uow)),
            PasswordResetRepository(uow),
            UserPermissionRepository(uow),
            RolePermissionRepository(uow),
        )
        user = await auth.get_current_user(token)
    set_audit_context(user.id, request.client.host if request.client else None, request.headers.get("user-agent"))
    return user
