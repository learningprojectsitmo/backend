from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from src.model.models import Permission
from src.schema.permission import PermissionCreate
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.permission_repository import PermissionRepository


class PermissionService(BaseService[Permission, PermissionCreate, BaseModel]):
    def __init__(self, permission_repository: PermissionRepository):
        super().__init__(permission_repository)
        self._permission_repository = permission_repository
