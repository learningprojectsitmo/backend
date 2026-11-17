from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.core.uow import IUnitOfWork
from src.model.exam_assessment import ExamAssessmentAnswer, ExamAssessmentSheet
from src.model.exam_attempt import AssessmentWindow, AssessmentWindowAudience, ExamAttempt
from src.model.project import Project


class ExamAssessmentRepository:
    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    # ── Sheet CRUD ──────────────────────────────────────────────────────

    async def get_or_create_sheet(
        self, workspace_id: int, exam_id: int, attempt_id: int, user_id: int
    ) -> ExamAssessmentSheet:
        existing = await self.get_sheet(workspace_id, exam_id, attempt_id, user_id)
        if existing is not None:
            return existing
        statement = (
            pg_insert(ExamAssessmentSheet)
            .values(workspace_id=workspace_id, exam_id=exam_id, attempt_id=attempt_id, user_id=user_id, status="draft")
            .on_conflict_do_nothing(index_elements=[ExamAssessmentSheet.user_id, ExamAssessmentSheet.attempt_id])
            .returning(ExamAssessmentSheet)
        )
        created = (await self.uow.session.scalars(statement)).one_or_none()
        if created is not None:
            return created
        # A concurrent creator committed the same personal sheet. Never roll back
        # the caller's transaction: it may contain other legitimate changes.
        existing = await self.get_sheet(workspace_id, exam_id, attempt_id, user_id)
        if existing is None:
            raise RuntimeError("Concurrent assessment sheet is outside the requested scope")
        return existing

    async def get_sheet(
        self, workspace_id: int, exam_id: int, attempt_id: int, user_id: int
    ) -> ExamAssessmentSheet | None:
        query = (
            select(ExamAssessmentSheet)
            .where(
                ExamAssessmentSheet.workspace_id == workspace_id,
                ExamAssessmentSheet.exam_id == exam_id,
                ExamAssessmentSheet.attempt_id == attempt_id,
                ExamAssessmentSheet.user_id == user_id,
            )
            .execution_options(populate_existing=True)
        )
        return (await self.uow.session.scalars(query)).one_or_none()

    # ── Answers ──────────────────────────────────────────────────────────

    async def get_answers(self, sheet_id: int) -> dict[int, ExamAssessmentAnswer]:
        """Return {question_id: answer} for a sheet."""
        rows = (
            await self.uow.session.scalars(
                select(ExamAssessmentAnswer)
                .where(ExamAssessmentAnswer.sheet_id == sheet_id)
                .order_by(ExamAssessmentAnswer.question_id)
                .execution_options(populate_existing=True)
            )
        ).all()
        return {int(row.question_id): row for row in rows}

    async def upsert_answers(
        self, sheet_id: int, answers: list[tuple[int, int | None, str | None]]
    ) -> dict[int, ExamAssessmentAnswer]:
        """Upsert (question_id, score, comment) tuples. Returns {question_id: answer}."""
        changed = False
        # Stable row-lock order prevents reverse-order autosaves from deadlocking.
        latest = {answer[0]: answer for answer in answers}
        for question_id, score, comment in sorted(latest.values(), key=lambda answer: answer[0]):
            stmt = (
                pg_insert(ExamAssessmentAnswer)
                .values(
                    sheet_id=sheet_id,
                    question_id=question_id,
                    score=score,
                    comment=comment,
                    updated_at=datetime.now(UTC),
                )
                .on_conflict_do_update(
                    index_elements=[ExamAssessmentAnswer.sheet_id, ExamAssessmentAnswer.question_id],
                    set_={"score": score, "comment": comment, "updated_at": datetime.now(UTC)},
                    where=or_(
                        ExamAssessmentAnswer.score.is_distinct_from(score),
                        ExamAssessmentAnswer.comment.is_distinct_from(comment),
                    ),
                )
                .returning(ExamAssessmentAnswer.sheet_id)
            )
            result = await self.uow.session.execute(stmt)
            changed = result.scalar_one_or_none() is not None or changed
        if changed:
            await self.uow.session.execute(
                update(ExamAssessmentSheet)
                .where(ExamAssessmentSheet.id == sheet_id)
                .values(updated_at=datetime.now(UTC))
            )
        await self.uow.session.flush()
        return await self.get_answers(sheet_id)

    # ── Scoped fetch ─────────────────────────────────────────────────────

    async def get_attempt_with_window_and_project(
        self, workspace_id: int, exam_id: int, attempt_id: int
    ) -> tuple[ExamAttempt, AssessmentWindow, Project] | None:
        attempt = await self.uow.session.scalar(
            select(ExamAttempt)
            .where(
                ExamAttempt.id == attempt_id,
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.workspace_id == workspace_id,
            )
            .execution_options(populate_existing=True)
        )
        if attempt is None:
            return None
        window = await self.uow.session.scalar(
            select(AssessmentWindow).where(AssessmentWindow.attempt_id == attempt_id)
        )
        project = await self.uow.session.get(Project, attempt.project_id)
        return (attempt, window, project)

    # Historical access is captured atomically when the window opens.
    async def get_audience(self, window_id: int, workspace_id: int, user_id: int) -> AssessmentWindowAudience | None:
        return await self.uow.session.scalar(
            select(AssessmentWindowAudience).where(
                AssessmentWindowAudience.window_id == window_id,
                AssessmentWindowAudience.workspace_id == workspace_id,
                AssessmentWindowAudience.user_id == user_id,
            )
        )

    async def has_audience(self, window_id: int, workspace_id: int) -> bool:
        row = await self.uow.session.scalar(
            select(AssessmentWindowAudience.id)
            .where(
                AssessmentWindowAudience.window_id == window_id,
                AssessmentWindowAudience.workspace_id == workspace_id,
            )
            .limit(1)
        )
        return row is not None
