from __future__ import annotations

from sqlalchemy import func, select

from src.core.uow import IUnitOfWork
from src.model.exam_result import ExamResultEdition
from src.model.project_type_question import ProjectTypeQuestion


class ExamResultRepository:
    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    async def latest(self, attempt_id: int) -> ExamResultEdition | None:
        query = (
            select(ExamResultEdition)
            .where(ExamResultEdition.attempt_id == attempt_id)
            .order_by(ExamResultEdition.version.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return (await self.uow.session.scalars(query)).one_or_none()

    async def editions(self, attempt_id: int) -> list[ExamResultEdition]:
        query = (
            select(ExamResultEdition)
            .where(ExamResultEdition.attempt_id == attempt_id)
            .order_by(ExamResultEdition.version)
            .execution_options(populate_existing=True)
        )
        return list((await self.uow.session.scalars(query)).all())

    async def add(self, edition: ExamResultEdition) -> ExamResultEdition:
        self.uow.session.add(edition)
        await self.uow.session.flush()
        return edition

    async def question_count(self, project_type_id: int) -> int:
        return int(
            await self.uow.session.scalar(
                select(func.count())
                .select_from(ProjectTypeQuestion)
                .where(ProjectTypeQuestion.project_type_id == project_type_id)
            )
            or 0
        )
