from __future__ import annotations

from collections.abc import AsyncGenerator

from src.repository.grading_criteria_repository import GradingCriteriaRepository
from src.services.grading_criteria_service import GradingCriteriaService


from fastapi import Depends

from src.core.uow import IUnitOfWork, SqlAlchemyUoW
from src.repository.audit_repository import AuditRepository
from src.repository.project_repository import ProjectRepository
from src.repository.resume_repository import ResumeRepository
from src.repository.session_repository import SessionRepository
from src.repository.user_repository import UserRepository
from src.repository.defense_repository import (
    DefenseDayRepository,
    DefenseProjectTypeRepository,
    DefenseRegistrationRepository,
    DefenseSlotRepository,
)
from src.services.audit_service import AuditService
from src.services.auth_service import AuthService
from src.services.project_service import ProjectService
from src.services.resume_service import ResumeService
from src.services.session_service import SessionService
from src.services.user_service import UserService
from src.services.defense_service import DefenseService


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


async def get_defense_project_type_repository(uow: IUnitOfWork = Depends(get_uow)) -> DefenseProjectTypeRepository:
    return DefenseProjectTypeRepository(uow)


async def get_defense_day_repository(uow: IUnitOfWork = Depends(get_uow)) -> DefenseDayRepository:
    return DefenseDayRepository(uow)


async def get_defense_slot_repository(uow: IUnitOfWork = Depends(get_uow)) -> DefenseSlotRepository:
    return DefenseSlotRepository(uow)


async def get_defense_registration_repository(uow: IUnitOfWork = Depends(get_uow)) -> DefenseRegistrationRepository:
    return DefenseRegistrationRepository(uow)


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
) -> AuthService:
    return AuthService(user_repository, session_service)


async def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserService:
    return UserService(user_repository, auth_service)


async def get_audit_service(
    audit_repository: AuditRepository = Depends(get_audit_repository),
) -> AuditService:
    return AuditService(audit_repository)


async def get_defense_service(
    project_type_repository: DefenseProjectTypeRepository = Depends(get_defense_project_type_repository),
    day_repository: DefenseDayRepository = Depends(get_defense_day_repository),
    slot_repository: DefenseSlotRepository = Depends(get_defense_slot_repository),
    registration_repository: DefenseRegistrationRepository = Depends(get_defense_registration_repository),
) -> DefenseService:
    return DefenseService(project_type_repository, day_repository, slot_repository, registration_repository)


async def get_grading_criteria_repository(uow: IUnitOfWork = Depends(get_uow)) -> GradingCriteriaRepository:
    return GradingCriteriaRepository(uow)


async def get_grading_criteria_service(
    grading_criteria_repository: GradingCriteriaRepository = Depends(get_grading_criteria_repository),
) -> GradingCriteriaService:
    return GradingCriteriaService(grading_criteria_repository)

