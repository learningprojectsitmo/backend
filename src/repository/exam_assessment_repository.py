from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from src.core.uow import IUnitOfWork
from src.model.exam_assessment import ExamAssessmentAnswer, ExamAssessmentSheet
from src.model.exam_attempt import AssessmentWindow, ExamAttempt
from src.model.project import Project, ProjectParticipation
from src.model.user import Role, User
from src.model.workspace import WorkSpaceParticipation


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
        sheet = ExamAssessmentSheet(
            workspace_id=workspace_id,
            exam_id=exam_id,
            attempt_id=attempt_id,
            user_id=user_id,
            status="draft",
        )
        self.uow.session.add(sheet)
        try:
            await self.uow.session.flush()
        except IntegrityError:
            await self.uow.session.rollback()
            # Re-query — another concurrent GET created the sheet
            result = await self.get_sheet(workspace_id, exam_id, attempt_id, user_id)
            if result is None:
                raise
            return result
        else:
            return sheet

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
                .execution_options(populate_existing=True)
            )
        ).all()
        return {int(row.question_id): row for row in rows}

    async def upsert_answers(
        self, sheet_id: int, answers: list[tuple[int, int | None, str | None]]
    ) -> dict[int, ExamAssessmentAnswer]:
        """Upsert (question_id, score, comment) tuples. Returns {question_id: answer}."""
        for question_id, score, comment in answers:
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
                )
            )
            await self.uow.session.execute(stmt)
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

    # ── Access / exclusion ───────────────────────────────────────────────

    async def is_excluded(self, project: Project, user_id: int, workspace_id: int) -> tuple[bool, str | None]:
        """Check if user is excluded from assessing this project."""
        if project.author_id == user_id:
            return True, "own_project_manager"
        participation = await self.uow.session.scalar(
            select(ProjectParticipation).where(
                ProjectParticipation.project_id == project.id,
                ProjectParticipation.participant_id == user_id,
            )
        )
        if participation is not None:
            return True, "own_project_member"
        is_member, _role = await self.get_workspace_participation(workspace_id, user_id)
        if not is_member:
            return True, "not_workspace_member"
        return False, None

    async def get_workspace_participation(self, workspace_id: int, user_id: int) -> tuple[bool, str | None]:
        """Return (is_member, local_role_name)."""
        query = (
            select(Role.name)
            .select_from(WorkSpaceParticipation)
            .outerjoin(Role, Role.id == WorkSpaceParticipation.role_id)
            .where(
                WorkSpaceParticipation.workspace_id == workspace_id,
                WorkSpaceParticipation.participant_id == user_id,
            )
        )
        row = (await self.uow.session.execute(query)).first()
        if row is None:
            return False, None
        return True, row[0]

    async def get_global_role(self, user_id: int) -> str | None:
        """Return global role name from User.role."""
        query = select(Role.name).select_from(User).outerjoin(Role, Role.id == User.role_id).where(User.id == user_id)
        return (await self.uow.session.execute(query)).scalar_one_or_none()
