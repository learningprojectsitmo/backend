from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.project import ProjectSpecification, SpecificationComment
from src.repository.base_repository import BaseRepository
from src.schema.specification import SpecificationUpdate


class SpecificationRepository(BaseRepository[ProjectSpecification, dict, SpecificationUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = ProjectSpecification

    async def get_by_project_id(self, project_id: int) -> ProjectSpecification | None:
        result = await self.uow.session.execute(
            select(ProjectSpecification).where(ProjectSpecification.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_draft(self, project_id: int) -> ProjectSpecification:
        spec = await self.get_by_project_id(project_id)
        if spec is None:
            spec = ProjectSpecification(project_id=project_id, status="draft")
            self.uow.session.add(spec)
            await self.uow.session.flush()
        return spec


class SpecificationCommentRepository(BaseRepository[SpecificationComment, dict, dict]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = SpecificationComment

    async def get_by_specification_id(self, specification_id: int) -> list[SpecificationComment]:
        result = await self.uow.session.execute(
            select(SpecificationComment)
            .where(SpecificationComment.specification_id == specification_id)
            .options(selectinload(SpecificationComment.author))
            .order_by(SpecificationComment.created_at)
        )
        return list(result.scalars().all())
