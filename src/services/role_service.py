from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.exceptions import PermissionError
from src.model.models import Role, RolePermission
from src.schema.role import RoleCreate, RoleUpdate, RolePermissionCreate, RolePermissionFull, RolePermissionListResponse
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.role_repository import RoleRepository, RolePermissionRepository

class RoleService(BaseService[Role, RoleCreate, RoleUpdate]):
    def __init__(self, role_repository: RoleRepository, role_permission_repository: RolePermissionRepository):
        super().__init__(role_repository)
        self._role_repository = role_repository
        self._role_permission_repository = role_permission_repository

    async def create_role_permission(self, role_permission: RolePermissionCreate) -> RolePermissionFull:
        return await self._role_permission_repository.create(role_permission)

    async def get_role_permissions(self, role_id: int) -> RolePermissionListResponse:
        return await self._role_permission_repository.get_role_permissions(role_id)

    async def delete_role_permission(self, role_permission_id: int) -> bool:
        return await self._role_permission_repository.delete(role_permission_id)
