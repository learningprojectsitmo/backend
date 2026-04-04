from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends

from src.core.uow import IUnitOfWork, SqlAlchemyUoW
from src.repository.audit_repository import AuditRepository
from src.repository.kanban_repository import KanbanColumnRepository, KanbanSubtaskRepository, KanbanTaskRepository
from src.repository.password_reset_repository import PasswordResetRepository
from src.repository.permission_repository import PermissionRepository
from src.repository.project_repository import ProjectRepository
from src.repository.resume_repository import ResumeRepository
from src.repository.role_repository import RolePermissionRepository, RoleRepository
from src.repository.session_repository import SessionRepository
from src.repository.user_repository import UserPermissionRepository, UserRepository
from src.services.audit_service import AuditService
from src.services.auth_service import AuthService
from src.services.fixtures_service import FixtureService
from src.services.kanban_service import KanbanService
from src.services.permission_service import PermissionService
from src.services.project_service import ProjectService
from src.services.resume_service import ResumeService
from src.services.role_service import RoleService
from src.services.session_service import SessionService
from src.services.user_service import UserService


async def get_uow() -> AsyncGenerator[IUnitOfWork, None]:
    async with SqlAlchemyUoW() as uow:
        yield uow


# ========== Репозитории ==========


async def get_project_repository(uow: IUnitOfWork = Depends(get_uow)) -> ProjectRepository:
    return ProjectRepository(uow)


async def get_role_repository(uow: IUnitOfWork = Depends(get_uow)) -> RoleRepository:
    return RoleRepository(uow)


async def get_permission_repository(uow: IUnitOfWork = Depends(get_uow)) -> PermissionRepository:
    return PermissionRepository(uow)


async def get_role_permission_repository(uow: IUnitOfWork = Depends(get_uow)) -> RolePermissionRepository:
    return RolePermissionRepository(uow)


async def get_resume_repository(uow: IUnitOfWork = Depends(get_uow)) -> ResumeRepository:
    return ResumeRepository(uow)


async def get_user_repository(uow: IUnitOfWork = Depends(get_uow)) -> UserRepository:
    return UserRepository(uow)


async def get_user_permission_repository(uow: IUnitOfWork = Depends(get_uow)) -> UserPermissionRepository:
    return UserPermissionRepository(uow)


async def get_session_repository(uow: IUnitOfWork = Depends(get_uow)) -> SessionRepository:
    return SessionRepository(uow)


async def get_audit_repository(uow: IUnitOfWork = Depends(get_uow)) -> AuditRepository:
    return AuditRepository(uow)


async def get_password_reset_repository(uow: IUnitOfWork = Depends(get_uow)) -> PasswordResetRepository:
    return PasswordResetRepository(uow)


async def get_kanban_column_repository(uow: IUnitOfWork = Depends(get_uow)) -> KanbanColumnRepository:
    return KanbanColumnRepository(uow)


async def get_kanban_task_repository(uow: IUnitOfWork = Depends(get_uow)) -> KanbanTaskRepository:
    return KanbanTaskRepository(uow)


async def get_kanban_subtask_repository(uow: IUnitOfWork = Depends(get_uow)) -> KanbanSubtaskRepository:
    return KanbanSubtaskRepository(uow)


# ========== Сервисы ==========


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
    user_permission_repository: UserPermissionRepository = Depends(get_user_permission_repository),
    role_permission_repository: RolePermissionRepository = Depends(get_role_permission_repository),
) -> AuthService:
    return AuthService(
        user_repository,
        session_service,
        password_reset_repository,
        user_permission_repository,
        role_permission_repository,
    )


async def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
    auth_service: AuthService = Depends(get_auth_service),
    user_permission_repository: UserPermissionRepository = Depends(get_user_permission_repository),
    permission_repository: PermissionRepository = Depends(get_permission_repository),
) -> UserService:
    return UserService(
        user_repository, auth_service, user_permission_repository, permission_repository=permission_repository
    )


async def get_role_service(
    role_repository: RoleRepository = Depends(get_role_repository),
    role_permission_repository: RolePermissionRepository = Depends(get_role_permission_repository),
    permission_repository: PermissionRepository = Depends(get_permission_repository),
) -> RoleService:
    return RoleService(role_repository, role_permission_repository, permission_repository)


async def get_permission_service(
    permission_repository: PermissionRepository = Depends(get_permission_repository),
) -> PermissionService:
    return PermissionService(permission_repository)


async def get_fixtures_service(
    permission_service: PermissionService = Depends(get_permission_service),
    role_service: RoleService = Depends(get_role_service),
    permission_repository: PermissionRepository = Depends(get_permission_repository),
    user_service: UserService = Depends(get_user_service),
) -> FixtureService:
    return FixtureService(permission_service, role_service, permission_repository, user_service)


async def get_audit_service(
    audit_repository: AuditRepository = Depends(get_audit_repository),
) -> AuditService:
    return AuditService(audit_repository)


async def get_kanban_service(
    kanban_column_repository: KanbanColumnRepository = Depends(get_kanban_column_repository),
    kanban_task_repository: KanbanTaskRepository = Depends(get_kanban_task_repository),
    kanban_subtask_repository: KanbanSubtaskRepository = Depends(get_kanban_subtask_repository),
    user_repository: UserRepository = Depends(get_user_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> KanbanService:
    return KanbanService(
        kanban_column_repository, kanban_task_repository, kanban_subtask_repository, user_repository, project_repository
    )
