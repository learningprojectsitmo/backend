from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.project import Project
from src.model.settings import SpaceSettings
from src.model.workspace import WorkSpace, WorkSpaceCategories, WorkSpaceParticipation
from src.repository.base_repository import BaseRepository
from src.schema.workspace import WorkSpaceCreate, WorkSpaceUpdate


class WorkSpaceRepository(BaseRepository[WorkSpace, WorkSpaceCreate, WorkSpaceUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = WorkSpace

    async def get_by_author_id(self, author_id: int) -> list[WorkSpace]:
        """Получить все workspace по author_id"""
        result = await self.uow.session.execute(select(WorkSpace).where(WorkSpace.author_id == author_id))
        return list(result.scalars().all())

    async def get_by_status_id(self, status_id: int) -> list[WorkSpace]:
        """Получить все workspace по status_id"""
        result = await self.uow.session.execute(select(WorkSpace).where(WorkSpace.status_id == status_id))
        return list(result.scalars().all())

    async def get_workspaces_with_stats(self, skip: int = 0, limit: int = 10) -> tuple[list[WorkSpace], int]:
        """Получить workspace с подсчетом проектов и участников"""
        total_result = await self.uow.session.execute(select(func.count()).select_from(WorkSpace))
        total = total_result.scalar()

        query = (
            select(WorkSpace).options(selectinload(WorkSpace.category)).order_by(WorkSpace.id).offset(skip).limit(limit)
        )
        workspaces_result = await self.uow.session.execute(query)
        workspaces = list(workspaces_result.scalars().all())

        return workspaces, total

    async def add_participation(self, workspace_id: int, participant_id: int) -> None:
        participation = WorkSpaceParticipation(
            workspace_id=workspace_id,
            participant_id=participant_id,
        )
        self.uow.session.add(participation)

    async def get_participants_count(self, workspace_id: int) -> int:
        result = await self.uow.session.execute(
            select(func.count()).where(WorkSpaceParticipation.workspace_id == workspace_id)
        )
        return result.scalar()

    async def get_all_categories(self) -> list[WorkSpaceCategories]:
        result = await self.uow.session.execute(
            select(WorkSpaceCategories).order_by(WorkSpaceCategories.id)
        )
        return list(result.scalars().all())

    async def get_category_name(self, category_id: int) -> str | None:
        result = await self.uow.session.execute(
            select(WorkSpaceCategories).where(WorkSpaceCategories.id == category_id)
        )
        category = result.scalar_one_or_none()
        return category.name if category else None

    async def get_or_create_category(self, category_data: dict) -> WorkSpaceCategories:
        result = await self.uow.session.execute(
            select(WorkSpaceCategories).where(WorkSpaceCategories.name == category_data["name"])
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing
        category = WorkSpaceCategories(**category_data)
        self.uow.session.add(category)
        return category

    async def get_workspaces_menu_data(self, user_id: int, skip: int = 0, limit: int = 10) -> tuple[list[dict], int]:
        """Получить workspace с подсчётом участников (только видимые пользователю)"""
        # Подзапрос для подсчёта участников по каждому workspace
        participants_count = (
            select(
                WorkSpaceParticipation.workspace_id,
                func.count(WorkSpaceParticipation.id).label("participants_count"),
            )
            .group_by(WorkSpaceParticipation.workspace_id)
            .subquery()
        )

        # Подзапрос для подсчёта проектов по каждому workspace
        projects_count = (
            select(
                Project.workspace_id,
                func.count(Project.id).label("projects_count"),
            )
            .where(Project.workspace_id.isnot(None))
            .group_by(Project.workspace_id)
            .subquery()
        )

        # Подзапрос для списка workspace, где пользователь — участник
        user_workspace_ids = select(WorkSpaceParticipation.workspace_id).where(
            WorkSpaceParticipation.participant_id == user_id
        )

        # Фильтр: публичные ИЛИ автор ИЛИ участник
        visible_filter = or_(
            SpaceSettings.visibility.is_(None),
            SpaceSettings.visibility == "public",
            WorkSpace.author_id == user_id,
            WorkSpace.id.in_(user_workspace_ids),
        )

        # Подсчёт видимых workspace
        count_query = (
            select(func.count())
            .select_from(WorkSpace)
            .outerjoin(SpaceSettings, WorkSpace.id == SpaceSettings.space_id)
            .where(visible_filter)
        )
        total_result = await self.uow.session.execute(count_query)
        total = total_result.scalar()

        # Основной запрос: сразу возвращаем поля, соответствующие schema.Space.
        query = (
            select(
                WorkSpace.id.label("id"),
                WorkSpace.name.label("title"),
                func.coalesce(projects_count.c.projects_count, 0).label("projectsCount"),
                func.coalesce(participants_count.c.participants_count, 0).label("membersCount"),
                func.coalesce(WorkSpace.color, WorkSpaceCategories.color, "#6366f1").label("color"),
                func.coalesce(WorkSpaceCategories.name, "General").label("category"),
                WorkSpace.category_id.label("category_id"),
                WorkSpace.description.label("description"),
                SpaceSettings.icon_url.label("icon_url"),
            )
            .outerjoin(participants_count, WorkSpace.id == participants_count.c.workspace_id)
            .outerjoin(projects_count, WorkSpace.id == projects_count.c.workspace_id)
            .outerjoin(WorkSpaceCategories, WorkSpace.category_id == WorkSpaceCategories.id)
            .outerjoin(SpaceSettings, WorkSpace.id == SpaceSettings.space_id)
            .where(visible_filter)
            .order_by(WorkSpace.id)
            .offset(skip)
            .limit(limit)
        )

        result = await self.uow.session.execute(query)
        return [dict(row) for row in result.mappings().all()], total
