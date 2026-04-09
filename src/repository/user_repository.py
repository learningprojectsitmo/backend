from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import delete, select

from src.core.uow import IUnitOfWork
from src.model.models import Permission, User, UserPermission
from src.repository.base_repository import BaseRepository
from src.schema.user import UserCreate, UserPermissionCreate, UserUpdate


class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.uow.session.execute(
            select(User).where(User.email == email),
        )
        return result.scalar_one_or_none()


class UserPermissionRepository(BaseRepository[UserPermission, UserPermissionCreate, BaseModel]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = UserPermission

    async def get_user_permissions(self, user_id: int) -> list[str]:
        user_permissions_result = await self.uow.session.execute(
            select(Permission.name).join(UserPermission).where(UserPermission.user_id == user_id)
        )
        return list(user_permissions_result.scalars().all())

    async def add_permissions(self, user_id: int, to_add: list[str]) -> None:
        if not to_add:
            return

        perm_query = await self.uow.session.execute(select(Permission.id).where(Permission.name.in_(to_add)))
        perm_ids = perm_query.scalars().all()

        new_links = [UserPermission(user_id=user_id, permission_id=p_id) for p_id in perm_ids]
        self.uow.session.add_all(new_links)

    async def remove_permissions(self, user_id: int, to_remove: list[str]) -> None:
        if not to_remove:
            return

        perm_query = await self.uow.session.execute(select(Permission.id).where(Permission.name.in_(to_remove)))
        perm_ids = perm_query.scalars().all()

        await self.uow.session.execute(
            delete(UserPermission)
            .where(UserPermission.user_id == user_id)
            .where(UserPermission.permission_id.in_(perm_ids))
        )
