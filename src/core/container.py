from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends

from src.core.uow import IUnitOfWork, SqlAlchemyUoW
from src.repository.audit_repository import AuditRepository
from src.repository.password_reset_repository import PasswordResetRepository
from src.repository.project_repository import ProjectRepository
from src.repository.resume_repository import ResumeRepository
from src.repository.session_repository import SessionRepository
from src.repository.user_repository import UserRepository
from src.services.audit_service import AuditService
from src.services.auth_service import AuthService
from src.services.project_service import ProjectService
from src.services.resume_service import ResumeService
from src.services.session_service import SessionService
from src.services.user_service import UserService


async def get_uow() -> AsyncGenerator[IUnitOfWork, None]:
    async with SqlAlchemyUoW() as uow:
        yield uow


# Repository
async def get_project_repository(uow: IUnitOfWork = Depends(get_uow)) -> ProjectRepository:
    return ProjectRepository(uow)


async def get_resume_repository(uow: IUnitOfWork = Depends(get_uow)) -> ResumeRepository:
    return ResumeRepository(uow)


async def get_user_repository(uow: IUnitOfWork = Depends(get_uow)) -> UserRepository:
    return UserRepository(uow)


async def get_session_repository(uow: IUnitOfWork = Depends(get_uow)) -> SessionRepository:
    return SessionRepository(uow)


async def get_audit_repository(uow: IUnitOfWork = Depends(get_uow)) -> AuditRepository:
    return AuditRepository(uow)


async def get_password_reset_repository(uow: IUnitOfWork = Depends(get_uow)) -> PasswordResetRepository:
    return PasswordResetRepository(uow)


# Service
async def get_session_service(
    session_repository: SessionRepository = Depends(get_session_repository),
) -> SessionService:
    return SessionService(session_repository)


async def get_resume_service(resume_repository: ResumeRepository = Depends(get_resume_repository)) -> ResumeService:
    return ResumeService(resume_repository)


async def get_project_service(
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> ProjectService:
    return ProjectService(project_repository)


async def get_auth_service(
    user_repository: UserRepository = Depends(get_user_repository),
    session_service: SessionService = Depends(get_session_service),
    password_reset_repository: PasswordResetRepository = Depends(get_password_reset_repository),
) -> AuthService:
    return AuthService(user_repository, session_service, password_reset_repository)


async def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserService:
    return UserService(user_repository, auth_service)


async def get_audit_service(
    audit_repository: AuditRepository = Depends(get_audit_repository),
) -> AuditService:
    return AuditService(audit_repository)
