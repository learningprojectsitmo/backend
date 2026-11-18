from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, select

from src.core.uow import IUnitOfWork
from src.model.exam_assessment import (
    ExamAssessmentSheet,
    ExamAssessmentSubmission,
    ExamAssessmentSubmissionAnswer,
)
from src.model.exam_attempt import AssessmentWindow, AssessmentWindowAudience
from src.model.user import User

ROLE_ORDER = {"teacher": 0, "manager": 1, "member": 2}
# Snapshot reasons -> the public names used by the assessment form.
PUBLIC_EXCLUSION_REASONS = {
    "member_of_defending_team": "own_project_member",
    "manager_of_defending_team": "own_project_manager",
}


@dataclass(frozen=True)
class ParticipationAnswer:
    question_id: int
    score: int
    comment: str | None


@dataclass(frozen=True)
class ParticipationSubmission:
    """Latest submitted edition of one sheet."""

    version: int
    submitted_at: datetime
    total: int
    answers: tuple[ParticipationAnswer, ...]


@dataclass(frozen=True)
class ParticipationRow:
    """One member of the audience snapshot; independent of the HTTP schemas (reused by the CSV, #122).

    `submission` is set only for admitted assessors that submitted; a draft is never reflected here.
    `exclusion_reason` is the raw snapshot value (see PUBLIC_EXCLUSION_REASONS).
    """

    user_id: int
    first_name: str
    last_name: str | None
    role: str
    admitted: bool
    exclusion_reason: str | None
    submission: ParticipationSubmission | None

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name or ''}".strip()

    @property
    def status(self) -> str:
        if not self.admitted:
            return "excluded"
        return "submitted" if self.submission is not None else "not_submitted"


@dataclass(frozen=True)
class ParticipationWindow:
    window_id: int
    opened_at: datetime
    closes_at: datetime
    settings_version: int


@dataclass(frozen=True)
class ExamParticipation:
    window: ParticipationWindow
    rows: tuple[ParticipationRow, ...]


class ExamParticipationRepository:
    def __init__(self, uow: IUnitOfWork):
        self.uow = uow

    async def list_participation(self, *, workspace_id: int, exam_id: int, attempt_id: int) -> ExamParticipation | None:
        """Audience of the attempt's assessment window with the latest submission of every assessor.

        Returns None when the window was never opened. At most three statements regardless of the
        audience size: window, audience LEFT JOIN sheet LEFT JOIN latest submission, answers of the
        latest submissions. Rows are ordered by role (teacher, manager, member), name, user id.
        """
        session = self.uow.session
        window_row = (
            await session.execute(
                select(
                    AssessmentWindow.id,
                    AssessmentWindow.opened_at,
                    AssessmentWindow.closes_at,
                    AssessmentWindow.settings_version,
                ).where(
                    AssessmentWindow.attempt_id == attempt_id,
                    AssessmentWindow.exam_id == exam_id,
                    AssessmentWindow.workspace_id == workspace_id,
                )
            )
        ).one_or_none()
        if window_row is None:
            return None
        window = ParticipationWindow(
            window_row.id, window_row.opened_at, window_row.closes_at, window_row.settings_version
        )

        latest_version = (
            select(func.max(ExamAssessmentSubmission.version))
            .where(ExamAssessmentSubmission.sheet_id == ExamAssessmentSheet.id)
            .correlate(ExamAssessmentSheet)
            .scalar_subquery()
        )
        audience = (
            await session.execute(
                select(
                    AssessmentWindowAudience.user_id,
                    User.first_name,
                    User.last_name,
                    AssessmentWindowAudience.role,
                    AssessmentWindowAudience.admitted,
                    AssessmentWindowAudience.exclusion_reason,
                    ExamAssessmentSubmission.id.label("submission_id"),
                    ExamAssessmentSubmission.version,
                    ExamAssessmentSubmission.submitted_at,
                    ExamAssessmentSubmission.total,
                )
                .select_from(AssessmentWindowAudience)
                .join(User, User.id == AssessmentWindowAudience.user_id)
                .outerjoin(
                    ExamAssessmentSheet,
                    and_(
                        ExamAssessmentSheet.user_id == AssessmentWindowAudience.user_id,
                        ExamAssessmentSheet.attempt_id == attempt_id,
                        ExamAssessmentSheet.exam_id == exam_id,
                        ExamAssessmentSheet.workspace_id == workspace_id,
                    ),
                )
                .outerjoin(
                    ExamAssessmentSubmission,
                    and_(
                        ExamAssessmentSubmission.sheet_id == ExamAssessmentSheet.id,
                        ExamAssessmentSubmission.version == latest_version,
                    ),
                )
                .where(
                    AssessmentWindowAudience.window_id == window.window_id,
                    AssessmentWindowAudience.workspace_id == workspace_id,
                )
            )
        ).all()

        # Excluded assessors do not vote: their sheet (if it somehow exists) is not reported.
        submission_ids = [row.submission_id for row in audience if row.admitted and row.submission_id is not None]
        answers: dict[int, list[ParticipationAnswer]] = {}
        if submission_ids:
            answer_rows = await session.execute(
                select(
                    ExamAssessmentSubmissionAnswer.submission_id,
                    ExamAssessmentSubmissionAnswer.question_id,
                    ExamAssessmentSubmissionAnswer.score,
                    ExamAssessmentSubmissionAnswer.comment,
                )
                .where(ExamAssessmentSubmissionAnswer.submission_id.in_(submission_ids))
                .order_by(ExamAssessmentSubmissionAnswer.submission_id, ExamAssessmentSubmissionAnswer.question_id)
            )
            for submission_id, question_id, score, comment in answer_rows.all():
                answers.setdefault(int(submission_id), []).append(
                    ParticipationAnswer(int(question_id), int(score), comment)
                )

        rows = [
            ParticipationRow(
                user_id=int(row.user_id),
                first_name=row.first_name,
                last_name=row.last_name,
                role=row.role,
                admitted=bool(row.admitted),
                exclusion_reason=row.exclusion_reason,
                submission=(
                    ParticipationSubmission(
                        version=int(row.version),
                        submitted_at=row.submitted_at,
                        total=int(row.total),
                        answers=tuple(answers.get(int(row.submission_id), ())),
                    )
                    if row.admitted and row.submission_id is not None
                    else None
                ),
            )
            for row in audience
        ]
        # Python-side ordering keeps the result independent of the database collation.
        rows.sort(key=lambda item: (ROLE_ORDER.get(item.role, len(ROLE_ORDER)), item.name, item.user_id))
        return ExamParticipation(window=window, rows=tuple(rows))
