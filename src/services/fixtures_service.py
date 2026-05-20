from __future__ import annotations

from sqlalchemy import select

from src.model.project import Project, ProjectStatus
from src.model.workspace import WorkSpace, WorkSpaceCategories, WorkSpaceStatus
from src.repository.project_repository import ProjectRepository
from src.schema.permission import PermissionMatrix
from src.schema.project import ProjectCreate
from src.schema.user import UserCreate
from src.schema.workspace import WorkSpaceCreate
from src.services.permission_service import PermissionService
from src.services.project_service import ProjectService
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
        project_service: ProjectService,
        project_repository: ProjectRepository,
    ) -> None:
        self._permission_service = permission_service
        self._role_service = role_service
        self._user_service = user_service
        self._workspace_service = workspace_service
        self._project_service = project_service
        self._project_repository = project_repository

    # ─── main entry ────────────────────────────────────────────────────────

    async def create_fixtures(self) -> None:
        await self._seed_permissions()
        await self._seed_roles()
        admin, member = await self._seed_users()
        await self._seed_workspace_statuses()
        categories_by_name = await self._seed_workspace_categories()
        workspaces_by_name = await self._seed_workspaces(admin, categories_by_name)
        await self._seed_projects(admin, workspaces_by_name)

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
            "user:read",
            "user:update",
        ]
        perm_repo = self._permission_service._repository
        for perm_name in permissions:
            await self._permission_service.get_or_create({"name": perm_name})
        await perm_repo.uow.commit()

    # ─── roles ─────────────────────────────────────────────────────────────

    async def _seed_roles(self) -> None:
        role_repo = self._role_service._repository

        await self._role_service.get_or_create({"name": "admin"})
        await self._role_service.get_or_create({"name": "member"})
        await role_repo.uow.commit()

        role_admin = await role_repo.get_by_name("admin")
        role_member = await role_repo.get_by_name("member")

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

    # ─── users ─────────────────────────────────────────────────────────────

    async def _seed_users(self) -> tuple:
        admin_email = "admin@example.com"
        member_email = "member@example.com"

        role_repo = self._role_service._repository
        role_admin = await role_repo.get_by_name("admin")
        role_member = await role_repo.get_by_name("member")

        existing_admin = await self._user_service.get_user_by_email(admin_email)
        existing_member = await self._user_service.get_user_by_email(member_email)

        if not existing_admin:
            existing_admin = await self._user_service.create(
                UserCreate(
                    email=admin_email,
                    first_name="Admin",
                    middle_name="",
                    last_name="User",
                    password="admin_password",
                    role_id=role_admin.id,
                )
            )

        if not existing_member:
            existing_member = await self._user_service.create(
                UserCreate(
                    email=member_email,
                    first_name="Member",
                    middle_name="",
                    last_name="User",
                    password="member_password",
                    role_id=role_member.id,
                )
            )

        return existing_admin, existing_member

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

    async def _seed_workspace_categories(self) -> dict[str, WorkSpaceCategories]:
        categories_data = [
            {"name": "Общеуниверситетские проекты", "color": "#6366f1"},
            {"name": "Дисциплины", "color": "#10b981"},
        ]

        categories_by_name = {}
        for cat_data in categories_data:
            category = await self._workspace_service.get_or_create_category(cat_data)
            categories_by_name[category.name] = category

        await self._workspace_service._repository.uow.commit()
        return categories_by_name

    # ─── workspaces ────────────────────────────────────────────────────────

    async def _seed_workspaces(
        self,
        admin: object,
        categories_by_name: dict[str, WorkSpaceCategories],
    ) -> dict[str, WorkSpace]:
        repo = self._workspace_service._repository
        workspaces_data = [
            ("Admin Workspace 1", "Общеуниверситетские проекты", "#6366f1"),
            ("Admin Workspace 2", "Дисциплины", "#10b981"),
        ]

        workspaces_by_name = {}
        for ws_name, category_name, ws_color in workspaces_data:
            result = await repo.uow.session.execute(
                select(WorkSpace).where(WorkSpace.name == ws_name)
            )
            existing = result.scalar_one_or_none()

            if not existing:
                category = categories_by_name.get(category_name)
                workspace_data = WorkSpaceCreate(
                    name=ws_name,
                    author_id=admin.id,
                    status_id=1,
                    category_id=category.id if category else None,
                    color=ws_color,
                )
                # Используем репозиторий напрямую (простое создание без бизнес-логики)
                existing = await repo.create(workspace_data)

            workspaces_by_name[ws_name] = existing

        return workspaces_by_name

    # ─── projects ──────────────────────────────────────────────────────────

    async def _seed_projects(
        self,
        admin: object,
        workspaces_by_name: dict[str, WorkSpace],
    ) -> None:
        ws1 = workspaces_by_name.get("Admin Workspace 1")
        ws2 = workspaces_by_name.get("Admin Workspace 2")

        # id=1 → planned, id=2 → in_progress, id=3 → completed, id=4 → review
        projects_data = [
            {
                "name": "Tasker — платформа управления задачами",
                "description": (
                    "Tasker — учебный проект по разработке веб-сервиса для управления "
                    "задачами и проектами. Сервис предназначен для планирования задач, "
                    "распределения ролей в команде, работы с дедлайнами и отслеживания "
                    "прогресса выполнения проекта."
                ),
                "workspace": ws1,
                "status_id": 2,
                "progress": 75,
                "tags": ["Frontend", "AI/ML", "Design"],
            },
            {
                "name": "Веб-сервис для студентов",
                "description": "Платформа для организации учебного процесса и взаимодействия студентов и преподавателей",
                "workspace": ws1,
                "status_id": 4,
                "progress": 45,
                "tags": ["Mobile", "iOS", "Android"],
            },
            {
                "name": "AI Learning Platform",
                "description": "Разработка цифровой платформы с искусственным интеллектом для персонализированного обучения",
                "workspace": ws2,
                "status_id": 2,
                "progress": 30,
                "tags": ["Design", "UI/UX"],
            },
            {
                "name": "Мобильное приложение",
                "description": "Разработка iOS и Android приложений для доступа к образовательным материалам",
                "workspace": ws2,
                "status_id": 1,
                "progress": 10,
                "tags": ["Mobile", "Frontend"],
            },
        ]

        for data in projects_data:
            # Проверяем существование проекта по имени через репозиторий
            result = await self._project_repository.uow.session.execute(
                select(Project).where(Project.name == data["name"])
            )
            if result.scalar_one_or_none():
                continue

            ws = data["workspace"]
            project_data = ProjectCreate(
                name=data["name"],
                description=data["description"],
                status_id=data["status_id"],
                progress=data["progress"],
                tags=data["tags"],
                author_id=admin.id,
                workspace_id=ws.id,
            )

            # Используем сервис — он сам разберётся с тегами и связями
            await self._project_service.create_project(project_data, admin.id)
