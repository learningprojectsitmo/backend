from __future__ import annotations

from sqlalchemy import select

from src.model.workspace import WorkSpaceStatus
from src.schema.permission import PermissionMatrix
from src.schema.user import UserCreate
from src.services.permission_service import PermissionService
from src.services.role_service import RoleService
from src.services.user_service import UserService
from src.services.workspace_service import WorkSpaceService


class FixtureService:
    """Сервис для создания базовых (справочных) данных приложения и пользователя-администратора"""

    def __init__(
        self,
        permission_service: PermissionService,
        role_service: RoleService,
        user_service: UserService,
        workspace_service: WorkSpaceService,
    ) -> None:
        self._permission_service = permission_service
        self._role_service = role_service
        self._user_service = user_service
        self._workspace_service = workspace_service

    # ─── main entry ────────────────────────────────────────────────────────

    async def create_fixtures(self) -> None:
        await self._seed_permissions()
        await self._seed_roles()
        await self._seed_users()
        await self._seed_workspace_statuses()
        await self._seed_workspace_categories()

    # ─── permissions ───────────────────────────────────────────────────────

    async def _seed_permissions(self) -> None:
        permissions = [
            "project:create",
            "project:read",
            "project:update",
            "project:delete",
            "resume:create",
            "resume:read",
            "resume:update",
            "resume:delete",
            "user:create",
            "user:read",
            "user:update",
            "user:delete",
            "workspace:create",
            "workspace:read",
            "workspace:update",
            "workspace:delete",
            "settings:create",
            "settings:read",
            "settings:update",
            "settings:delete",
            "audit:create",
            "audit:read",
            "audit:update",
            "audit:delete",
            "ideas:create",
            "ideas:read",
            "ideas:update",
            "ideas:delete",
            "kanban:create",
            "kanban:read",
            "kanban:update",
            "kanban:delete",
            "notification:create",
            "notification:read",
            "notification:update",
            "notification:delete",
            "invitation:create",
            "invitation:read",
            "invitation:update",
            "invitation:delete",
            "session:create",
            "session:read",
            "session:update",
            "session:delete",
            "role:create",
            "role:read",
            "role:update",
            "role:delete",
            "perm:create",
            "perm:read",
            "perm:update",
            "perm:delete",
        ]
        perm_repo = self._permission_service._repository
        for perm_name in permissions:
            await self._permission_service.get_or_create({"name": perm_name})
        await perm_repo.uow.commit()

    # ─── roles ─────────────────────────────────────────────────────────────

    async def _seed_roles(self) -> None:
        role_repo = self._role_service._repository

        await self._role_service.get_or_create(
            {"name": "admin", "description": "Полный доступ ко всем функциям системы"}
        )
        await self._role_service.get_or_create({"name": "teacher", "description": "Создание и оценка заданий"})
        await self._role_service.get_or_create(
            {"name": "member", "description": "Доступ к проектам и учебным материалам"}
        )
        await self._role_service.get_or_create(
            {"name": "manager", "description": "Руководитель проекта: создаёт проекты и наполняет их данными"}
        )
        await role_repo.uow.commit()

        role_admin = await role_repo.get_by_name("admin")
        role_teacher = await role_repo.get_by_name("teacher")
        role_member = await role_repo.get_by_name("member")
        role_manager = await role_repo.get_by_name("manager")

        admin_matrix = {
            "project": {"create": True, "read": True, "update": True, "delete": True},
            "resume": {"create": True, "read": True, "update": True, "delete": True},
            "user": {"create": True, "read": True, "update": True, "delete": True},
            "workspace": {"create": True, "read": True, "update": True, "delete": True},
            "settings": {"create": True, "read": True, "update": True, "delete": True},
            "audit": {"create": True, "read": True, "update": True, "delete": True},
            "ideas": {"create": True, "read": True, "update": True, "delete": True},
            "kanban": {"create": True, "read": True, "update": True, "delete": True},
            "notification": {"create": True, "read": True, "update": True, "delete": True},
            "invitation": {"create": True, "read": True, "update": True, "delete": True},
            "session": {"create": True, "read": True, "update": True, "delete": True},
            "role": {"create": True, "read": True, "update": True, "delete": True},
            "perm": {"create": True, "read": True, "update": True, "delete": True},
        }
        teacher_matrix = {
            "project": {"create": True, "read": True, "update": True, "delete": True},
            "resume": {"create": True, "read": True, "update": True, "delete": True},
            "user": {"create": False, "read": True, "update": True, "delete": False},
            "workspace": {"create": True, "read": True, "update": True, "delete": True},
            "settings": {"create": False, "read": True, "update": False, "delete": False},
            "audit": {"create": False, "read": True, "update": False, "delete": False},
            "ideas": {"create": True, "read": True, "update": True, "delete": True},
            "kanban": {"create": True, "read": True, "update": True, "delete": True},
            "notification": {"create": True, "read": True, "update": True, "delete": True},
            "invitation": {"create": True, "read": True, "update": True, "delete": False},
            "session": {"create": True, "read": True, "update": True, "delete": False},
            "role": {"create": False, "read": True, "update": False, "delete": False},
            "perm": {"create": False, "read": False, "update": False, "delete": False},
        }
        member_matrix = {
            "project": {"create": True, "read": True, "update": True, "delete": True},
            "resume": {"create": True, "read": True, "update": True, "delete": True},
            "user": {"create": False, "read": True, "update": False, "delete": False},
            "workspace": {"create": False, "read": True, "update": False, "delete": False},
            "settings": {"create": False, "read": False, "update": False, "delete": False},
            "audit": {"create": False, "read": True, "update": False, "delete": False},
            "ideas": {"create": True, "read": True, "update": True, "delete": True},
            "kanban": {"create": True, "read": True, "update": True, "delete": True},
            "notification": {"create": True, "read": True, "update": True, "delete": False},
            "invitation": {"create": True, "read": True, "update": True, "delete": False},
            "session": {"create": False, "read": True, "update": True, "delete": False},
            "role": {"create": False, "read": True, "update": False, "delete": False},
            "perm": {"create": False, "read": False, "update": False, "delete": False},
        }
        manager_matrix = {
            "project": {"create": True, "read": True, "update": True, "delete": True},
            "resume": {"create": True, "read": True, "update": True, "delete": True},
            "user": {"create": False, "read": True, "update": True, "delete": False},
            "workspace": {"create": False, "read": True, "update": False, "delete": False},
            "settings": {"create": False, "read": True, "update": False, "delete": False},
            "audit": {"create": False, "read": True, "update": False, "delete": False},
            "ideas": {"create": True, "read": True, "update": True, "delete": True},
            "kanban": {"create": True, "read": True, "update": True, "delete": True},
            "notification": {"create": True, "read": True, "update": True, "delete": False},
            "invitation": {"create": True, "read": True, "update": True, "delete": False},
            "session": {"create": True, "read": True, "update": True, "delete": False},
            "role": {"create": False, "read": True, "update": False, "delete": False},
            "perm": {"create": False, "read": False, "update": False, "delete": False},
        }

        await self._role_service.remap_role_permission(role_admin.id, PermissionMatrix(permissions_matrix=admin_matrix))
        await self._role_service.remap_role_permission(
            role_teacher.id, PermissionMatrix(permissions_matrix=teacher_matrix)
        )
        await self._role_service.remap_role_permission(
            role_member.id, PermissionMatrix(permissions_matrix=member_matrix)
        )
        await self._role_service.remap_role_permission(
            role_manager.id, PermissionMatrix(permissions_matrix=manager_matrix)
        )

    # ─── admin user ────────────────────────────────────────────────────────

    async def _seed_users(self) -> None:
        role_repo = self._role_service._repository
        role_admin = await role_repo.get_by_name("admin")

        existing = await self._user_service.get_user_by_email("admin@example.com")
        if existing:
            return

        await self._user_service.create(
            UserCreate(
                email="admin@example.com",
                first_name="Admin",
                middle_name="",
                last_name="User",
                password="admin_password",
                role_id=role_admin.id,
                tg_nickname="@admin_tg",
                vk_nickname="@admin_vk",
                phone="+7 (999) 123-45-67",
            )
        )

    # ─── workspace statuses ────────────────────────────────────────────────

    async def _seed_workspace_statuses(self) -> None:
        repo = self._workspace_service._repository
        statuses = [
            {"name": "active"},
            {"name": "archived"},
            {"name": "on_hold"},
        ]

        for status_data in statuses:
            result = await repo.uow.session.execute(
                select(WorkSpaceStatus).where(WorkSpaceStatus.name == status_data["name"])
            )
            if not result.scalar_one_or_none():
                repo.uow.session.add(WorkSpaceStatus(**status_data))

        await repo.uow.commit()

    # ─── workspace categories ──────────────────────────────────────────────

    async def _seed_workspace_categories(self) -> None:
        categories_data = [
            {"name": "Дисциплины", "color": "#10b981"},
            {"name": "Общеуниверситетские проекты", "color": "#6366f1"},
        ]

        for cat_data in categories_data:
            await self._workspace_service.get_or_create_category(cat_data)

        await self._workspace_service._repository.uow.commit()
