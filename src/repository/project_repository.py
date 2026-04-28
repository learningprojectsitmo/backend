from __future__ import annotations

from sqlalchemy import or_, select

from src.core.uow import IUnitOfWork
from src.model.models import Project, ProjectParticipation
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

    async def is_user_in_project(self, project_id: int, user_id: int) -> bool:
        """Проверить, является ли пользователь автором или участником проекта."""
        result = await self.uow.session.execute(
            select(Project.id)
            .outerjoin(ProjectParticipation, ProjectParticipation.project_id == Project.id)
            .where(
                Project.id == project_id,
                or_(
                    Project.author_id == user_id,
                    ProjectParticipation.participant_id == user_id,
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
