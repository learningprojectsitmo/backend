from dependency_injector import containers, providers
from sqlalchemy.orm import Session

from core.config import settings
from core.database import Database
from repository.project_repository import ProjectRepository
from repository.resume_repository import ResumeRepository
from repository.user_repository import UserRepository
from services.auth_service import AuthService
from services.project_service import ProjectService
from services.resume_service import ResumeService
from services.user_service import UserService


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

    # Database singleton
    db = providers.Singleton(Database, db_url=settings.DATABASE_URL)

    # Database session provider
    session = providers.Factory(Session, db.provided.session)

    # Repositories
    user_repository = providers.Factory(UserRepository, session_factory=db.provided.session)

    project_repository = providers.Factory(
        ProjectRepository, session_factory=db.provided.session
    )

    resume_repository = providers.Factory(
        ResumeRepository,
        session_factory=db.provided.session
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
