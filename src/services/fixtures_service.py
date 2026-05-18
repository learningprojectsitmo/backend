from __future__ import annotations

from sqlalchemy import select

from src.model.workspace import WorkSpace, WorkSpaceCategories, WorkSpaceStatus
from src.schema.permission import PermissionMatrix
from src.schema.user import UserCreate
from src.schema.workspace import WorkSpaceCreate
from src.services.permission_service import PermissionService
from src.services.role_service import RoleService
from src.services.user_service import UserService
from src.services.workspace_service import WorkSpaceService


class FixtureService:
    """Сервис для создания тестовых данных (фикстур)"""

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

    async def create_fixtures(self) -> None:
        """Создаёт базовые фикстуры: permissions, roles, users, workspaces"""
        # 1. Создаём permissions (get_or_create предотвращает дубликаты)
        permissions = [
            "project:create",
            "project:read",
            "project:update",
            "project:delete",
            "resume:create",
            "resume:read",
            "resume:update",
            "resume:delete",
            "user:read",
            "user:update",
        ]

        created_permissions = {}
        for perm_name in permissions:
            perm, _ = await self._permission_service.get_or_create({"name": perm_name})
            created_permissions[perm_name] = perm

        # Явный commit для гарантированного сохранения permissions в БД
        await self._permission_service._repository.uow.commit()

        # 2. Создаём roles (get_or_create предотвращает дубликаты)
        await self._role_service.get_or_create({"name": "admin"})
        await self._role_service.get_or_create({"name": "member"})

        # Явный commit для гарантированного сохранения ролей в БД
        await self._role_service._repository.uow.commit()

        # Пере-получаем роли из БД, чтобы получить актуальные ID из новой сессии
        role_admin = await self._role_service._repository.get_by_name("admin")
        role_member = await self._role_service._repository.get_by_name("member")

        # 3. Настраиваем permissions для roles
        admin_matrix = {
            "project": {"create": True, "read": True, "update": True, "delete": True},
            "resume": {"create": True, "read": True, "update": True, "delete": True},
            "user": {"create": False, "read": True, "update": True, "delete": True},
        }
        member_matrix = {
            "project": {"create": True, "read": True, "update": True, "delete": False},
            "resume": {"create": True, "read": True, "update": True, "delete": False},
            "user": {"create": False, "read": True, "update": False, "delete": False},
        }

        await self._role_service.remap_role_permission(role_admin.id, PermissionMatrix(permissions_matrix=admin_matrix))
        await self._role_service.remap_role_permission(
            role_member.id, PermissionMatrix(permissions_matrix=member_matrix)
        )

        # 4. Создаём тестовых пользователей (проверяем существование по email)
        admin_email = "admin@example.com"
        member_email = "member@example.com"

        # Проверяем существование пользователей
        existing_admin = await self._user_service.get_user_by_email(admin_email)
        existing_member = await self._user_service.get_user_by_email(member_email)

        if not existing_admin:
            user_admin_data = UserCreate(
                email=admin_email,
                first_name="Admin",
                middle_name="",
                last_name="User",
                password="admin_password",
                role_id=role_admin.id,
            )
            existing_admin = await self._user_service.create(user_admin_data)

        if not existing_member:
            user_member_data = UserCreate(
                email=member_email,
                first_name="Member",
                middle_name="",
                last_name="User",
                password="member_password",
                role_id=role_member.id,
            )
            existing_member = await self._user_service.create(user_member_data)

        # 5. Создаём workspace_status (если их нет)

        statuses = [
            {"name": "active"},
            {"name": "archived"},
            {"name": "on_hold"},
        ]

        for status_data in statuses:
            result = await self._workspace_service._repository.uow.session.execute(
                select(WorkSpaceStatus).where(WorkSpaceStatus.name == status_data["name"])
            )
            existing_status = result.scalar_one_or_none()
            
            if not existing_status:
                self._workspace_service._repository.uow.session.add(
                    WorkSpaceStatus(**status_data)
                )

        await self._workspace_service._repository.uow.commit()

        # 5.1 Создаём workspace_categories (если их нет)
        categories = [
            {"name": "Общеуниверситетские проекты", "color": "#6366f1"},
            {"name": "Дисциплины", "color": "#10b981"},
        ]

        categories_by_name: dict[str, WorkSpaceCategories] = {}
        for category_data in categories:
            category = await self._workspace_service.get_or_create_category(category_data)
            categories_by_name[category.name] = category

        await self._workspace_service._repository.uow.commit()

        # 6. Создаём тестовые workspace (проверяем существование по имени)
        admin_workspaces = [
            ("Admin Workspace 1", "Общеуниверситетские проекты"),
            ("Admin Workspace 2", "Дисциплины"),
        ]

        for ws_name, category_name in admin_workspaces:
            existing_workspace_result = await self._workspace_service._repository.uow.session.execute(
                select(WorkSpace).where(WorkSpace.name == ws_name)
            )
            existing_workspace = existing_workspace_result.scalar_one_or_none()

            if not existing_workspace:
                category = categories_by_name.get(category_name)
                workspace_data = WorkSpaceCreate(
                    name=ws_name,
                    author_id=existing_admin.id,
                    status_id=1,
                    category_id=category.id if category else None,
                )
                await self._workspace_service.create_workspace(workspace_data, existing_admin.id)
