from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import BusinessLogicError, NotFoundError
from src.model.exam import Exam
from src.model.exam_attempt import ExamAttempt
from src.model.exam_registration import ExamRegistration, ExamSlot, RegistrationEvent
from src.model.user import User
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.schema.exam_queue import (
    QueueCommand,
    QueueItemRead,
    QueueMutationRead,
    QueuePlace,
    QueueRead,
    QueueReason,
)
from src.services.exam_attempt_mapping import attempt_read
from src.services.exam_service import ExamService


class ExamQueueService:
    def __init__(
        self,
        repository: ExamRegistrationRepository,
        attempts: ExamAttemptRepository,
        exams: ExamRepository,
        exam_service: ExamService,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository = repository
        self._attempts = attempts
        self._exams = exams
        self._exam_service = exam_service
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _conflict(code: str):
        raise BusinessLogicError({"code": code, "message": code.replace("_", " ")})

    async def _lock_exam(self, workspace_id: int, exam_id: int, user: User) -> Exam:
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        exam = await self._exams.get_scoped(workspace_id, exam_id, lock=True)
        if exam is None:
            raise NotFoundError("Exam not found")
        # Re-check the current role after the lock wait, like other exam mutations.
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        return exam

    @staticmethod
    def _state(registration: ExamRegistration, attempt: ExamAttempt | None) -> str:
        if attempt is not None:
            if attempt.status == "finished":
                return "finished"
            if attempt.status in ("speaking", "questions"):
                return "running"
            return "postponed"
        if registration.queue_hold == "no_show":
            return "no_show"
        if registration.queue_hold == "postponed":
            return "postponed"
        return "waiting"

    async def _item(
        self,
        registration: ExamRegistration,
        attempt: ExamAttempt | None,
        slot: ExamSlot | None,
        now: datetime,
    ) -> QueueItemRead:
        return QueueItemRead(
            registration_id=registration.id,
            project_id=registration.project_id,
            project_type_id=(
                registration.project_type_id_at_registration if attempt is None else attempt.project_type_id
            ),
            slot_id=registration.slot_id,
            planned_start_at=None if slot is None else slot.starts_at,
            planned_end_at=None if slot is None else slot.ends_at,
            position=registration.queue_position,
            state=self._state(registration, attempt),
            registration_version=registration.version,
            started_at=registration.started_at,
            attempt=None if attempt is None else await attempt_read(self._attempts, attempt, now=now),
        )

    async def _mutation(
        self,
        exam: Exam,
        registration: ExamRegistration,
        attempt: ExamAttempt | None,
        now: datetime,
        revision: int,
    ) -> QueueMutationRead:
        slot = await self._repository.slot(exam.id, registration.slot_id) if registration.slot_id else None
        return QueueMutationRead(
            item=await self._item(registration, attempt, slot, now),
            queue_revision=revision,
            server_now=now,
        )

    def _event(
        self,
        registration: ExamRegistration,
        *,
        action: str,
        user: User,
        now: datetime,
        from_position: int | None = None,
        to_position: int | None = None,
        reason: str | None = None,
    ) -> None:
        self._repository.uow.session.add(
            RegistrationEvent(
                workspace_id=registration.workspace_id,
                exam_id=registration.exam_id,
                registration_id=registration.id,
                version=registration.version,
                action=action,
                source="organizer",
                actor_id=user.id,
                occurred_at=now,
                reason=reason,
                from_position=from_position,
                to_position=to_position,
            )
        )

    async def _set_order(
        self,
        order: list[ExamRegistration],
        target: ExamRegistration | None,
        index: int,
    ) -> None:
        final = list(order)
        if target is not None:
            final.insert(index, target)
        for row in final:
            row.queue_position = None
        await self._flush_positions()
        for position, row in enumerate(final, 1):
            row.queue_position = position
        await self._flush_positions()

    async def _flush_positions(self) -> None:
        try:
            await self._repository.uow.session.flush()
        except IntegrityError as error:
            cause = getattr(error.orig, "__cause__", None)
            if getattr(cause, "constraint_name", None) == "uq_registration_queue_position":
                self._conflict("queue_position_conflict")
            raise

    async def _release(self, exam: Exam, registration: ExamRegistration) -> bool:
        if registration.queue_position is None:
            return False
        order = [
            row
            for row in await self._repository.queued_for_update(exam.workspace_id, exam.id)
            if row.id != registration.id
        ]
        registration.queue_position = None
        await self._set_order(order, None, 0)
        return True

    async def read(self, workspace_id: int, exam_id: int, user: User) -> QueueRead:
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        exam = await self._exams.get_scoped(workspace_id, exam_id)
        if exam is None:
            raise NotFoundError("Exam not found")
        now = self._clock()
        rows = await self._repository.list_active(workspace_id, exam_id)
        attempts = await self._attempts.for_exam(workspace_id, exam_id)
        slots = {slot.id: slot for slot in await self._repository.all_slots(exam_id)}
        running: list[tuple[ExamRegistration, QueueItemRead, datetime]] = []
        queued: list[tuple[ExamRegistration, QueueItemRead, datetime]] = []
        postponed: list[tuple[ExamRegistration, QueueItemRead, datetime]] = []
        no_show: list[tuple[ExamRegistration, QueueItemRead, datetime]] = []
        finished: list[tuple[ExamRegistration, QueueItemRead, datetime]] = []
        for registration in rows:
            attempt = attempts.get(registration.id)
            item = await self._item(registration, attempt, slots.get(registration.slot_id), now)
            marker = (
                attempt.postponed_at
                if attempt is not None and attempt.postponed_at is not None
                else registration.updated_at
            )
            if item.state == "running":
                running.append((registration, item, marker))
            elif registration.queue_position is not None:
                queued.append((registration, item, marker))
            elif item.state == "postponed":
                postponed.append((registration, item, marker))
            elif item.state == "no_show":
                no_show.append((registration, item, marker))
            else:
                finished.append(
                    (registration, item, attempt.finished_at if attempt and attempt.finished_at else marker)
                )
        queued.sort(key=lambda entry: (entry[1].position or 0, entry[0].id))
        postponed.sort(key=lambda entry: (entry[2], entry[0].id), reverse=True)
        no_show.sort(key=lambda entry: (entry[2], entry[0].id), reverse=True)
        finished.sort(key=lambda entry: (entry[2], entry[0].id), reverse=True)
        ordered = running + queued + postponed + no_show + finished
        return QueueRead(
            queue_revision=exam.queue_revision,
            server_now=now,
            items=[item for _, item, _ in ordered],
        )

    async def place(
        self,
        workspace_id: int,
        exam_id: int,
        registration_id: int,
        data: QueuePlace,
        user: User,
    ) -> QueueMutationRead:
        exam = await self._lock_exam(workspace_id, exam_id, user)
        registration = await self._repository.registration(workspace_id, exam_id, registration_id, lock=True)
        if registration is None:
            raise NotFoundError("Registration not found")
        if registration.status != "active":
            self._conflict("registration_not_active")
        attempt = await self._attempts.by_registration(workspace_id, exam_id, registration.id, lock=True)
        if attempt is not None:
            if attempt.status == "finished":
                self._conflict("attempt_finished")
            if attempt.status in ("speaking", "questions"):
                self._conflict("attempt_running")
        now = self._clock()
        order = [
            row for row in await self._repository.queued_for_update(workspace_id, exam_id) if row.id != registration.id
        ]
        index = len(order) if data.position is None else data.position - 1
        if index > len(order):
            self._conflict("queue_position_out_of_range")
        if registration.queue_position == index + 1 and registration.queue_hold is None:
            return await self._mutation(exam, registration, attempt, now, exam.queue_revision)
        from_position = registration.queue_position
        registration.queue_hold = None
        await self._set_order(order, registration, index)
        registration.version += 1
        registration.updated_by = user.id
        registration.updated_at = now
        self._event(
            registration,
            action="returned" if from_position is None else "queue_changed",
            user=user,
            now=now,
            from_position=from_position,
            to_position=index + 1,
        )
        await self._repository.uow.session.flush()
        revision = await self._exams.bump_queue_revision(exam_id)
        return await self._mutation(exam, registration, attempt, now, revision)

    async def next(
        self,
        workspace_id: int,
        exam_id: int,
        registration_id: int,
        data: QueueCommand,
        user: User,
    ) -> QueueMutationRead:
        placement = QueuePlace(expected_version=data.expected_version, position=1)
        return await self.place(workspace_id, exam_id, registration_id, placement, user)

    async def postpone(
        self,
        workspace_id: int,
        exam_id: int,
        registration_id: int,
        data: QueueReason,
        user: User,
    ) -> QueueMutationRead:
        exam = await self._lock_exam(workspace_id, exam_id, user)
        registration = await self._repository.registration(workspace_id, exam_id, registration_id, lock=True)
        if registration is None:
            raise NotFoundError("Registration not found")
        if registration.status != "active":
            self._conflict("registration_not_active")
        attempt = await self._attempts.by_registration(workspace_id, exam_id, registration.id, lock=True)
        if attempt is not None:
            if attempt.status == "finished":
                self._conflict("attempt_finished")
            self._conflict("defense_already_started")
        if registration.started_at is not None:
            self._conflict("defense_already_started")
        now = self._clock()
        if registration.queue_hold == "postponed":
            return await self._mutation(exam, registration, attempt, now, exam.queue_revision)
        if registration.queue_hold == "no_show":
            self._conflict("registration_not_queued")
        if registration.queue_position is None:
            self._conflict("registration_not_queued")
        from_position = registration.queue_position
        await self._release(exam, registration)
        registration.queue_hold = "postponed"
        registration.version += 1
        registration.updated_by = user.id
        registration.updated_at = now
        self._event(
            registration,
            action="postponed",
            user=user,
            now=now,
            from_position=from_position,
            reason=data.reason,
        )
        await self._repository.uow.session.flush()
        revision = await self._exams.bump_queue_revision(exam_id)
        return await self._mutation(exam, registration, attempt, now, revision)

    async def no_show(
        self,
        workspace_id: int,
        exam_id: int,
        registration_id: int,
        data: QueueReason,
        user: User,
    ) -> QueueMutationRead:
        exam = await self._lock_exam(workspace_id, exam_id, user)
        registration = await self._repository.registration(workspace_id, exam_id, registration_id, lock=True)
        if registration is None:
            raise NotFoundError("Registration not found")
        if registration.status != "active":
            self._conflict("registration_not_active")
        attempt = await self._attempts.by_registration(workspace_id, exam_id, registration.id, lock=True)
        if attempt is not None:
            if attempt.status == "finished":
                self._conflict("attempt_finished")
            self._conflict("defense_already_started")
        if registration.started_at is not None:
            self._conflict("defense_already_started")
        now = self._clock()
        if registration.queue_hold == "no_show":
            return await self._mutation(exam, registration, attempt, now, exam.queue_revision)
        if registration.queue_position is None and registration.queue_hold != "postponed":
            self._conflict("registration_not_queued")
        from_position = registration.queue_position
        await self._release(exam, registration)
        registration.queue_hold = "no_show"
        registration.version += 1
        registration.updated_by = user.id
        registration.updated_at = now
        self._event(registration, action="no_show", user=user, now=now, from_position=from_position, reason=data.reason)
        await self._repository.uow.session.flush()
        revision = await self._exams.bump_queue_revision(exam_id)
        return await self._mutation(exam, registration, attempt, now, revision)

    async def assign_on_create(self, workspace_id: int, exam_id: int, registration: ExamRegistration) -> None:
        order = [
            row for row in await self._repository.queued_for_update(workspace_id, exam_id) if row.id != registration.id
        ]
        index = len(order)
        if registration.slot_id is not None:
            slot = await self._repository.slot(exam_id, registration.slot_id)
            slots = {row.id: row for row in await self._repository.all_slots(exam_id)}
            if slot is not None:
                index = len(order)
                for position, row in enumerate(order):
                    other = slots.get(row.slot_id) if row.slot_id is not None else None
                    if other is not None and other.starts_at > slot.starts_at:
                        index = position
                        break
        await self._set_order(order, registration, index)
        await self._exams.bump_queue_revision(exam_id)

    async def release(self, workspace_id: int, exam_id: int, registration: ExamRegistration) -> int | None:
        exam = await self._exams.get_scoped(workspace_id, exam_id, lock=True)
        if exam is None:
            raise NotFoundError("Exam not found")
        if not await self._release(exam, registration):
            return None
        return await self._exams.bump_queue_revision(exam_id)
