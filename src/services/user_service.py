from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_password
from src.model.models import User
from src.repository.user_repository import UserRepository
from src.schema.user import UserCreate, UserFull, UserListResponse, UserUpdate
from src.services.auth_service import AuthService
from src.services.base_service import BaseService


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(self, user_repository: UserRepository):
        super().__init__(user_repository)
        self._user_repository = user_repository

    async def create_user(self, user_data: UserCreate) -> User:
        """Создать нового пользователя с хешированием пароля"""
        hashed_password = hash_password(user_data.password_string)

        # Создаем объект с хешированным паролем
        user_data_with_hash = UserCreate(
            email=user_data.email,
            first_name=user_data.first_name,
            middle_name=user_data.middle_name,
            last_name=user_data.last_name,
            isu_number=user_data.isu_number,
            password_string=hashed_password,
        )

        return await self._user_repository.create(user_data_with_hash)

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
