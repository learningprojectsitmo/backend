from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.model.models import Resume
from src.schema.resume import ResumeCreate, ResumeUpdate
from src.repository.base_repository import BaseRepository


class ResumeRepository(BaseRepository[Resume, ResumeCreate, ResumeUpdate]):
    def __init__(self, session_factory):
        super().__init__(session_factory)
        self._model = Resume

    async def get_by_id(self, id: int) -> Resume | None:
        """Получить резюме по ID"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Resume).where(Resume.id == id)
            )
            return result.scalar_one_or_none()
        finally:
            await session.close()

    async def get_by_author_id(self, author_id: int) -> list[Resume]:
        """Получить резюме по автору"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Resume).where(Resume.author_id == author_id)
            )
            return result.scalars().all()
        finally:
            await session.close()

    async def get_multi(self, skip: int = 0, limit: int = 100) -> list[Resume]:
        """Получить список резюме с пагинацией"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Resume).offset(skip).limit(limit)
            )
            return result.scalars().all()
        finally:
            await session.close()

    async def create(self, obj_data: ResumeCreate) -> Resume:
        """Создать новое резюме"""
        session = await self._get_session()
        try:
            db_resume = Resume(**obj_data.model_dump())
            session.add(db_resume)
            await self._commit_session(session)
            await self._refresh_session(session, db_resume)
            return db_resume
        finally:
            await session.close()

    async def update(self, id: int, obj_data: ResumeUpdate) -> Resume | None:
        """Обновить резюме"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Resume).where(Resume.id == id)
            )
            db_resume = result.scalar_one_or_none()

            if not db_resume:
                return None

            update_data = obj_data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_resume, field, value)

            await self._commit_session(session)
            await self._refresh_session(session, db_resume)
            return db_resume
        finally:
            await session.close()

    async def delete(self, id: int) -> bool:
        """Удалить резюме"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Resume).where(Resume.id == id)
            )
            db_resume = result.scalar_one_or_none()

            if not db_resume:
                return False

            await session.delete(db_resume)
            await self._commit_session(session)
            return True
        finally:
            await session.close()

    async def count(self) -> int:
        """Подсчитать количество резюме"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Resume).count()
            )
            return result.scalar()
        finally:
            await session.close()