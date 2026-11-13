from __future__ import annotations

from sqlalchemy import select

from src.core.uow import IUnitOfWork
from src.model.exam_attempt import AssessmentWindow, AttemptEvent, ExamAttempt


class ExamAttemptRepository:
    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    async def by_registration(
        self, workspace_id: int, exam_id: int, registration_id: int, *, lock: bool = False
    ) -> ExamAttempt | None:
        query = (
            select(ExamAttempt)
            .where(
                ExamAttempt.workspace_id == workspace_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.registration_id == registration_id,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.uow.session.scalars(query)).one_or_none()

    async def running(self, exam_id: int, *, lock: bool = False) -> ExamAttempt | None:
        query = (
            select(ExamAttempt)
            .where(ExamAttempt.exam_id == exam_id, ExamAttempt.status.in_(("speaking", "questions")))
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.uow.session.scalars(query)).one_or_none()

    async def get(self, workspace_id: int, exam_id: int, attempt_id: int, *, lock: bool = False) -> ExamAttempt | None:
        query = (
            select(ExamAttempt)
            .where(
                ExamAttempt.id == attempt_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.workspace_id == workspace_id,
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.uow.session.scalars(query)).one_or_none()

    async def latest(self, workspace_id: int, exam_id: int) -> ExamAttempt | None:
        running = await self.running(exam_id)
        if running is not None:
            return running
        postponed = await self.uow.session.scalar(
            select(ExamAttempt)
            .where(
                ExamAttempt.workspace_id == workspace_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.status == "postponed",
            )
            .order_by(ExamAttempt.postponed_at.desc(), ExamAttempt.id.desc())
            .limit(1)
        )
        if postponed is not None:
            return postponed
        query = (
            select(ExamAttempt)
            .where(
                ExamAttempt.workspace_id == workspace_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.status == "finished",
            )
            .order_by(ExamAttempt.finished_at.desc(), ExamAttempt.id.desc())
            .limit(1)
        )
        return (await self.uow.session.scalars(query)).one_or_none()

    async def for_exam(self, workspace_id: int, exam_id: int, *, lock: bool = False) -> dict[int, ExamAttempt]:
        query = (
            select(ExamAttempt)
            .where(ExamAttempt.workspace_id == workspace_id, ExamAttempt.exam_id == exam_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        rows = (await self.uow.session.scalars(query)).all()
        return {row.registration_id: row for row in rows}

    async def window(self, attempt_id: int) -> AssessmentWindow | None:
        return (
            await self.uow.session.scalars(select(AssessmentWindow).where(AssessmentWindow.attempt_id == attempt_id))
        ).one_or_none()

    async def events(self, attempt_id: int, *, limit: int, offset: int) -> list[AttemptEvent]:
        return list(
            (
                await self.uow.session.scalars(
                    select(AttemptEvent)
                    .where(AttemptEvent.attempt_id == attempt_id)
                    .order_by(AttemptEvent.version, AttemptEvent.id)
                    .limit(limit + 1)
                    .offset(offset)
                )
            ).all()
        )
