from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.user import User
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_participation_repository import (
    ExamParticipationRepository,
    ParticipationRow,
)
from src.schema.exam_participation import (
    ParticipantRead,
    ParticipationAnswerRead,
    ParticipationCounts,
    ParticipationRead,
    ParticipationState,
    ParticipationSubmissionRead,
    ParticipationSummary,
    ParticipationWindowRead,
)
from src.services.exam_service import ExamService
from src.services.project_relations import ProjectRelationsService


class ExamParticipationService:
    """Who may assess an attempt, who submitted, who did not and who is excluded (AC-07)."""

    def __init__(
        self,
        repository: ExamParticipationRepository,
        attempts: ExamAttemptRepository,
        exam_service: ExamService,
        relations: ProjectRelationsService,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository = repository
        self._attempts = attempts
        self._exam_service = exam_service
        self._relations = relations
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _item(row: ParticipationRow) -> ParticipantRead:
        submission = row.submission
        return ParticipantRead(
            user_id=row.user_id,
            name=row.name,
            role=row.role,
            status=row.status,
            exclusion_reason=None if row.admitted else row.exclusion_reason,
            submission=(
                None
                if submission is None
                else ParticipationSubmissionRead(
                    version=submission.version,
                    submitted_at=submission.submitted_at,
                    total=submission.total,
                    answers=[
                        ParticipationAnswerRead(question_id=a.question_id, score=a.score, comment=a.comment)
                        for a in submission.answers
                    ],
                )
            ),
        )

    @staticmethod
    def _summary(items: list[ParticipantRead]) -> ParticipationSummary:
        counts = {key: ParticipationCounts() for key in ("total", "teacher", "manager", "member")}
        for item in items:
            for key in ("total", item.role):
                counter = counts[key]
                if item.status == "excluded":
                    counter.excluded += 1
                    continue
                counter.admitted += 1
                if item.status == "submitted":
                    counter.submitted += 1
                else:
                    counter.not_submitted += 1
        return ParticipationSummary(**counts)

    async def get(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> ParticipationRead:
        # Hidden or foreign exams are 404 before the role check; a visible exam without the role is 403.
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        if not await self._relations.is_workspace_teacher(user.id, workspace_id=workspace_id):
            raise PermissionError("Only workspace teacher/admin can see assessment participation")
        if await self._attempts.get(workspace_id, exam_id, attempt_id) is None:
            raise NotFoundError("Attempt not found")

        data = await self._repository.list_participation(
            workspace_id=workspace_id, exam_id=exam_id, attempt_id=attempt_id
        )
        if data is None:
            return ParticipationRead(
                workspace_id=workspace_id,
                exam_id=exam_id,
                attempt_id=attempt_id,
                state="not_offered",
                window=None,
                summary=self._summary([]),
                items=[],
            )
        if not data.rows:
            raise BusinessLogicError(
                {
                    "code": "audience_snapshot_unavailable",
                    "message": "Historical audience is unavailable for this assessment window",
                }
            )
        state: ParticipationState = "open" if self._clock() < data.window.closes_at else "closed"
        items = [self._item(row) for row in data.rows]
        return ParticipationRead(
            workspace_id=workspace_id,
            exam_id=exam_id,
            attempt_id=attempt_id,
            state=state,
            window=ParticipationWindowRead(
                opened_at=data.window.opened_at,
                closes_at=data.window.closes_at,
                settings_version=data.window.settings_version,
            ),
            summary=self._summary(items),
            items=items,
        )
