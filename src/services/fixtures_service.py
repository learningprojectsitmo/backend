from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from src.core.logging_config import get_logger
from src.schema.permission import PermissionCreate
from src.services.permission_service import PermissionService

logger = get_logger(__name__)

# Актуальные разрешения, которые используются в проде
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


class FixtureService:
    """Сервис для создания тестовых данных (фикстур)"""

    def __init__(self, permission_service: PermissionService) -> None:
        """Initialize with permission service dependency"""
        self._permission_service = permission_service

    async def create_fixtures(self) -> None:
        """
        Создание всех тестовых данных
        """
        try:
            for perm_name in PERMISSIONS:
                try:
                    new_perm = PermissionCreate(name=perm_name)
                    await self._permission_service.create(new_perm)
                except IntegrityError:
                    await self._permission_service._permission_repository.uow.session.rollback()
                    logger.info(f"Permission '{perm_name}' already exists, skipping.")

            logger.info("Fixtures created successfully")
        except Exception:
            logger.exception("Failed to create fixtures")
            raise
