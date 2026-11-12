from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import BusinessLogicError, NotFoundError
from src.model.exam_attempt import AssessmentWindow, AttemptEvent, ExamAttempt
from src.model.user import User
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_repository import ExamRepository
from src.schema.exam_attempt import (
    AttemptCommand,
    AttemptEventListRead,
    AttemptEventRead,
    AttemptPause,
    AttemptRead,
    AttemptStart,
    AttemptTiming,
    AttemptWindowRead,
    CurrentAttemptRead,
)
from src.services.exam_registration_service import ExamRegistrationService
from src.services.exam_service import ExamService


class ExamAttemptService:
    def __init__(
        self,
        repository: ExamAttemptRepository,
        exams: ExamRepository,
        registrations: ExamRegistrationService,
        exam_service: ExamService,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository = repository
        self._exams = exams
        self._registrations = registrations
        self._exam_service = exam_service
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _conflict(code: str):
        raise BusinessLogicError({"code": code, "message": code.replace("_", " ")})

    async def _lock_exam(self, workspace_id: int, exam_id: int, user: User):
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        exam = await self._exams.get_scoped(workspace_id, exam_id, lock=True)
        if exam is None:
            raise NotFoundError("Exam not found")
        return exam

    async def _lock_attempt(self, workspace_id: int, exam_id: int, attempt_id: int, user: User):
        exam = await self._lock_exam(workspace_id, exam_id, user)
        attempt = await self._repository.get(workspace_id, exam_id, attempt_id, lock=True)
        if attempt is None:
            raise NotFoundError("Attempt not found")
        return exam, attempt

    async def _timing(self, exam_id: int, settings_version: int) -> AttemptTiming:
        revision = await self._exams.get_revision(exam_id, settings_version)
        if revision is None:
            raise NotFoundError("Settings revision not found")
        return AttemptTiming(
            presentation_minutes=revision.presentation_minutes, questions_minutes=revision.questions_minutes
        )

    async def _window_read(self, attempt_id: int) -> AttemptWindowRead | None:
        window = await self._repository.window(attempt_id)
        if window is None:
            return None
        return AttemptWindowRead(
            opened_at=window.opened_at,
            closes_at=window.closes_at,
            settings_version=window.settings_version,
            project_type_id=window.project_type_id,
        )

    @staticmethod
    def _remaining(attempt: ExamAttempt, now: datetime) -> int:
        if attempt.status == "finished":
            return 0
        return int((attempt.phase_deadline - (attempt.paused_at or now)).total_seconds())

    async def _read(self, attempt: ExamAttempt) -> AttemptRead:
        now = self._clock()
        return AttemptRead(
            id=attempt.id,
            workspace_id=attempt.workspace_id,
            exam_id=attempt.exam_id,
            registration_id=attempt.registration_id,
            project_id=attempt.project_id,
            project_type_id=attempt.project_type_id,
            status=attempt.status,
            version=attempt.version,
            settings_version=attempt.settings_version,
            started_at=attempt.started_at,
            phase_started_at=attempt.phase_started_at,
            phase_deadline=attempt.phase_deadline,
            paused_at=attempt.paused_at,
            paused_seconds=attempt.paused_seconds,
            finished_at=attempt.finished_at,
            created_by=attempt.created_by,
            created_at=attempt.created_at,
            updated_at=attempt.updated_at,
            remaining_seconds=self._remaining(attempt, now),
            server_now=now,
            assessment_window=await self._window_read(attempt.id),
        )

    def _event(self, attempt: ExamAttempt, *, action: str, user: User, now: datetime, reason: str | None = None):
        self._repository.uow.session.add(
            AttemptEvent(
                workspace_id=attempt.workspace_id,
                exam_id=attempt.exam_id,
                attempt_id=attempt.id,
                version=attempt.version,
                action=action,
                actor_id=user.id,
                occurred_at=now,
                reason=reason,
            )
        )

    async def start(self, workspace_id: int, exam_id: int, data: AttemptStart, user: User) -> tuple[AttemptRead, bool]:
        exam = await self._lock_exam(workspace_id, exam_id, user)
        existing = await self._repository.by_registration(exam_id, data.registration_id)
        if existing is not None:
            if existing.workspace_id != workspace_id:
                raise NotFoundError("Attempt not found")
            return await self._read(existing), False
        if await self._repository.running(exam_id) is not None:
            self._conflict("another_defense_active")
        now = self._clock()
        binding = await self._registrations.claim_for_attempt(
            workspace_id,
            exam_id,
            data.registration_id,
            expected_version=data.expected_version,
            actor=user,
            started_at=now,
        )
        timing = await self._timing(exam_id, exam.current_settings_version)
        attempt = ExamAttempt(
            workspace_id=workspace_id,
            exam_id=exam_id,
            registration_id=binding.registration_id,
            project_id=binding.project_id,
            project_type_id=binding.project_type_id,
            status="speaking",
            version=1,
            settings_version=exam.current_settings_version,
            started_at=binding.started_at,
            phase_started_at=binding.started_at,
            phase_deadline=binding.started_at + timedelta(minutes=timing.presentation_minutes),
            paused_at=None,
            paused_seconds=0,
            finished_at=None,
            created_by=user.id,
            created_at=now,
            updated_at=now,
        )
        self._repository.uow.session.add(attempt)
        try:
            await self._repository.uow.session.flush()
        except IntegrityError as error:
            cause = getattr(error.orig, "__cause__", None)
            constraint = getattr(cause, "constraint_name", None)
            if constraint == "uq_attempt_running_exam":
                self._conflict("another_defense_active")
            raise
        self._event(attempt, action="started", user=user, now=now)
        await self._repository.uow.session.flush()
        return await self._read(attempt), True

    async def current(self, workspace_id: int, exam_id: int, user: User) -> CurrentAttemptRead:
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        attempt = await self._repository.latest(workspace_id, exam_id)
        return CurrentAttemptRead(attempt=None if attempt is None else await self._read(attempt))

    async def get(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> AttemptRead:
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        attempt = await self._repository.get(workspace_id, exam_id, attempt_id)
        if attempt is None:
            raise NotFoundError("Attempt not found")
        return await self._read(attempt)

    async def questions(
        self, workspace_id: int, exam_id: int, attempt_id: int, data: AttemptCommand, user: User
    ) -> AttemptRead:
        _, attempt = await self._lock_attempt(workspace_id, exam_id, attempt_id, user)
        if attempt.status == "finished":
            self._conflict("attempt_finished")
        if attempt.paused_at is not None:
            self._conflict("attempt_paused")
        if attempt.status == "questions":
            return await self._read(attempt)
        if attempt.version != data.expected_version:
            self._conflict("attempt_version_conflict")
        now = self._clock()
        timing = await self._timing(attempt.exam_id, attempt.settings_version)
        attempt.status = "questions"
        attempt.phase_started_at = now
        attempt.phase_deadline = now + timedelta(minutes=timing.questions_minutes)
        attempt.version += 1
        attempt.updated_at = now
        self._event(attempt, action="questions", user=user, now=now)
        await self._repository.uow.session.flush()
        return await self._read(attempt)

    async def pause(
        self, workspace_id: int, exam_id: int, attempt_id: int, data: AttemptPause, user: User
    ) -> AttemptRead:
        _, attempt = await self._lock_attempt(workspace_id, exam_id, attempt_id, user)
        if attempt.status == "finished":
            self._conflict("attempt_finished")
        if attempt.paused_at is not None:
            return await self._read(attempt)
        if attempt.version != data.expected_version:
            self._conflict("attempt_version_conflict")
        now = self._clock()
        attempt.paused_at = now
        attempt.version += 1
        attempt.updated_at = now
        self._event(attempt, action="paused", user=user, now=now, reason=data.reason)
        await self._repository.uow.session.flush()
        return await self._read(attempt)

    async def resume(
        self, workspace_id: int, exam_id: int, attempt_id: int, data: AttemptCommand, user: User
    ) -> AttemptRead:
        _, attempt = await self._lock_attempt(workspace_id, exam_id, attempt_id, user)
        if attempt.status == "finished":
            self._conflict("attempt_finished")
        if attempt.paused_at is None:
            return await self._read(attempt)
        if attempt.version != data.expected_version:
            self._conflict("attempt_version_conflict")
        now = self._clock()
        delta = now - attempt.paused_at
        attempt.phase_deadline = attempt.phase_deadline + delta
        attempt.paused_seconds = attempt.paused_seconds + int(delta.total_seconds())
        attempt.paused_at = None
        attempt.version += 1
        attempt.updated_at = now
        self._event(attempt, action="resumed", user=user, now=now)
        await self._repository.uow.session.flush()
        return await self._read(attempt)

    async def finish(
        self, workspace_id: int, exam_id: int, attempt_id: int, data: AttemptCommand, user: User
    ) -> AttemptRead:
        exam, attempt = await self._lock_attempt(workspace_id, exam_id, attempt_id, user)
        if attempt.status == "finished":
            return await self._read(attempt)
        if attempt.version != data.expected_version:
            self._conflict("attempt_version_conflict")
        now = self._clock()
        settings = await self._exam_service.prepare_assessment_window(
            workspace_id,
            exam_id,
            attempt.project_type_id,
            expected_version=exam.current_settings_version,
            opened_at=now,
        )
        self._repository.uow.session.add(
            AssessmentWindow(
                workspace_id=workspace_id,
                exam_id=exam_id,
                attempt_id=attempt.id,
                project_type_id=attempt.project_type_id,
                settings_version=settings.settings_version,
                opened_at=settings.opened_at,
                closes_at=settings.closes_at,
                created_by=user.id,
                created_at=now,
            )
        )
        attempt.status = "finished"
        attempt.finished_at = now
        attempt.paused_at = None
        attempt.version += 1
        attempt.updated_at = now
        self._event(attempt, action="finished", user=user, now=now)
        await self._repository.uow.session.flush()
        return await self._read(attempt)

    async def events(
        self, workspace_id: int, exam_id: int, attempt_id: int, user: User, *, limit: int, offset: int
    ) -> AttemptEventListRead:
        await self._lock_exam(workspace_id, exam_id, user)
        if await self._repository.get(workspace_id, exam_id, attempt_id) is None:
            raise NotFoundError("Attempt not found")
        rows = await self._repository.events(attempt_id, limit=limit, offset=offset)
        return AttemptEventListRead(
            items=[AttemptEventRead.model_validate(row) for row in rows[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )
