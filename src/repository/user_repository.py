from __future__ import annotations

from sqlalchemy import select

from src.model.models import User
from src.repository.base_repository import BaseRepository
from src.schema.user import UserCreate, UserUpdate


class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    def __init__(self, session_factory):
        super().__init__(session_factory)
        self._model = User

    async def get_by_id(self, id: int) -> User | None:
        """Получить пользователя по ID"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(User).where(User.id == id),
            )
            return result.scalar_one_or_none()
        finally:
            await session.close()

    async def get_by_email(self, email: str) -> User | None:
        """Получить пользователя по email"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(User).where(User.email == email),
            )
            return result.scalar_one_or_none()
        finally:
            await session.close()

    async def get_multi(self, skip: int = 0, limit: int = 100) -> list[User]:
        """Получить список пользователей с пагинацией"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(User).offset(skip).limit(limit),
            )
            return result.scalars().all()
        finally:
            await session.close()

    async def create(self, obj_data: UserCreate) -> User:
        """Создать нового пользователя"""
        session = await self._get_session()
        try:
            # Хеширование пароля будет происходить в сервисе
            db_obj = User(
                email=obj_data.email,
                first_name=obj_data.first_name,
                middle_name=obj_data.middle_name,
                last_name=obj_data.last_name,
                isu_number=obj_data.isu_number,
                password_hashed=obj_data.password_string,  # Будет заменено на хеш в сервисе
            )

            session.add(db_obj)
            await self._commit_session(session)
            await self._refresh_session(session, db_obj)
            return db_obj
        finally:
            await session.close()

    async def update(self, id: int, obj_data: UserUpdate) -> User | None:
        """Обновить пользователя"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(User).where(User.id == id),
            )
            db_user = result.scalar_one_or_none()

            if not db_user:
                return None

            update_data = obj_data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                if hasattr(db_user, field):
                    setattr(db_user, field, value)

            await self._commit_session(session)
            await self._refresh_session(session, db_user)
            return db_user
        finally:
            await session.close()

    async def delete(self, id: int) -> bool:
        """Удалить пользователя"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(User).where(User.id == id),
            )
            db_user = result.scalar_one_or_none()

            if not db_user:
                return False

            await session.delete(db_user)
            await self._commit_session(session)
            return True
        finally:
            await session.close()

    async def count(self) -> int:
        """Подсчитать количество пользователей"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(User).count(),
            )
            return result.scalar()
        finally:
            await session.close()

    async def authenticate_user(self, email: str, password: str, verify_password_func) -> User | None:
        """Аутентификация пользователя"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(User).where(User.email == email),
            )
            user = result.scalar_one_or_none()

            if user and verify_password_func(password, user.password_hashed):
                return user
            return None
        finally:
            await session.close()
