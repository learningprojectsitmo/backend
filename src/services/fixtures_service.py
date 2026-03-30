from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from src.core.logging_config import get_logger
from src.repository.permission_repository import PermissionRepository
from src.schema.permission import PermissionCreate
from src.schema.role import RoleCreate, RolePermissionCreate
from src.services.permission_service import PermissionService
from src.services.role_service import RoleService

logger = get_logger(__name__)

PERMISSIONS = [
    "users:read",
    "users:create",
    "users:delete",
    "users:update",
    "projects:read",
    "projects:create",
    "projects:delete",
    "projects:update",
    "resumes:read",
    "resumes:create",
    "resumes:delete",
    "resumes:update",
]

ROLES = [
    "admin",
    "student_bak",
    "student_mag",
    "teacher",
]

ROLE_PERMISSIONS = {
    "student_bak": [
        "users:read",
        "projects:read",
        "resumes:read",
        "resumes:create",
        "resumes:delete",
        "resumes:update",
    ],
    "student_mag": [
        "users:read",
        "projects:read",
        "projects:create",
        "projects:delete",
        "projects:update",
        "resumes:read",
    ],
    "teacher": PERMISSIONS,
    "admin": PERMISSIONS,
}


class FixtureService:
    """Сервис для создания тестовых данных (фикстур)"""

    def __init__(self, permission_service: PermissionService, role_service: RoleService, permission_repository: PermissionRepository) -> None:
        """Initialize with permission service dependency"""
        self._permission_service = permission_service
        self._permission_repository = permission_repository
        self._role_service = role_service

    async def create_fixtures(self) -> None:
        """
        Создание всех фикстур
        """
        try:
            for perm_name in PERMISSIONS:
                try:
                    new_perm = PermissionCreate(name=perm_name)
                    await self._permission_service.create(new_perm)
                except IntegrityError:
                    await self._permission_service._permission_repository.uow.session.rollback()
                    logger.info(f"Permission '{perm_name}' already exists, skipping.")

            for role_name in ROLES:
                try:
                    new_role = RoleCreate(name=role_name)
                    created_role = await self._role_service.create(new_role)

                    for permission_name in ROLE_PERMISSIONS.get(role_name, []):
                        permission = await self._permission_repository.get_by_name(permission_name)
                        if permission:
                            new_role_permission = RolePermissionCreate(role_id=created_role.id, permission_id=permission.id)
                            await self._permission_service.create(new_role_permission)
                        else:
                            logger.exception(f"Permission '{permission_name}' does not exist, cannot map it to a role {role_name}.")

                except IntegrityError:
                    await self._role_service._role_repository.uow.session.rollback()
                    logger.info(f"Role '{role_name}' already exists, skipping.")

            logger.info("Fixtures created successfully")

        except Exception:
            logger.exception("Failed to create fixtures")
            raise
