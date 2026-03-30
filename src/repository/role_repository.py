from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import delete, select

from src.core.uow import IUnitOfWork
from src.model.models import Permission, Role, RolePermission
from src.repository.base_repository import BaseRepository
from src.schema.role import RoleCreate, RolePermissionCreate, RoleUpdate


class RoleRepository(BaseRepository[Role, RoleCreate, RoleUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Role


class RolePermissionRepository(BaseRepository[RolePermission, RolePermissionCreate, BaseModel]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = RolePermission

    async def get_role_permissions(self, role_id: int) -> list[str]:
        role_permissions_result = await self.uow.session.execute(
            select(Permission.name).join(RolePermission).where(RolePermission.role_id == role_id)
        )
        return list(role_permissions_result.scalars().all())

    async def get_by_name_and_role(self, perm_id: int, role_id: int) -> int | None:
        result = await self.uow.session.execute(
            select(RolePermission.id).where(RolePermission.role_id == role_id, RolePermission.permission_id == perm_id)
        )
        return result.scalar_one_or_none()

    async def add_permissions(self, role_id: int, to_add: list[str]) -> None:
        if not to_add:
            return

        perm_query = await self.uow.session.execute(select(Permission.id).where(Permission.name.in_(to_add)))
        perm_ids = perm_query.scalars().all()

        new_links = [RolePermission(role_id=role_id, permission_id=p_id) for p_id in perm_ids]
        self.uow.session.add_all(new_links)

    async def remove_permissions(self, role_id: int, to_remove: list[str]) -> None:
        if not to_remove:
            return

        perm_query = await self.uow.session.execute(select(Permission.id).where(Permission.name.in_(to_remove)))
        perm_ids = perm_query.scalars().all()

        await self.uow.session.execute(
            delete(RolePermission)
            .where(RolePermission.role_id == role_id)
            .where(RolePermission.permission_id.in_(perm_ids))
        )
