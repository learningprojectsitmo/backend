from sqlalchemy.orm import Session

from core.security import hash_password
from model.models import User
from repository.user_repository import UserRepository
from schemas import UserCreate, UserFull, UserListItem, UserListResponse, UserUpdate

from .base_service import BaseService


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(self, user_repository: UserRepository, db_session: Session):
        super().__init__(user_repository)
        self._user_repository = user_repository
        self._db_session = db_session

    def create_user(self, user_data: UserCreate) -> User:
        """Создать нового пользователя с хешированием пароля"""
        # Хешируем пароль перед созданием пользователя
        user_data.password_string = hash_password(user_data.password_string)
        return self._user_repository.create(user_data)

    def get_user_by_id(self, id: int) -> User | None:
        """Получить пользователя по ID"""
        return self._user_repository.get_by_id(id)

    def get_user_by_email(self, email: str) -> User | None:
        """Получить пользователя по email"""
        return self._user_repository.get_by_email(email)

    def get_users_paginated(self, page: int = 1, limit: int = 10) -> UserListResponse:
        """Получить список пользователей с пагинацией"""
        # Вычисляем offset для пагинации
        skip = (page - 1) * limit

        # Получаем пользователей и общее количество
        users = self._user_repository.get_multi(skip=skip, limit=limit)
        total = self._user_repository.count()

        # Преобразуем в UserListItem
        user_items = [UserListItem.model_validate(user) for user in users]

        # Вычисляем общее количество страниц
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return UserListResponse(
            items=user_items,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages
        )

    def update_user(self, id: int, user_data: UserUpdate) -> User | None:
        """Обновить пользователя"""
        return self._user_repository.update(id, user_data)

    def delete_user(self, id: int) -> bool:
        """Удалить пользователя"""
        return self._user_repository.delete(id)

    def count_users(self) -> int:
        """Подсчитать количество пользователей"""
        return self._user_repository.count()

    def get_user_full(self, id: int) -> UserFull | None:
        """Получить полную информацию о пользователе"""
        user = self._user_repository.get_by_id(id)
        if user:
            return UserFull.model_validate(user)
        return None
