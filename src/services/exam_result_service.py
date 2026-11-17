from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import BusinessLogicError, NotFoundError
from src.model.exam import Exam
from src.model.exam_attempt import ExamAttempt
from src.model.exam_result import ExamResultEdition
from src.model.user import User
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_repository import ExamRepository
from src.repository.exam_result_repository import ExamResultRepository
from src.schema.exam import ExamWeights
from src.schema.exam_result import (
    ResultAccept,
    ResultEditionListRead,
    ResultEditionRead,
    ResultPreliminaryRead,
    ResultPublish,
    ResultRead,
    ResultRoleRead,
    ResultSheetCounts,
    ResultSnapshot,
)
from src.services.exam_score import ExamScoreError, ExamScoreResult, ScoreWeights, calculate_exam_score
from src.services.exam_service import ExamService
from src.services.exam_sheet_source import ExamSheetSource

SHEET_CRITERION_MAX = 5


class ExamResultService:
    def __init__(
        self,
        repository: ExamResultRepository,
        attempts: ExamAttemptRepository,
        exams: ExamRepository,
        exam_service: ExamService,
        sheets: ExamSheetSource,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository = repository
        self._attempts = attempts
        self._exams = exams
        self._exam_service = exam_service
        self._sheets = sheets
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _conflict(code: str):
        raise BusinessLogicError({"code": code, "message": code.replace("_", " ")})

    async def _lock_attempt(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> ExamAttempt:
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        exam = await self._exams.get_scoped(workspace_id, exam_id, lock=True)
        if exam is None:
            raise NotFoundError("Exam not found")
        # Re-check the role after the lock wait, like the attempt service does.
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        attempt = await self._attempts.get(workspace_id, exam_id, attempt_id, lock=True)
        if attempt is None:
            raise NotFoundError("Attempt not found")
        return attempt

    async def _attempt(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> ExamAttempt:
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        attempt = await self._attempts.get(workspace_id, exam_id, attempt_id)
        if attempt is None:
            raise NotFoundError("Attempt not found")
        return attempt

    async def _require_closed_window(self, attempt: ExamAttempt, now: datetime) -> None:
        if attempt.status != "finished":
            self._conflict("attempt_not_finished")
        window = await self._attempts.window(attempt.id)
        if window is None:
            self._conflict("assessment_window_missing")
        if window.closes_at > now:
            self._conflict("assessment_window_open")

    async def _calculate(self, exam: Exam, attempt: ExamAttempt) -> tuple[ExamScoreResult, ResultSnapshot]:
        revision = await self._exams.get_revision(exam.id, exam.current_settings_version)
        if revision is None:
            raise NotFoundError("Settings revision not found")
        questions = await self._repository.question_count(attempt.project_type_id)
        if questions == 0:
            self._conflict("questions_missing")
        sheet_max = SHEET_CRITERION_MAX * questions
        sheets = await self._sheets.load_submitted_sheets(attempt_id=attempt.id)
        weights = ExamWeights(
            teacher=revision.teacher_weight, manager=revision.manager_weight, member=revision.member_weight
        )
        try:
            result = calculate_exam_score(
                sheets=sheets,
                weights=ScoreWeights(weights.teacher, weights.manager, weights.member),
                sheet_max=sheet_max,
                max_score=revision.max_score,
            )
        except ExamScoreError:
            self._conflict("invalid_sheet_data")
        counts = {role.role: role.sheets_count for role in result.roles}
        snapshot = ResultSnapshot(
            settings_version=exam.current_settings_version,
            weights=weights,
            max_score=revision.max_score,
            sheet_max=sheet_max,
            sheets=ResultSheetCounts(teacher=counts["teacher"], manager=counts["manager"], member=counts["member"]),
            used_weight=result.used_weight,
        )
        return result, snapshot

    @staticmethod
    def _edition_read(edition: ExamResultEdition) -> ResultEditionRead:
        return ResultEditionRead(
            id=edition.id,
            workspace_id=edition.workspace_id,
            exam_id=edition.exam_id,
            attempt_id=edition.attempt_id,
            version=edition.version,
            kind=edition.kind,
            calculated_score=edition.calculated_score,
            final_score=edition.final_score,
            snapshot=ResultSnapshot(
                settings_version=edition.settings_version,
                weights=ExamWeights(
                    teacher=edition.teacher_weight, manager=edition.manager_weight, member=edition.member_weight
                ),
                max_score=edition.max_score,
                sheet_max=edition.sheet_max,
                sheets=ResultSheetCounts(
                    teacher=edition.teacher_sheets, manager=edition.manager_sheets, member=edition.member_sheets
                ),
                used_weight=edition.used_weight,
            ),
            reason=edition.reason,
            decided_by=edition.decided_by,
            decided_at=edition.decided_at,
            published_at=edition.published_at,
            published_by=edition.published_by,
        )

    @staticmethod
    def _outdated(edition: ResultEditionRead | None, preliminary: ResultPreliminaryRead | None) -> bool:
        if edition is None or preliminary is None:
            return False
        if edition.snapshot != preliminary.snapshot:
            return True
        return edition.calculated_score != preliminary.score

    async def _read(self, exam_id: int, attempt: ExamAttempt, edition: ExamResultEdition | None) -> ResultRead:
        exam = await self._exams.get_scoped(attempt.workspace_id, exam_id)
        if exam is None:
            raise NotFoundError("Exam not found")
        edition_read = None if edition is None else self._edition_read(edition)
        preliminary = None
        if attempt.status == "finished" and await self._attempts.window(attempt.id) is not None:
            result, snapshot = await self._calculate(exam, attempt)
            preliminary = ResultPreliminaryRead(
                score=result.score,
                no_calculation=result.no_calculation,
                snapshot=snapshot,
                roles=[
                    ResultRoleRead(
                        role=role.role,
                        weight=role.weight,
                        sheets_count=role.sheets_count,
                        average=role.average,
                        counted=role.counted,
                    )
                    for role in result.roles
                ],
            )
        return ResultRead(
            workspace_id=attempt.workspace_id,
            exam_id=exam_id,
            attempt_id=attempt.id,
            edition=edition_read,
            preliminary=preliminary,
            outdated=self._outdated(edition_read, preliminary),
        )

    async def get(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> ResultRead:
        attempt = await self._attempt(workspace_id, exam_id, attempt_id, user)
        return await self._read(exam_id, attempt, await self._repository.latest(attempt.id))

    async def editions(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> ResultEditionListRead:
        attempt = await self._attempt(workspace_id, exam_id, attempt_id, user)
        rows = await self._repository.editions(attempt.id)
        return ResultEditionListRead(items=[self._edition_read(row) for row in rows])

    async def accept(
        self, workspace_id: int, exam_id: int, attempt_id: int, data: ResultAccept, user: User
    ) -> ResultRead:
        attempt = await self._lock_attempt(workspace_id, exam_id, attempt_id, user)
        now = self._clock()
        await self._require_closed_window(attempt, now)
        latest = await self._repository.latest(attempt.id)
        current_version = 0 if latest is None else latest.version
        if data.expected_version != current_version:
            self._conflict("result_version_conflict")
        exam = await self._exams.get_scoped(workspace_id, exam_id)
        if exam is None:
            raise NotFoundError("Exam not found")
        result, snapshot = await self._calculate(exam, attempt)
        if result.score is None:
            self._conflict("no_calculation")
        edition = ExamResultEdition(
            workspace_id=workspace_id,
            exam_id=exam_id,
            attempt_id=attempt.id,
            version=current_version + 1,
            kind="calculated",
            calculated_score=result.score,
            final_score=result.score,
            settings_version=snapshot.settings_version,
            teacher_weight=snapshot.weights.teacher,
            manager_weight=snapshot.weights.manager,
            member_weight=snapshot.weights.member,
            max_score=snapshot.max_score,
            sheet_max=snapshot.sheet_max,
            teacher_sheets=snapshot.sheets.teacher,
            manager_sheets=snapshot.sheets.manager,
            member_sheets=snapshot.sheets.member,
            used_weight=snapshot.used_weight,
            reason=data.reason,
            decided_by=user.id,
            decided_at=now,
        )
        try:
            await self._repository.add(edition)
        except IntegrityError as error:
            cause = getattr(error.orig, "__cause__", None)
            if getattr(cause, "constraint_name", None) == "uq_result_edition_version":
                self._conflict("result_version_conflict")
            raise
        return await self._read(exam_id, attempt, edition)

    async def publish(
        self, workspace_id: int, exam_id: int, attempt_id: int, data: ResultPublish, user: User
    ) -> ResultRead:
        attempt = await self._lock_attempt(workspace_id, exam_id, attempt_id, user)
        latest = await self._repository.latest(attempt.id)
        if latest is None:
            self._conflict("result_not_accepted")
        if latest.version != data.expected_version:
            self._conflict("result_version_conflict")
        now = self._clock()
        if latest.published_at is None:
            latest.published_at = now
            latest.published_by = user.id
            await self._repository.uow.session.flush()
        return await self._read(exam_id, attempt, latest)
