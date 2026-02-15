from __future__ import annotations

from sqlalchemy import select

from core.uow import IUnitOfWork
from src.model.models import PasswordReset
from src.repository.base_repository import BaseRepository
from src.schema.auth import PasswordResetRequest


class PasswordResetRepository(BaseRepository[PasswordReset, PasswordResetRequest, None]):
    """Репозиторий для работы с токенами для сброса пароля"""

    def __init__(self, uow: IUnitOfWork):
        super().__init__(uow)
        self._model = PasswordReset

    async def get_by_token(self, token: str) -> PasswordReset | None:
        """Получить токен сброса пароля по токену"""

        result = await self.uow.session.execute(
            select(PasswordReset).where(PasswordReset.token == token),
        )
        return result.scalar_one_or_none()
