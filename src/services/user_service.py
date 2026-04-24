from __future__ import annotations

from src.model.models import User
from src.repository.permission_repository import PermissionRepository
from src.repository.user_repository import UserPermissionRepository, UserRepository
from src.schema.permission import PermissionMatrix, PermissionMatrixElement
from src.schema.user import UserCreate, UserFull, UserListResponse, UserUpdate
from src.services.auth_service import AuthService
from src.services.base_service import BaseService


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(
        self,
        user_repository: UserRepository,
        auth_service: AuthService,
        user_permission_repository: UserPermissionRepository,
        permission_repository: PermissionRepository,
    ):
        super().__init__(user_repository)
        self._user_repository = user_repository
        self._user_permission_repository = user_permission_repository
        self._permission_repository = permission_repository
        self._auth_service = auth_service

    async def create(self, obj_data: UserCreate) -> User:
        """Создать нового пользователя с хешированием пароля"""
        hashed_password = self._auth_service.get_password_hash(obj_data.password)

        # Создаем словарь с правильными ключами для модели User
        # TODO сделать распаковку как было раньше? model dump
        user_data_dict = {
            "email": obj_data.email,
            "first_name": obj_data.first_name,
            "middle_name": obj_data.middle_name,
            "last_name": obj_data.last_name,
            "isu_number": obj_data.isu_number,
            "role_id": obj_data.role_id,
            "password_hashed": hashed_password,
        }

        return await self._user_repository.create(user_data_dict)

    async def get_user_by_id(self, id: int) -> User | None:
        """Получить пользователя по ID"""
        return await self._user_repository.get_by_id(id)

    async def get_user_by_email(self, email: str) -> User | None:
        """Получить пользователя по email"""
        return await self._user_repository.get_by_email(email)

    async def get_users_paginated(self, page: int = 1, limit: int = 10) -> UserListResponse:
        """Получить пользователей с пагинацией"""
        skip = (page - 1) * limit
        users = await self._user_repository.get_multi(skip=skip, limit=limit)
        total = await self._user_repository.count()

        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return UserListResponse(
            items=users,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    async def update_user(self, id: int, user_data: UserUpdate) -> User | None:
        """Обновить пользователя"""
        return await self._user_repository.update(id, user_data)

    async def delete_user(self, id: int) -> bool:
        """Удалить пользователя"""
        return await self._user_repository.delete(id)

    async def count_users(self) -> int:
        """Подсчитать количество пользователей"""
        return await self._user_repository.count()

    async def get_user_full(self, id: int) -> UserFull | None:
        """Получить полную информацию о пользователе"""
        user = await self._user_repository.get_by_id(id)
        if user:
            return UserFull.model_validate(user)
        return None

    async def get_user_permissions(self, user_id: int) -> PermissionMatrix:
        all_permissions = await self._permission_repository.get_all_possible()

        user_permissions = await self._user_permission_repository.get_user_permissions(user_id)

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

            if permission in user_permissions:
                try:
                    setattr(permissions_matrix[entity], action, True)
                except AttributeError:
                    raise ValueError(f"Action {action} is not supported") from None

        return PermissionMatrix(permissions_matrix=permissions_matrix)

    async def remap_user_permission(self, user_id: int, permission_matrix: PermissionMatrix) -> PermissionMatrix:
        current_matrix = await self.get_user_permissions(user_id)

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

        async with self._user_permission_repository.uow:
            if to_add:
                await self._user_permission_repository.add_permissions(user_id, to_add)
            if to_remove:
                await self._user_permission_repository.remove_permissions(user_id, to_remove)

        return permission_matrix
