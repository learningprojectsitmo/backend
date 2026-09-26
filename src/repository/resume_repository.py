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

    async def unset_other_defaults(self, author_id: int, keep_id: int) -> int:
        """Снять признак основного со всех остальных резюме автора.

        Нужен для переключения «основное» НА этот резюме: guard
        ``id != keep_id`` не даёт снять флаг, который в той же транзакции
        только что поставили.
        """

        result = await self.uow.session.execute(
            update(Resume)
            .where(
                Resume.author_id == author_id,
                Resume.id != keep_id,
                Resume.is_default.is_(True),
            )
            .values(is_default=False),
        )
        return result.rowcount or 0

    async def clear_default(self, resume_id: int) -> None:
        """Немедленно снять признак основного с конкретного резюме.

        Отдельный метод, а не unset_other_defaults: здесь очищается именно та
        строка, которую unset_other_defaults исключал бы по ``id != keep_id``.
        UPDATE выполняется сразу, тогда как мутация ORM-объекта ушла бы в flush
        на commit — и между ними у автора было бы два основных, что ломает
        uq_resume_author_default.
        """

        await self.uow.session.execute(
            update(Resume).where(Resume.id == resume_id).values(is_default=False),
        )

    async def get_next_default_candidate_id(
        self,
        author_id: int,
        *,
        exclude_id: int,
        visible_only: bool,
    ) -> int | None:
        """Наиболее подходящее резюме, которым можно заменить основное.

        ``exclude_id`` обязателен: в момент вызова скрываемое/удаляемое резюме
        ещё находится в БД и иначе единственный кандидат на замену — оно само.

        Сначала ищутся видимые с непустым заголовком, чтобы участник не исчез из
        списка резюме пространства; если видимых не осталось — любое, чтобы
        основное всегда оставалось ровно одно.
        """

        query = select(Resume.id).where(Resume.author_id == author_id, Resume.id != exclude_id)
        if visible_only:
            query = query.where(Resume.is_visible.is_(True), Resume.header != "")
            query = query.order_by(Resume.id)
        else:
            query = query.order_by(
                Resume.is_visible.desc(),
                (Resume.header != "").desc(),
                Resume.id,
            )
        result = await self.uow.session.execute(query.limit(1))
        return result.scalar()

    async def set_default(self, resume_id: int) -> None:
        await self.uow.session.execute(
            update(Resume).where(Resume.id == resume_id).values(is_default=True),
        )

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
