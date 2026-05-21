from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.project import Project, ProjectParticipation, Response, Tag
from src.repository.base_repository import BaseRepository
from src.schema.project import ProjectCreate, ProjectUpdate


class ProjectRepository(BaseRepository[Project, ProjectCreate, ProjectUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Project

    async def get_by_id(self, id: int) -> Project | None:
        query = (
            select(Project)
            .where(Project.id == id)
            .options(
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
                selectinload(Project.responses).selectinload(Response.respondent),
                selectinload(Project.workspace),
            )
        )
        result = await self.uow.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_author_id(self, author_id: int) -> list[Project]:
        result = await self.uow.session.execute(select(Project).where(Project.author_id == author_id))
        return list(result.scalars().all())

    async def get_projects_by_workspace(self, workspace_id: int, skip: int = 0, limit: int = 100) -> list[Project]:
        query = (
            select(Project)
            .where(Project.workspace_id == workspace_id)
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

    async def count_by_workspace(self, workspace_id: int) -> int:
        result = await self.uow.session.execute(
            select(func.count()).select_from(Project).where(Project.workspace_id == workspace_id)
        )
        return result.scalar()

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

        existing_tags_result = await self.uow.session.execute(select(Tag).where(Tag.name.in_(tag_names)))
        existing_tags_list = list(existing_tags_result.scalars().all())
        existing_tags = {tag.name: tag for tag in existing_tags_list}

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
