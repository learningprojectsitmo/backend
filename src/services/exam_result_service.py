from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError, ValidationError
from src.model.exam import Exam
from src.model.exam_attempt import ExamAttempt
from src.model.exam_result import ExamResultEdition
from src.model.user import User
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_repository import ExamRepository
from src.repository.exam_result_repository import (
    ExamResultRegistryRow,
    ExamResultRepository,
    RegistryState,
)
from src.schema.exam import ExamWeights
from src.schema.exam_result import (
    ResultAccept,
    ResultEditionListRead,
    ResultEditionRead,
    ResultManual,
    ResultPreliminaryRead,
    ResultPublish,
    ResultRead,
    ResultRegistryCurrentRead,
    ResultRegistryItemRead,
    ResultRegistryRead,
    ResultRoleRead,
    ResultSheetCounts,
    ResultSnapshot,
)
from src.services.exam_score import ExamScoreError, ExamScoreResult, ScoreWeights, calculate_exam_score
from src.services.exam_service import ExamService
from src.services.exam_sheet_source import ExamSheetSource
from src.services.project_relations import ProjectRelationsService


class ExamResultService:
    def __init__(
        self,
        repository: ExamResultRepository,
        attempts: ExamAttemptRepository,
        exams: ExamRepository,
        exam_service: ExamService,
        sheets: ExamSheetSource,
        relations: ProjectRelationsService,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository = repository
        self._attempts = attempts
        self._exams = exams
        self._exam_service = exam_service
        self._sheets = sheets
        self._relations = relations
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _conflict(code: str):
        raise BusinessLogicError({"code": code, "message": code.replace("_", " ")})

    async def _require_teacher(self, workspace_id: int, user: User) -> None:
        # Effective teacher/admin role of this very workspace (see docs/project-relations.md).
        if not await self._relations.is_workspace_teacher(user.id, workspace_id=workspace_id):
            raise PermissionError("Only workspace teacher/admin can manage exam results")

    async def _lock_attempt(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> ExamAttempt:
        # Hidden or foreign exams are 404 before the role check; a visible exam without the role is 403.
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        await self._require_teacher(workspace_id, user)
        exam = await self._exams.get_scoped(workspace_id, exam_id, lock=True)
        if exam is None:
            raise NotFoundError("Exam not found")
        # Re-check the role after the lock wait: it may have changed while we waited.
        await self._require_teacher(workspace_id, user)
        attempt = await self._attempts.get(workspace_id, exam_id, attempt_id, lock=True)
        if attempt is None:
            raise NotFoundError("Attempt not found")
        return attempt

    async def _attempt(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> ExamAttempt:
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        await self._require_teacher(workspace_id, user)
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
        sheet_max = await self._repository.sheet_max(attempt.project_type_id)
        if sheet_max == 0:
            self._conflict("questions_missing")
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

    @staticmethod
    def _registry_item(row: ExamResultRegistryRow) -> ResultRegistryItemRead:
        current = None
        if row.current is not None:
            c = row.current
            name = " ".join(part for part in (c.decided_by_first_name, c.decided_by_last_name) if part and part.strip())
            current = ResultRegistryCurrentRead(
                version=c.version,
                kind=c.kind,
                calculated_score=c.calculated_score,
                final_score=c.final_score,
                max_score=c.max_score,
                reason=c.reason,
                decided_by_id=c.decided_by_id,
                decided_by_name=name,
                decided_at=c.decided_at,
                published_at=c.published_at,
                published_by_id=c.published_by_id,
            )
        return ResultRegistryItemRead(
            attempt_id=row.attempt_id,
            registration_id=row.registration_id,
            project_id=row.project_id,
            project_name=row.project_name,
            project_type_id=row.project_type_id,
            finished_at=row.finished_at,
            state=row.state,
            editions_count=row.editions_count,
            current=current,
            previous_final_score=row.previous_final_score,
            settings_outdated=row.settings_outdated,
        )

    async def registry(
        self,
        workspace_id: int,
        exam_id: int,
        user: User,
        *,
        q: str | None,
        state: RegistryState | None,
        limit: int,
        offset: int,
    ) -> ResultRegistryRead:
        # Same order as the other result operations: hidden/foreign exam -> 404, visible without the role -> 403.
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        await self._require_teacher(workspace_id, user)
        rows = await self._repository.list_results(
            workspace_id, exam_id, q=(q or "").strip() or None, state=state, limit=limit, offset=offset
        )
        return ResultRegistryRead(
            items=[self._registry_item(row) for row in rows[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )

    @staticmethod
    def _new_edition(
        attempt: ExamAttempt,
        *,
        version: int,
        kind: str,
        calculated_score: Decimal | None,
        final_score: Decimal,
        snapshot: ResultSnapshot,
        reason: str | None,
        user: User,
        now: datetime,
    ) -> ExamResultEdition:
        return ExamResultEdition(
            workspace_id=attempt.workspace_id,
            exam_id=attempt.exam_id,
            attempt_id=attempt.id,
            version=version,
            kind=kind,
            calculated_score=calculated_score,
            final_score=final_score,
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
            reason=reason,
            decided_by=user.id,
            decided_at=now,
        )

    async def _save(self, edition: ExamResultEdition) -> None:
        try:
            await self._repository.add(edition)
        except IntegrityError as error:
            cause = getattr(error.orig, "__cause__", None)
            if getattr(cause, "constraint_name", None) == "uq_result_edition_version":
                self._conflict("result_version_conflict")
            raise

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
        edition = self._new_edition(
            attempt,
            version=current_version + 1,
            kind="calculated",
            calculated_score=result.score,
            final_score=result.score,
            snapshot=snapshot,
            reason=data.reason,
            user=user,
            now=now,
        )
        await self._save(edition)
        return await self._read(exam_id, attempt, edition)

    async def manual(
        self, workspace_id: int, exam_id: int, attempt_id: int, data: ResultManual, user: User
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
        # The fresh calculation is stored for comparison only; "no calculation" (None) is a valid state here.
        result, snapshot = await self._calculate(exam, attempt)
        if data.final_score > snapshot.max_score:
            raise ValidationError(
                {
                    "code": "final_score_out_of_range",
                    "message": "final score must be between 0 and the exam max score",
                    "max_score": str(snapshot.max_score),
                }
            )
        edition = self._new_edition(
            attempt,
            version=current_version + 1,
            kind="manual",
            calculated_score=result.score,
            final_score=data.final_score,
            snapshot=snapshot,
            reason=data.reason,
            user=user,
            now=now,
        )
        await self._save(edition)
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
