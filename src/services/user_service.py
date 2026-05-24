from __future__ import annotations

import secrets
from src.core.logging_config import get_logger, security_logger
from datetime import UTC, datetime, timedelta
import random

from src.model.models import NewUser
from src.model.user import User
from src.repository.permission_repository import PermissionRepository
from src.repository.user_repository import UserPermissionRepository, UserRepository, NewUserRepository
from src.schema.permission import PermissionMatrix, PermissionMatrixElement
from src.schema.user import (
    NewUserCreate,
    NewUserUpdate,
    UserCreate,
    UserCreateHashedPwd,
    UserFull,
    UserListResponse,
    UserUpdate,
)
from src.services.auth_service import AuthService
from src.services.base_service import BaseService


class UserService(BaseService[User, UserCreate, UserUpdate]):
    def __init__(
        self,
        user_repository: UserRepository,
        newuser_repository: NewUserRepository,
        auth_service: AuthService,
        user_permission_repository: UserPermissionRepository,
        permission_repository: PermissionRepository,
    ):
        super().__init__(user_repository)
        self._user_repository = user_repository
        self._newuser_repository = newuser_repository
        self._user_permission_repository = user_permission_repository
        self._permission_repository = permission_repository
        self._auth_service = auth_service
        self._logger = get_logger(self.__class__.__name__)

    async def create(self, obj_data: UserCreate) -> User:
        """Создать нового пользователя с хешированием пароля"""
        user_data = obj_data.model_dump()
        user_data["password_hashed"] = self._auth_service.get_password_hash(user_data.pop("password"))

        user_create = UserCreateHashedPwd(**user_data)
        return await self._user_repository.create(user_create)

    async def get_user_by_email(self, email: str) -> User | None:
        """Получить пользователя по email"""
        return await self._user_repository.get_by_email(email)

    async def get_users_paginated(self, page: int = 1, limit: int = 10) -> UserListResponse:
        """Получить пользователей с пагинацией"""
        # TODO why don't we use get_multi from base_service?
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

    async def request_signup(self, user_data: UserCreate) -> int:
        """Создать нового пользователя во временной таблице БД с проверкой email"""
        hashed_password = self._auth_service.get_password_hash(user_data.password)

        code = random.randint(10000, 99999)
        self._logger.info(f"Signup with email for newuser, sent code {code}")
        expires_at = datetime.now(UTC) + timedelta(minutes=5)

        newuser = NewUserCreate(
            **user_data.model_dump(), password_hashed=hashed_password, code=code, expires_at=expires_at
        )

        newuser = await self._newuser_repository.create(newuser)

        # TODO: добавить отправку кода через email-клиент, сейчас токен доступен в БД
        # Пример интерфейса:
        # email_service.send(user.email, token)

        self._logger.info(f"Signup attempt with email {newuser.email}")
        return newuser.id

    async def resend_signup_code(self, newuser_id: int) -> bool:
        """Создать нового пользователя во временной таблице БД с проверкой email"""
        code = random.randint(10000, 99999)
        self._logger.info(f"Signup with email for newuser with {newuser_id}, sent code {code}")
        expires_at = datetime.now(UTC) + timedelta(minutes=5)

        newuser_update = NewUserUpdate(
            code=code,
            expires_at=expires_at,
        )

        await self._newuser_repository.update(newuser_id, newuser_update)

        # TODO: добавить генерацию и отправку кода через email-клиент, сейчас токен доступен в БД
        # Пример интерфейса:
        # email_service.send(user.email, token)

        self._logger.info(f"Code resend attempt for newuser with id {newuser_id}")
        return True

    async def confirm_signup(self, newuser_id: int, code: int) -> bool | UserFull:
        """Проверить введённый код и переместить пользователя из временной таблицы БД в постоянную"""

        newuser = await self._newuser_repository.get_by_id(newuser_id)

        if not newuser:
            self._logger.warning(f"User signup attempted with invalid newuser_id {newuser_id}")
            return False

        if newuser.code != code:
            self._logger.warning(f"User signup attempted with invalid code for newuser with id {newuser_id}")
            # TODO: inform frontend that the code is invalid
            return False

        if datetime.now(UTC) > newuser.expires_at:
            self._logger.warning(f"User signup attempted with expired token for user with email {newuser.email}")
            # TODO: inform frontend that the time has expired
            return False

        newuser_data = {
            k: v for k, v in newuser.__dict__.items() if k not in {"_sa_instance_state", "code", "expires_at"}
        }
        user_create = UserCreateHashedPwd(**newuser_data)

        user_full = await self._user_repository.create(user_create)
        await self._newuser_repository.delete(newuser_id)

        self._logger.info(f"Signup with email verification successful for user with email {newuser.email}")
        return user_full
