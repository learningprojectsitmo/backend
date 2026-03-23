from __future__ import annotations

# For now, when I don't have updates:
from pydantic import BaseModel
from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.models import Permission, Role, RolePermission
from src.repository.base_repository import BaseRepository
from src.schema.role import RoleCreate, RolePermissionCreate, RolePermissionRepr, RoleUpdate


class RoleRepository(BaseRepository[Role, RoleCreate, RoleUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Role


class RolePermissionRepository(BaseRepository[RolePermission, RolePermissionCreate, BaseModel]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = RolePermission

    async def get_role_permissions(self, role_id: int) -> list[RolePermissionRepr]:
        all_permissions_result = await self.uow.session.execute(select(Permission.name))
        all_permissions = all_permissions_result.scalars().all()

        role_permissions_result = await self.uow.session.execute(
            select(Permission.name).join(RolePermission).where(RolePermission.role_id == role_id)
        )
        role_permissions = set(role_permissions_result.scalars().all())

        entity_permissions: dict[str, list[str]] = {}

        for permission in all_permissions:
            entity, action = permission.split(":", 1)
            if entity not in entity_permissions:
                entity_permissions[entity] = []

            if permission in role_permissions:
                entity_permissions[entity].append(action)

        return [
            RolePermissionRepr(entity_name=entity, allowed_permissions=permissions)
            for entity, permissions in sorted(entity_permissions.items())
        ]

    async def get_by_name_and_role(self, perm_id: int, role_id: int) -> int | None:
        result = await self.uow.session.execute(
            select(RolePermission.id).where(RolePermission.role_id == role_id, RolePermission.permission_id == perm_id)
        )
        return result.scalar_one_or_none()
