from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from src.core.logging_config import get_logger
from src.repository.permission_repository import PermissionRepository
from src.schema.permission import PermissionCreate
from src.schema.role import RoleCreate
from src.schema.user import UserCreate
from src.services.permission_service import PermissionService
from src.services.role_service import RoleService
from src.services.user_service import UserService

logger = get_logger(__name__)

# TODO: delete in production the users fixture!!

admin_user_for_dev = UserCreate(
    email="user@example.com",
    first_name="string",
    middle_name="string",
    role_id=1,
    password="string",
)
USERS = [admin_user_for_dev]

PERMISSIONS = [
    "users:create",
    "users:read",
    "users:update",
    "users:delete",
    "projects:create",
    "projects:read",
    "projects:update",
    "projects:delete",
    "resumes:create",
    "resumes:read",
    "resumes:update",
    "resumes:delete",
]


ROLE_PERMISSIONS = {
    "admin": PERMISSIONS,
    "teacher": PERMISSIONS,
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
}

ROLES = ROLE_PERMISSIONS.keys()


class FixtureService:
    """Сервис для создания тестовых данных (фикстур)"""

    def __init__(
        self,
        permission_service: PermissionService,
        role_service: RoleService,
        permission_repository: PermissionRepository,
        user_service: UserService,
    ) -> None:
        self._permission_service = permission_service
        self._permission_repository = permission_repository
        self._role_service = role_service
        self._user_service = user_service

    async def create_fixtures(self) -> None:
        # TODO: remove commits and rollbacks
        # (they were added because of async bugs)
        # TODO: remove permission repository, do all operations through the service
        try:
            for perm_name in PERMISSIONS:
                try:
                    await self._permission_service.create(PermissionCreate(name=perm_name))
                    await self._permission_repository.uow.commit()
                except IntegrityError:
                    await self._permission_repository.uow.session.rollback()
                    logger.info(f"Permission '{perm_name}' already exists, skipping.")

            for role_name in ROLES:
                try:
                    role = await self._role_service.create(RoleCreate(name=role_name))
                    await self._role_service._role_repository.uow.commit()

                    for perm_name in ROLE_PERMISSIONS.get(role_name, []):
                        perm = await self._permission_repository.get_by_name(perm_name)
                        if perm:
                            await self._role_service.create_role_permission(role.id, perm.id)
                        else:
                            logger.error(f"Permission '{perm_name}' not found.")
                    await self._role_service._role_repository.uow.commit()

                except IntegrityError:
                    await self._role_service._role_repository.uow.session.rollback()
                    logger.info(f"Role '{role_name}' already exists, skipping.")

            for user in USERS:
                try:
                    await self._user_service.create(user)
                    await self._user_service._user_repository.uow.commit()

                except IntegrityError:
                    await self._user_service._user_repository.uow.session.rollback()
                    logger.info(f"User '{user}' already exists, skipping.")

            logger.info("Fixtures created successfully")

        except Exception:
            logger.exception("Failed to create fixtures")
            raise
