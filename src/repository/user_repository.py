from __future__ import annotations

from sqlalchemy import select

from src.model.models import User
from src.repository.base_repository import BaseRepository
from src.schema.user import UserCreate, UserUpdate


class UserRepository(BaseRepository[User, UserCreate, UserUpdate]):
    def __init__(self, session_factory):
        super().__init__(session_factory)
        self._model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.uow.session.execute(
            select(User).where(User.email == email),
        )
        return result.scalar_one_or_none()
