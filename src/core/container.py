from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends

from src.core.uow import IUnitOfWork, SqlAlchemyUoW
from src.repository.project_repository import ProjectRepository
from src.repository.resume_repository import ResumeRepository
from src.repository.user_repository import UserRepository
from src.services.auth_service import AuthService
from src.services.project_service import ProjectService
from src.services.resume_service import ResumeService
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


# Service
async def get_auth_service(user_repository: UserRepository = Depends(get_user_repository)) -> AuthService:
    return AuthService(user_repository)


async def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserService:
    return UserService(user_repository, auth_service)


async def get_resume_service(resume_repository: ResumeRepository = Depends(get_resume_repository)) -> ResumeService:
    return ResumeService(resume_repository)


async def get_project_service(
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> ProjectService:
    return ProjectService(project_repository)
