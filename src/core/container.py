from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.core.config import settings
from src.repository.user_repository import UserRepository
from src.repository.project_repository import ProjectRepository
from src.repository.resume_repository import ResumeRepository
from src.services.auth_service import AuthService
from src.services.user_service import UserService
from src.services.project_service import ProjectService
from src.services.resume_service import ResumeService


class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        modules=[
            "api.v1.endpoints.auth",
            "api.v1.endpoints.user",
            "api.v1.endpoints.project",
            "api.v1.endpoints.resume",
            "core.dependencies",
        ]
    )

    # Database configuration for async operations
    engine = providers.Singleton(create_async_engine,settings.DATABASE_URL, echo=settings.DEBUG)

    # Async session factory
    async_session_factory = providers.Singleton(        sessionmaker,         bind=engine.provided,        class_=AsyncSession,        expire_on_commit=False
    )

    # Database session provider (async)
    session = providers.Factory(        AsyncSession,        bind=engine.provided    )

    # Repositories
    user_repository = providers.Factory(        UserRepository,         session_factory=async_session_factory    )

    project_repository = providers.Factory(
        ProjectRepository, 
        session_factory=async_session_factory
    )

    resume_repository = providers.Factory(
        ResumeRepository,
        session_factory=async_session_factory
    )

    # Services
    auth_service = providers.Factory(
        AuthService,
        user_repository=user_repository,
        db_session=session
    )

    user_service = providers.Factory(
        UserService,
        user_repository=user_repository,
        db_session=session
    )

    project_service = providers.Factory(
        ProjectService,
        project_repository=project_repository,
        db_session=session
    )

    resume_service = providers.Factory(
        ResumeService,
        resume_repository=resume_repository,
        db_session=session
    )