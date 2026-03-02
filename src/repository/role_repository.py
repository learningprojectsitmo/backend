from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.models import Resume, Role, RolePermission
from src.repository.base_repository import BaseRepository
from src.schema.role import RoleCreate, RoleUpdate, RolePermissionCreate, RolePermissionListResponse

# For now, when I don't have updates:
from pydantic import BaseModel

class RoleRepository(BaseRepository[Role, RoleCreate, RoleUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Role

class RolePermissionRepository(BaseRepository[RolePermission, RolePermissionCreate, BaseModel]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = RolePermission

    async def get_role_permissions(self, role_id: int) -> RolePermissionListResponse | None:
        result = await self.uow.session.execute(
            select(RolePermission).where(RolePermission.role_id == role_id),
        )
        return result.scalar_one_or_none()

    # Here should be no update logic, right?

