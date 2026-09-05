from __future__ import annotations

from src.repository.audit_repository import AuditRepository
from src.repository.ideas_repository import IdeaRepository
from src.repository.project_repository import ProjectRepository
from src.repository.role_repository import RoleRepository
from src.repository.session_repository import SessionRepository
from src.repository.user_repository import UserRepository
from src.repository.workspace_repository import WorkSpaceRepository
from src.schema.admin import (
    AdminAuditItem,
    AdminAuditListResponse,
    AdminOverview,
    AdminSessionItem,
    AdminSessionsResponse,
    AdminSessionStats,
)


class AdminService:
    """Сервис админ-панели: обзор, сессии и аудит всей системы"""

    def __init__(
        self,
        user_repository: UserRepository,
        role_repository: RoleRepository,
        idea_repository: IdeaRepository,
        project_repository: ProjectRepository,
        workspace_repository: WorkSpaceRepository,
        session_repository: SessionRepository,
        audit_repository: AuditRepository,
    ) -> None:
        self._user_repository = user_repository
        self._role_repository = role_repository
        self._idea_repository = idea_repository
        self._project_repository = project_repository
        self._workspace_repository = workspace_repository
        self._session_repository = session_repository
        self._audit_repository = audit_repository

    @staticmethod
    def _user_name(user) -> str:
        """Собрать ФИО пользователя для отображения в админ-панели"""

        if user is None:
            return ""
        return f"{user.first_name} {user.last_name or ''}".strip()

    def _to_session_item(self, session) -> AdminSessionItem:
        return AdminSessionItem(
            id=session.id,
            user_id=session.user_id,
            user_name=self._user_name(getattr(session, "user", None)),
            user_email=getattr(getattr(session, "user", None), "email", None),
            device_name=session.device_name,
            browser_name=session.browser_name,
            browser_version=session.browser_version,
            operating_system=session.operating_system,
            device_type=session.device_type,
            ip_address=session.ip_address,
            is_active=session.is_active,
            is_current=session.is_current,
            created_at=session.created_at,
            last_activity=session.last_activity,
            expires_at=session.expires_at,
        )

    def _to_audit_item(self, log) -> AdminAuditItem:
        return AdminAuditItem(
            id=log.id,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            action=log.action,
            old_values=log.old_values,
            new_values=log.new_values,
            performed_by=log.performed_by,
            performed_at=log.performed_at,
            user_name=self._user_name(getattr(log, "user", None)),
            user_email=getattr(getattr(log, "user", None), "email", None),
        )

    async def get_overview(self, activity_limit: int = 10) -> AdminOverview:
        """Обзорная статистика системы + последние действия"""

        logs = await self._audit_repository.get_all_logs(0, activity_limit)
        return AdminOverview(
            total_users=await self._user_repository.count(),
            total_roles=await self._role_repository.count(),
            total_ideas=await self._idea_repository.count(),
            total_projects=await self._project_repository.count(),
            total_workspaces=await self._workspace_repository.count(),
            total_sessions=await self._session_repository.count_all(),
            active_sessions=await self._session_repository.count_active_all(),
            active_users=await self._session_repository.count_active_users(),
            recent_activity=[self._to_audit_item(log) for log in logs],
        )

    async def get_all_sessions(
        self, page: int = 1, limit: int = 20, only_active: bool = False
    ) -> AdminSessionsResponse:
        """Список сессий всех пользователей с пагинацией"""

        skip = (page - 1) * limit
        sessions = await self._session_repository.get_all(skip=skip, limit=limit, only_active=only_active)
        total = (
            await self._session_repository.count_active_all()
            if only_active
            else await self._session_repository.count_all()
        )
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return AdminSessionsResponse(
            items=[self._to_session_item(session) for session in sessions],
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    async def get_session_stats(self) -> AdminSessionStats:
        """Статистика сессий по всей системе"""

        return AdminSessionStats(
            total_sessions=await self._session_repository.count_all(),
            active_sessions=await self._session_repository.count_active_all(),
            expired_sessions=await self._session_repository.count_expired_all(),
            active_users=await self._session_repository.count_active_users(),
        )

    async def get_all_audit_logs(self, page: int = 1, limit: int = 20) -> AdminAuditListResponse:
        """Audit логи всех пользователей с пагинацией"""

        skip = (page - 1) * limit
        logs = await self._audit_repository.get_all_logs(skip=skip, limit=limit)
        total = await self._audit_repository.count_all()
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return AdminAuditListResponse(
            items=[self._to_audit_item(log) for log in logs],
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )
