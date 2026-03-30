from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.models import Permission
from src.repository.base_repository import BaseRepository
from src.schema.permission import PermissionCreate


class PermissionRepository(BaseRepository[Permission, PermissionCreate, BaseModel]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Permission

    async def get_by_name(self, permission_name: str) -> Permission | None:
        result = await self.uow.session.execute(
            select(Permission).where(Permission.name == permission_name),
        )
        return result.scalar_one_or_none()

    async def get_all_possible(self) -> list[str]:
        all_permissions_result = await self.uow.session.execute(select(Permission.name))
        return list(all_permissions_result.scalars().all())
