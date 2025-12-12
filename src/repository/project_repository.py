from __future__ import annotations

from sqlalchemy import select

from src.model.models import Project
from src.repository.base_repository import BaseRepository
from src.schema.project import ProjectCreate, ProjectUpdate


class ProjectRepository(BaseRepository[Project, ProjectCreate, ProjectUpdate]):
    def __init__(self, session_factory):
        super().__init__(session_factory)
        self._model = Project

    async def get_by_id(self, id: int) -> Project | None:
        """Получить проект по ID"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Project).where(Project.id == id),
            )
            return result.scalar_one_or_none()
        finally:
            await session.close()

    async def get_by_author_id(self, author_id: int) -> list[Project]:
        """Получить проекты по автору"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Project).where(Project.author_id == author_id),
            )
            return result.scalars().all()
        finally:
            await session.close()

    async def get_multi(self, skip: int = 0, limit: int = 100) -> list[Project]:
        """Получить список проектов с пагинацией"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Project).offset(skip).limit(limit),
            )
            return result.scalars().all()
        finally:
            await session.close()

    async def create(self, obj_data: ProjectCreate) -> Project:
        """Создать новый проект"""
        session = await self._get_session()
        try:
            db_project = Project(**obj_data.model_dump())
            session.add(db_project)
            await self._commit_session(session)
            await self._refresh_session(session, db_project)
            return db_project
        finally:
            await session.close()

    async def update(self, id: int, obj_data: ProjectUpdate) -> Project | None:
        """Обновить проект"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Project).where(Project.id == id),
            )
            db_project = result.scalar_one_or_none()

            if not db_project:
                return None

            update_data = obj_data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_project, field, value)

            await self._commit_session(session)
            await self._refresh_session(session, db_project)
            return db_project
        finally:
            await session.close()

    async def delete(self, id: int) -> bool:
        """Удалить проект"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Project).where(Project.id == id),
            )
            db_project = result.scalar_one_or_none()

            if not db_project:
                return False

            await session.delete(db_project)
            await self._commit_session(session)
            return True
        finally:
            await session.close()

    async def count(self) -> int:
        """Подсчитать количество проектов"""
        session = await self._get_session()
        try:
            result = await session.execute(
                select(Project).count(),
            )
            return result.scalar()
        finally:
            await session.close()
