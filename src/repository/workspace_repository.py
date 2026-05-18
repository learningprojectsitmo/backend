from __future__ import annotations

from sqlalchemy import func, literal, select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.workspace import WorkSpace, WorkSpaceCategories
from src.repository.base_repository import BaseRepository
from src.schema.workspace import WorkSpaceCreate, WorkSpaceUpdate


class WorkSpaceRepository(BaseRepository[WorkSpace, WorkSpaceCreate, WorkSpaceUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = WorkSpace

    async def get_by_author_id(self, author_id: int) -> list[WorkSpace]:
        """Получить все workspace по author_id"""
        result = await self.uow.session.execute(
            select(WorkSpace).where(WorkSpace.author_id == author_id)
        )
        return list(result.scalars().all())

    async def get_by_status_id(self, status_id: int) -> list[WorkSpace]:
        """Получить все workspace по status_id"""
        result = await self.uow.session.execute(
            select(WorkSpace).where(WorkSpace.status_id == status_id)
        )
        return list(result.scalars().all())

    async def get_workspaces_with_stats(
        self, skip: int = 0, limit: int = 10
    ) -> tuple[list[WorkSpace], int]:
        """Получить workspace с подсчетом проектов и участников"""
        total_result = await self.uow.session.execute(select(func.count()).select_from(WorkSpace))
        total = total_result.scalar()

        query = (
            select(WorkSpace)
            .options(selectinload(WorkSpace.category))
            .order_by(WorkSpace.id)
            .offset(skip)
            .limit(limit)
        )
        workspaces_result = await self.uow.session.execute(query)
        workspaces = list(workspaces_result.scalars().all())

        return workspaces, total

    async def get_workspaces_menu_data(
        self, skip: int = 0, limit: int = 10
    ) -> tuple[list[dict], int]:
        """Получить workspace с подсчётом участников одним запросом (для меню)"""
        from src.model.workspace import WorkSpaceParticipation
        
        # Подсчёт общего количества
        total_result = await self.uow.session.execute(select(func.count()).select_from(WorkSpace))
        total = total_result.scalar()

        # Подзапрос для подсчёта участников по каждому workspace
        participants_count = (
            select(
                WorkSpaceParticipation.workspace_id,
                func.count(WorkSpaceParticipation.id).label("participants_count"),
            )
            .group_by(WorkSpaceParticipation.workspace_id)
            .subquery()
        )

        # Основной запрос: сразу возвращаем поля, соответствующие schema.Space.
        query = (
            select(
                WorkSpace.id.label("id"),
                WorkSpace.name.label("title"),
                literal(0).label("projectsCount"),
                func.coalesce(participants_count.c.participants_count, 0).label("membersCount"),
                func.coalesce(WorkSpace.color, WorkSpaceCategories.color, "#6366f1").label("color"),
                func.coalesce(WorkSpaceCategories.name, "General").label("category"),
                WorkSpace.category_id.label("category_id"),
                WorkSpace.description.label("description"),
            )
            .outerjoin(participants_count, WorkSpace.id == participants_count.c.workspace_id)
            .outerjoin(WorkSpaceCategories, WorkSpace.category_id == WorkSpaceCategories.id)
            .order_by(WorkSpace.id)
            .offset(skip)
            .limit(limit)
        )

        result = await self.uow.session.execute(query)
        return [dict(row) for row in result.mappings().all()], total
