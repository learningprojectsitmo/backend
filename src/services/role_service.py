from __future__ import annotations

from typing import TYPE_CHECKING

from src.model.models import Role  # , RolePermission
from src.schema.permission import PermissionMatrix, PermissionMatrixElement
from src.schema.role import (
    RoleCreate,
    RolePermissionCreate,
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

    async def get_role_permissions(self, role_id: int) -> PermissionMatrix:
        all_permissions = await self._permission_repository.get_all_possible()

        role_permissions = await self._role_permission_repository.get_role_permissions(role_id)

        permissions_matrix = {}

        for permission in all_permissions:
            entity, action = permission.split(":", 1)
            if entity not in permissions_matrix:
                permissions_matrix[entity] = PermissionMatrixElement(
                    create=False,
                    read=False,
                    update=False,
                    delete=False,
                )

            if permission in role_permissions:
                try:
                    setattr(permissions_matrix[entity], action, True)
                except AttributeError:
                    raise ValueError(f"Action {action} is not supported") from None

        return PermissionMatrix(permissions_matrix=permissions_matrix)

    async def remap_role_permission(self, role_id: int, permission_matrix: PermissionMatrix) -> PermissionMatrix:
        current_matrix = await self.get_role_permissions(role_id)

        to_add = []
        to_remove = []

        for entity, new_elements in permission_matrix.permissions_matrix.items():
            curr_elements = current_matrix.permissions_matrix.get(entity)

            for action in ["create", "read", "update", "delete"]:
                new_val = getattr(new_elements, action)
                curr_val = getattr(curr_elements, action)

                if new_val != curr_val:
                    perm_str = f"{entity}:{action}"
                    if new_val:
                        to_add.append(perm_str)
                    else:
                        to_remove.append(perm_str)

        async with self._role_permission_repository.uow:
            if to_add:
                await self._role_permission_repository.add_permissions(role_id, to_add)
            if to_remove:
                await self._role_permission_repository.remove_permissions(role_id, to_remove)

        return permission_matrix

    async def create_role_permission(self, role_id: int, permission_id: int) -> None:
        new_role_permission_link = RolePermissionCreate(role_id=role_id, permission_id=permission_id)
        await self._role_permission_repository.create(new_role_permission_link)
