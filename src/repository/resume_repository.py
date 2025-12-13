from __future__ import annotations

from sqlalchemy import select

from src.model.models import Resume
from src.repository.base_repository import BaseRepository
from src.schema.resume import ResumeCreate, ResumeUpdate


class ResumeRepository(BaseRepository[Resume, ResumeCreate, ResumeUpdate]):
    def __init__(self, session_factory) -> None:
        super().__init__(session_factory)
        self._model = Resume

    async def get_by_author_id(self, author_id: int) -> list[Resume]:
        """Получить резюме по автору"""

        result = await self.uow.session.execute(
            select(Resume).where(Resume.author_id == author_id),
        )
        return result.scalars().all()
