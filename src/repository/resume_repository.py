from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.resume import (
    Resume,
)
from src.model.user import User
from src.repository.base_repository import BaseRepository
from src.schema.resume import ResumeCreate, ResumeUpdate


class ResumeRepository(BaseRepository[Resume, ResumeCreate, ResumeUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Resume

    async def get_by_author_id(self, author_id: int) -> list[Resume]:
        """Получить резюме по автору"""

        result = await self.uow.session.execute(
            select(Resume).where(Resume.author_id == author_id),
        )
        return list(result.scalars().all())

    async def count_by_author_id(self, author_id: int) -> int:
        result = await self.uow.session.execute(
            select(func.count()).select_from(Resume).where(Resume.author_id == author_id),
        )
        return result.scalar()

    async def get_by_id_with_all(self, resume_id: int) -> Resume | None:
        query = (
            select(Resume)
            .where(Resume.id == resume_id)
            .options(
                selectinload(Resume.user).selectinload(User.role),
                selectinload(Resume.experiences),
                selectinload(Resume.skills),
                selectinload(Resume.interests),
                selectinload(Resume.links),
                selectinload(Resume.educations),
                selectinload(Resume.languages),
            )
        )
        result = await self.uow.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_author_paginated(self, author_id: int, skip: int = 0, limit: int = 10) -> list[Resume]:
        """Получить резюме автора с пагинацией."""
        result = await self.uow.session.execute(
            select(Resume).where(Resume.author_id == author_id).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def increment_views_count(self, resume_id: int) -> None:
        """Увеличить счётчик просмотров резюме."""
        await self.uow.session.execute(
            update(Resume).where(Resume.id == resume_id).values(views_count=Resume.views_count + 1),
        )
        await self.uow.session.flush()
