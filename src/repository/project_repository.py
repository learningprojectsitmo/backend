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
                selectinload(Project.vacancies),
            )
        )
        result = await self.uow.session.execute(query)
        return result.scalar_one_or_none()

    async def is_user_in_project(self, project_id: int, user_id: int) -> bool:
        result = await self.uow.session.execute(
            select(ProjectParticipation).where(
                ProjectParticipation.project_id == project_id,
                ProjectParticipation.user_id == user_id,
            ),
        )
        return result.scalar_one_or_none() is not None

    async def get_by_author_id(self, author_id: int) -> list[Project]:
        query = (
            select(Project)
            .where(Project.author_id == author_id)
            .options(
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
                selectinload(Project.vacancies),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_projects_by_ids(self, project_ids: list[int]) -> list[Project]:
        query = (
            select(Project)
            .where(Project.id.in_(project_ids))
            .options(
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
                selectinload(Project.vacancies),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_projects_by_participant_id(self, participant_id: int) -> list[Project]:
        subquery = select(ProjectParticipation.project_id).where(ProjectParticipation.participant_id == participant_id)
        query = (
            select(Project)
            .where(Project.id.in_(subquery))
            .options(
                selectinload(Project.participants).selectinload(ProjectParticipation.participant),
                selectinload(Project.tags),
                selectinload(Project.status),
                selectinload(Project.vacancies),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_responses_by_respondent_id(self, respondent_id: int) -> list[Response]:
        query = (
            select(Response)
            .where(Response.respondent_id == respondent_id, Response.type == "response")
            .options(
                selectinload(Response.project),
                selectinload(Response.vacancy),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def get_response_by_id(self, response_id: int) -> Response | None:
        result = await self.uow.session.execute(select(Response).where(Response.id == response_id))
        return result.scalar_one_or_none()

    async def update_response_status(self, response_id: int, status: str) -> Response | None:
        response = await self.get_response_by_id(response_id)
        if not response:
            return None
        response.status = status
        await self.uow.session.flush()
        return response

    async def get_invitations_by_invitee_id(self, invitee_id: int) -> list[Response]:
        query = (
            select(Response)
            .where(Response.respondent_id == invitee_id, Response.type == "invitation")
            .options(
                selectinload(Response.project),
                selectinload(Response.vacancy),
                selectinload(Response.inviter),
            )
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def count_invitations_by_user_id(self, user_id: int) -> int:
        result = await self.uow.session.execute(
            select(func.count())
            .select_from(Response)
            .where(Response.respondent_id == user_id, Response.type == "invitation"),
        )
        return result.scalar() or 0

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

    async def remove_participant(self, project_id: int, user_id: int) -> bool:
        result = await self.uow.session.execute(
            select(ProjectParticipation).where(
                ProjectParticipation.project_id == project_id,
                ProjectParticipation.participant_id == user_id,
            ),
        )
        participation = result.scalar_one_or_none()
        if not participation:
            return False
        await self.uow.session.delete(participation)
        await self.uow.session.flush()
        return True

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
