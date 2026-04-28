from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.models import Project, ProjectParticipation, Tag
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

    async def get_projects_with_details(self, skip: int = 0, limit: int = 100) -> list[Project]:
        query = (
            select(Project)
            .options(
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_or_create_tags(self, tag_names: list[str]) -> list[Tag]:
        if not tag_names:
            return []

        result = await self.uow.session.execute(select(Tag).where(Tag.name.in_(tag_names)))
        existing_tags = {tag.name: tag for tag in result.scalars().all()}

        tags = []
        for tag_name in tag_names:
            tag = existing_tags.get(tag_name)
            if tag is None:
                tag = Tag(name=tag_name)
                self.uow.session.add(tag)
                tags.append(tag)
            else:
                tags.append(tag)

        await self.uow.session.flush()
        return tags