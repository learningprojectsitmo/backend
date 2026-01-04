from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.models import Project
from src.repository.base_repository import BaseRepository
from src.schema.project import ProjectCreate, ProjectUpdate


class ProjectRepository(BaseRepository[Project, ProjectCreate, ProjectUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Project

    # Дополнительные методы, если нужны
    async def get_by_author_id(self, author_id: int) -> list[Project]:
        result = await self.uow.session.execute(select(Project).where(Project.author_id == author_id))
        return list(result.scalars().all())
