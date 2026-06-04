from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.education import Education
from src.repository.base_repository import BaseRepository
from src.schema.education import EducationCreate, EducationUpdate


class EducationRepository(BaseRepository[Education, EducationCreate, EducationUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Education

    async def get_by_user_id(self, user_id: int) -> list[Education]:
        result = await self.uow.session.execute(
            select(Education).where(Education.user_id == user_id),
        )
        return list(result.scalars().all())
