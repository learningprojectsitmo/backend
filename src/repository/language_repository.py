from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.language import Language
from src.repository.base_repository import BaseRepository
from src.schema.language import LanguageCreate, LanguageUpdate


class LanguageRepository(BaseRepository[Language, LanguageCreate, LanguageUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Language

    async def get_by_user_id(self, user_id: int) -> list[Language]:
        result = await self.uow.session.execute(
            select(Language).where(Language.user_id == user_id),
        )
        return list(result.scalars().all())
