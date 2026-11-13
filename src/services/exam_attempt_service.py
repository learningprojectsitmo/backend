from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import BusinessLogicError, NotFoundError
from src.model.exam_attempt import AssessmentWindow, AttemptEvent, ExamAttempt
from src.model.user import User
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.schema.exam_attempt import (
    AttemptCommand,
    AttemptEventListRead,
    AttemptEventRead,
    AttemptPause,
    AttemptPostpone,
    AttemptRead,
    AttemptRestart,
    AttemptStart,
    AttemptTiming,
    CurrentAttemptRead,
)
from src.services.exam_attempt_mapping import attempt_read
from src.services.exam_queue_service import ExamQueueService
from src.services.exam_registration_service import ExamRegistrationService
from src.services.exam_service import ExamService


class ExamAttemptService:
    def __init__(
        self,
        repository: ExamAttemptRepository,
        exams: ExamRepository,
        registrations: ExamRegistrationService,
        exam_service: ExamService,
        queue: ExamQueueService,
        registrations_repository: ExamRegistrationRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository = repository
        self._exams = exams
        self._registrations = registrations
        self._exam_service = exam_service
        self._queue = queue
        self._registrations_repository = registrations_repository
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _conflict(code: str):
        raise BusinessLogicError({"code": code, "message": code.replace("_", " ")})

    async def _lock_exam(self, workspace_id: int, exam_id: int, user: User):
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        exam = await self._exams.get_scoped(workspace_id, exam_id, lock=True)
        if exam is None:
            raise NotFoundError("Exam not found")
        # Re-check the role from the database after the lock wait, like registrations do.
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
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

    async def _read(self, attempt: ExamAttempt, now: datetime | None = None) -> AttemptRead:
        return await attempt_read(self._repository, attempt, now=self._clock() if now is None else now)

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
        existing = await self._repository.by_registration(workspace_id, exam_id, data.registration_id)
        if existing is not None:
            if existing.status == "postponed":
                self._conflict("attempt_postponed")
            return await self._read(existing), False
        registration = await self._registrations_repository.registration(workspace_id, exam_id, data.registration_id)
        if registration is None:
            raise NotFoundError("Registration not found")
        if registration.status != "active":
            self._conflict("registration_not_active")
        if registration.started_at is not None:
            self._conflict("defense_already_started")
        if registration.queue_hold is not None or registration.queue_position is None:
            self._conflict("registration_not_queued")
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
        await self._exam_service.require_questions_ready(workspace_id, binding.project_type_id)
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
            # uq_attempt_registration is unreachable: every start holds the Exam row lock first.
            raise
        self._event(attempt, action="started", user=user, now=now)
        await self._repository.uow.session.flush()
        await self._queue.release(workspace_id, exam_id, registration)
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
        if attempt.status == "postponed":
            self._conflict("attempt_postponed")
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
        if attempt.status == "postponed":
            self._conflict("attempt_postponed")
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
        if attempt.status == "postponed":
            self._conflict("attempt_postponed")
        if attempt.paused_at is None:
            return await self._read(attempt)
        if attempt.version != data.expected_version:
            self._conflict("attempt_version_conflict")
        now = self._clock()
        delta = max(now - attempt.paused_at, timedelta(0))
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
        if attempt.paused_at is not None:
            attempt.paused_seconds += int(max(now - attempt.paused_at, timedelta(0)).total_seconds())
        registration = await self._registrations_repository.registration(workspace_id, exam_id, attempt.registration_id)
        released = None
        if registration is not None:
            released = await self._queue.release(workspace_id, exam_id, registration)
        attempt.status = "finished"
        attempt.finished_at = now
        attempt.paused_at = None
        attempt.postponed_at = None
        attempt.postponed_phase = None
        attempt.version += 1
        attempt.updated_at = now
        self._event(attempt, action="finished", user=user, now=now)
        await self._repository.uow.session.flush()
        if released is None:
            await self._exams.bump_queue_revision(exam_id)
        return await self._read(attempt)

    async def postpone(
        self,
        workspace_id: int,
        exam_id: int,
        attempt_id: int,
        data: AttemptPostpone,
        user: User,
    ) -> AttemptRead:
        _, attempt = await self._lock_attempt(workspace_id, exam_id, attempt_id, user)
        if attempt.status == "finished":
            self._conflict("attempt_finished")
        if attempt.status == "postponed":
            return await self._read(attempt)
        if attempt.version != data.expected_version:
            self._conflict("attempt_version_conflict")
        now = self._clock()
        if attempt.paused_at is not None:
            attempt.paused_seconds += int(max(now - attempt.paused_at, timedelta(0)).total_seconds())
            attempt.paused_at = None
        attempt.postponed_at = now
        attempt.postponed_phase = attempt.status
        attempt.status = "postponed"
        attempt.version += 1
        attempt.updated_at = now
        self._event(attempt, action="postponed", user=user, now=now, reason=data.reason)
        await self._repository.uow.session.flush()
        await self._exams.bump_queue_revision(exam_id)
        return await self._read(attempt)

    async def restart(
        self,
        workspace_id: int,
        exam_id: int,
        attempt_id: int,
        data: AttemptRestart,
        user: User,
    ) -> AttemptRead:
        _, attempt = await self._lock_attempt(workspace_id, exam_id, attempt_id, user)
        if attempt.status == "finished":
            self._conflict("attempt_finished")
        if attempt.status != "postponed":
            self._conflict("attempt_not_postponed")
        if await self._repository.running(exam_id) is not None:
            self._conflict("another_defense_active")
        if attempt.version != data.expected_version:
            self._conflict("attempt_version_conflict")
        now = self._clock()
        phase = attempt.postponed_phase
        timing = await self._timing(exam_id, attempt.settings_version)
        minutes = timing.presentation_minutes if phase == "speaking" else timing.questions_minutes
        attempt.status = phase
        attempt.phase_started_at = now
        attempt.phase_deadline = now + timedelta(minutes=minutes)
        attempt.postponed_at = None
        attempt.postponed_phase = None
        attempt.version += 1
        attempt.updated_at = now
        registration = await self._registrations_repository.registration(workspace_id, exam_id, attempt.registration_id)
        released = None
        if registration is not None:
            released = await self._queue.release(workspace_id, exam_id, registration)
        self._event(attempt, action="restarted", user=user, now=now, reason=data.reason)
        await self._repository.uow.session.flush()
        if released is None:
            await self._exams.bump_queue_revision(exam_id)
        return await self._read(attempt)

    async def events(
        self, workspace_id: int, exam_id: int, attempt_id: int, user: User, *, limit: int, offset: int
    ) -> AttemptEventListRead:
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        if await self._repository.get(workspace_id, exam_id, attempt_id) is None:
            raise NotFoundError("Attempt not found")
        rows = await self._repository.events(attempt_id, limit=limit, offset=offset)
        return AttemptEventListRead(
            items=[AttemptEventRead.model_validate(row) for row in rows[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )
