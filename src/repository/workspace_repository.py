from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.workspase import WorkSpace
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
