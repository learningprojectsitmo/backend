from __future__ import annotations

from typing import TYPE_CHECKING

from src.model.models import Role  # , RolePermission
from src.schema.role import (
    RoleCreate,
    RolePermissionCreate,
    RolePermissionCreateAPI,
    RolePermissionFull,
    RolePermissionRepr,
    RoleUpdate,
)
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.permission_repository import PermissionRepository
    from src.repository.role_repository import RolePermissionRepository, RoleRepository


class RoleService(BaseService[Role, RoleCreate, RoleUpdate]):
    def __init__(
        self,
        role_repository: RoleRepository,
        role_permission_repository: RolePermissionRepository,
        permission_repository: PermissionRepository,
    ):
        super().__init__(role_repository)
        self._role_repository = role_repository
        self._role_permission_repository = role_permission_repository
        self._permission_repository = permission_repository

    async def create_role_permission(self, role_permission: RolePermissionCreateAPI) -> RolePermissionFull:
        # TODO: We need to check that this role permission has not been created yet
        permission = await self._permission_repository.get_by_name(role_permission.permission_str)
        if not permission:
            raise ValueError("There is no such permission!")

        role_permission_with_id = RolePermissionCreate(role_id=role_permission.role_id, permission_id=permission.id)
        return await self._role_permission_repository.create(role_permission_with_id)

    async def get_role_permissions(self, role_id: int) -> list[RolePermissionRepr]:
        return await self._role_permission_repository.get_role_permissions(role_id)

    async def delete_role_permission(self, role_permission: RolePermissionCreateAPI) -> bool:
        permission = await self._permission_repository.get_by_name(role_permission.permission_str)
        if not permission:
            raise ValueError("There is no such permission!")

        role_permission_id = await self._role_permission_repository.get_by_name_and_role(
            permission.id, role_permission.role_id
        )
        if not role_permission_id:
            raise ValueError("There is no such role permission!")

        return await self._role_permission_repository.delete(role_permission_id)
