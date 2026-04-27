from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.workspace import WorkSpace
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
