from __future__ import annotations



from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.models import Resume, Role, Entity, Permission, RolePermission, UserPermission
from src.repository.base_repository import BaseRepository
from src.schema.auth import RoleCreate, RoleUpdate, EntityCreate, EntityUpdate, PermissionCreate, PermissionUpdate, RolePermissionCreate, UserPermissionCreate #, RolePermissionUpdate, UserPermissionUpdate

# For now, when I don't have updates:
from pydantic import BaseModel


class RoleRepository(BaseRepository[Role, RoleCreate, RoleUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Role

class EntityRepository(BaseRepository[Entity, EntityCreate, EntityUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Entity

class PermissionRepository(BaseRepository[Permission, PermissionCreate, PermissionUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Permission

class RolePermissionRepository(BaseRepository[RolePermission, RolePermissionCreate, BaseModel]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = RolePermission
    # Here should be get permissions for a role, ? get all roles with the listed permission
    # Here should be no update logic, right?


class UserPermissionRepository(BaseRepository[UserPermission, UserPermissionCreate, BaseModel]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = UserPermission
    # Here should be get permissions for a user, ? get all users with the listed permission
    # Here should be no update logic, right?
