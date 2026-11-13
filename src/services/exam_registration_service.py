from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from itertools import pairwise
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.exam_registration import ExamRegistration, ExamSlot, RegistrationEvent
from src.model.user import User
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam_registration import (
    EventListRead,
    EventRead,
    RegistrationAttemptBinding,
    RegistrationCancel,
    RegistrationCreate,
    RegistrationListRead,
    RegistrationMove,
    RegistrationMoveRead,
    RegistrationRead,
    RegistrationVersion,
    SlotBatchCreate,
    SlotListRead,
    SlotRead,
)
from src.services.exam_queue_service import ExamQueueService
from src.services.exam_service import ExamService


class ExamRegistrationService:
    def __init__(
        self,
        repository: ExamRegistrationRepository,
        exam_service: ExamService,
        questions: ProjectTypeQuestionRepository,
        queue: ExamQueueService,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository = repository
        self._exam_service = exam_service
        self._questions = questions
        self._queue = queue
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _conflict(code: str):
        raise BusinessLogicError({"code": code, "message": code.replace("_", " ")})

    async def list_slots(self, workspace_id: int, exam_id: int, user: User, *, limit: int, offset: int) -> SlotListRead:
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        rows = await self._repository.list_slots(workspace_id, exam_id, limit=limit, offset=offset)
        return SlotListRead(items=rows[:limit], limit=limit, offset=offset, has_more=len(rows) > limit)

    async def add_slots(self, workspace_id: int, exam_id: int, data: SlotBatchCreate, user: User) -> list[SlotRead]:
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        # The same parent lock serializes publication, slot mode and registrations.

        exam = await ExamRepository(self._repository.uow).get_scoped(workspace_id, exam_id, lock=True)
        if exam is None:
            raise NotFoundError("Exam not found")
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        configuration = (await self._exam_service.get(workspace_id, exam_id, user)).configuration
        now = self._clock()
        if now >= configuration.starts_at:
            self._conflict("slot_schedule_closed")
        old = await self._repository.all_slots(exam_id)
        if not old and await self._repository.has_registrations(exam_id):
            self._conflict("slot_schedule_locked")
        if any(slot.starts_at < configuration.starts_at for slot in data.slots):
            self._conflict("slot_before_exam")
        intervals = sorted([(s.starts_at, s.ends_at) for s in old] + [(s.starts_at, s.ends_at) for s in data.slots])
        if any(right[0] < left[1] for left, right in pairwise(intervals)):
            self._conflict("slot_overlap")
        rows = [
            ExamSlot(
                workspace_id=workspace_id,
                exam_id=exam_id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                created_by=user.id,
                created_at=now,
            )
            for slot in data.slots
        ]
        self._repository.uow.session.add_all(rows)
        await self._repository.uow.session.flush()
        return [
            SlotRead(
                id=s.id,
                workspace_id=workspace_id,
                exam_id=exam_id,
                starts_at=s.starts_at,
                ends_at=s.ends_at,
                is_available=True,
            )
            for s in rows
        ]

    async def _access(self, workspace_id, exam_id, user, *, organized):
        if organized:
            await self._exam_service.require_organizer(workspace_id, exam_id, user)
        else:
            await self._exam_service.require_read_access(workspace_id, exam_id, user)

    async def _lock_exams(self, workspace_id, exam_ids):
        repository = ExamRepository(self._repository.uow)
        for exam_id in sorted(set(exam_ids)):
            if await repository.get_scoped(workspace_id, exam_id, lock=True) is None:
                raise NotFoundError("Exam not found")

    async def _project(self, workspace_id, project_id, user, *, organized):
        project = await self._repository.project(workspace_id, project_id, lock=True)
        if project is None:
            raise NotFoundError("Project not found in this workspace")
        if not organized:
            if project.author_id != user.id:
                raise NotFoundError("Own project not found")
            member, local = await self._questions.get_membership_role(workspace_id, user.id)
            effective = local if local is not None else await self._questions.get_global_role(user.id)
            if not member or effective != "manager":
                raise PermissionError("Only the team's manager can change its registration")
        return project

    async def _configuration(self, workspace_id, exam_id, user, now, *, organized):
        if not organized:
            return (
                await self._exam_service.require_self_registration_open(workspace_id, exam_id, user, now=now)
            ).configuration
        exam = await self._exam_service.get(workspace_id, exam_id, user)
        if exam.status != "published":
            self._conflict("exam_not_published")
        return exam.configuration

    def _project_type(self, project, configuration):
        if project.project_type_id is None or project.project_type_id not in configuration.project_type_ids:
            self._conflict("project_type_not_allowed")

    async def _slot(self, exam_id, slot_id, *, locked, current=None):
        if slot_id is not None and (slot_id not in locked or locked[slot_id].exam_id != exam_id):
            raise NotFoundError("Slot not found in this exam")
        if slot_id is None:
            if await self._repository.has_slots(exam_id):
                self._conflict("slot_required")
        elif await self._repository.slot_occupied(slot_id, except_registration=current.id if current else None):
            self._conflict("slot_unavailable")

    async def _flush(self):
        try:
            await self._repository.uow.session.flush()
        except IntegrityError as error:
            cause = getattr(error.orig, "__cause__", None)
            constraint = getattr(cause, "constraint_name", None)
            codes = {
                "uq_registration_active_project": "project_already_registered",
                "uq_registration_active_slot": "slot_unavailable",
            }
            if constraint in codes:
                self._conflict(codes[constraint])
            raise

    def _event(
        self,
        row,
        *,
        action,
        source,
        user,
        now,
        reason=None,
        from_slot_id=None,
        to_slot_id=None,
        related=None,
        transfer_id=None,
    ):
        self._repository.uow.session.add(
            RegistrationEvent(
                workspace_id=row.workspace_id,
                exam_id=row.exam_id,
                registration_id=row.id,
                version=row.version,
                action=action,
                source=source,
                actor_id=user.id,
                occurred_at=now,
                reason=reason,
                from_slot_id=from_slot_id,
                to_slot_id=to_slot_id,
                related_registration_id=related,
                transfer_id=transfer_id,
            )
        )

    def _new(self, workspace_id, exam_id, project, slot_id, user, now, source):
        row = ExamRegistration(
            workspace_id=workspace_id,
            exam_id=exam_id,
            project_id=project.id,
            project_type_id_at_registration=project.project_type_id,
            slot_id=slot_id,
            status="active",
            version=1,
            created_source=source,
            created_by=user.id,
            created_at=now,
            updated_by=user.id,
            updated_at=now,
        )
        self._repository.uow.session.add(row)
        return row

    async def _create(self, workspace_id, exam_id, data, user, *, organized):
        await self._access(workspace_id, exam_id, user, organized=organized)
        await self._lock_exams(workspace_id, [exam_id])
        project = await self._project(workspace_id, data.project_id, user, organized=organized)
        slots = await self._repository.slots_for_update(
            workspace_id, {exam_id}, {data.slot_id} if data.slot_id is not None else set()
        )
        await self._access(workspace_id, exam_id, user, organized=organized)
        project = await self._project(workspace_id, project.id, user, organized=organized)
        now = self._clock()
        configuration = await self._configuration(workspace_id, exam_id, user, now, organized=organized)
        self._project_type(project, configuration)
        if await self._repository.active_for_project(project.id) is not None:
            self._conflict("project_already_registered")
        await self._slot(exam_id, data.slot_id, locked=slots)
        source = "organizer" if organized else "manager"
        row = self._new(workspace_id, exam_id, project, data.slot_id, user, now, source)
        await self._flush()
        self._event(row, action="created", source=source, user=user, now=now, to_slot_id=row.slot_id)
        await self._flush()
        await self._queue.assign_on_create(workspace_id, exam_id, row)
        return RegistrationRead.model_validate(row)

    async def create_self(
        self, workspace_id: int, exam_id: int, data: RegistrationCreate, user: User
    ) -> RegistrationRead:
        return await self._create(workspace_id, exam_id, data, user, organized=False)

    def _state(self, row, expected_version):
        if row.started_at is not None:
            self._conflict("defense_already_started")
        if row.version != expected_version:
            self._conflict("registration_version_conflict")
        if row.status != "active":
            self._conflict("registration_not_active")

    async def _change(
        self, workspace_id, exam_id, registration_id, data, user, *, organized, target_exam_id, target_slot_id=None
    ):
        for eid in sorted({exam_id, target_exam_id}):
            await self._access(workspace_id, eid, user, organized=organized)
        initial = await self._repository.registration(workspace_id, exam_id, registration_id)
        if initial is None:
            raise NotFoundError("Registration not found")
        await self._lock_exams(workspace_id, [exam_id, target_exam_id])
        project = await self._project(workspace_id, initial.project_id, user, organized=organized)
        row = await self._repository.registration(workspace_id, exam_id, registration_id, lock=True)
        self._state(row, data.expected_version)
        slot_ids = {i for i in (row.slot_id, target_slot_id) if i is not None}
        slots = await self._repository.slots_for_update(workspace_id, {exam_id, target_exam_id}, slot_ids)
        for eid in sorted({exam_id, target_exam_id}):
            await self._access(workspace_id, eid, user, organized=organized)
        project = await self._project(workspace_id, project.id, user, organized=organized)
        now = self._clock()
        for eid in sorted({exam_id, target_exam_id}):
            config = await self._configuration(workspace_id, eid, user, now, organized=organized)
            self._project_type(project, config)
        return row, project, now, slots

    @staticmethod
    def _touch(row, user, now):
        row.version += 1
        row.updated_by = user.id
        row.updated_at = now

    async def _cancel(self, workspace_id, exam_id, registration_id, data, user, *, organized):
        row, _, now, _ = await self._change(
            workspace_id, exam_id, registration_id, data, user, organized=organized, target_exam_id=exam_id
        )
        row.status = "cancelled"
        row.queue_hold = None
        self._touch(row, user, now)
        self._event(
            row,
            action="cancelled",
            source="organizer" if organized else "manager",
            user=user,
            now=now,
            reason=data.reason,
            from_slot_id=row.slot_id,
        )
        await self._flush()
        if await self._queue.release(workspace_id, exam_id, row) is None:
            await ExamRepository(self._repository.uow).bump_queue_revision(exam_id)
        return RegistrationRead.model_validate(row)

    async def cancel_self(
        self, workspace_id: int, exam_id: int, registration_id: int, data: RegistrationCancel, user: User
    ) -> RegistrationRead:
        return await self._cancel(workspace_id, exam_id, registration_id, data, user, organized=False)

    async def _move(self, workspace_id, exam_id, registration_id, data, user, *, organized):
        row, project, now, slots = await self._change(
            workspace_id,
            exam_id,
            registration_id,
            data,
            user,
            organized=organized,
            target_exam_id=data.target_exam_id,
            target_slot_id=data.target_slot_id,
        )
        same_exam = exam_id == data.target_exam_id
        await self._slot(data.target_exam_id, data.target_slot_id, locked=slots, current=row if same_exam else None)
        if same_exam and row.slot_id == data.target_slot_id:
            saved = RegistrationRead.model_validate(row)
            return RegistrationMoveRead(source=saved, target=saved)
        source = "organizer" if organized else "manager"
        old_slot = row.slot_id
        self._touch(row, user, now)
        if same_exam:
            row.slot_id = data.target_slot_id
            self._event(
                row,
                action="slot_changed",
                source=source,
                user=user,
                now=now,
                reason=data.reason,
                from_slot_id=old_slot,
                to_slot_id=row.slot_id,
            )
            await self._flush()
            saved = RegistrationRead.model_validate(row)
            return RegistrationMoveRead(source=saved, target=saved)
        row.status = "moved"
        row.queue_hold = None
        # Release the global active-project index before inserting its successor.
        await self._flush()
        if await self._queue.release(workspace_id, exam_id, row) is None:
            await ExamRepository(self._repository.uow).bump_queue_revision(exam_id)
        target = self._new(workspace_id, data.target_exam_id, project, data.target_slot_id, user, now, source)
        await self._flush()
        await self._queue.assign_on_create(workspace_id, data.target_exam_id, target)
        transfer_id = uuid4()
        self._event(
            row,
            action="moved_out",
            source=source,
            user=user,
            now=now,
            reason=data.reason,
            from_slot_id=old_slot,
            related=target.id,
            transfer_id=transfer_id,
        )
        self._event(
            target,
            action="moved_in",
            source=source,
            user=user,
            now=now,
            reason=data.reason,
            to_slot_id=target.slot_id,
            related=row.id,
            transfer_id=transfer_id,
        )
        await self._flush()
        return RegistrationMoveRead(
            source=RegistrationRead.model_validate(row), target=RegistrationRead.model_validate(target)
        )

    async def move_self(
        self, workspace_id: int, exam_id: int, registration_id: int, data: RegistrationMove, user: User
    ) -> RegistrationMoveRead:
        return await self._move(workspace_id, exam_id, registration_id, data, user, organized=False)

    async def list_self(
        self,
        workspace_id: int,
        exam_id: int,
        user: User,
        *,
        project_id: int | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> RegistrationListRead:
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        rows = await self._repository.list_registrations(
            workspace_id, exam_id, author_id=user.id, project_id=project_id, status=status, limit=limit, offset=offset
        )
        return RegistrationListRead(
            items=[RegistrationRead.model_validate(r) for r in rows[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )

    async def history(
        self, workspace_id: int, exam_id: int, registration_id: int, user: User, *, limit: int, offset: int
    ) -> EventListRead:
        await self._exam_service.require_read_access(workspace_id, exam_id, user)
        row = await self._repository.registration(workspace_id, exam_id, registration_id)
        if row is None:
            raise NotFoundError("Registration not found")
        if await self._repository.project_author(row.project_id) != user.id:
            try:
                await self._exam_service.require_organizer(workspace_id, exam_id, user)
            except PermissionError as error:
                raise NotFoundError("Registration not found") from error
        events = await self._repository.events(row.id, limit=limit, offset=offset)
        return EventListRead(
            items=[EventRead.model_validate(e) for e in events[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(events) > limit,
        )

    async def create_organized(
        self, workspace_id: int, exam_id: int, data: RegistrationCreate, user: User
    ) -> RegistrationRead:
        return await self._create(workspace_id, exam_id, data, user, organized=True)

    async def cancel_organized(
        self, workspace_id: int, exam_id: int, registration_id: int, data: RegistrationCancel, user: User
    ) -> RegistrationRead:
        return await self._cancel(workspace_id, exam_id, registration_id, data, user, organized=True)

    async def move_organized(
        self, workspace_id: int, exam_id: int, registration_id: int, data: RegistrationMove, user: User
    ) -> RegistrationMoveRead:
        return await self._move(workspace_id, exam_id, registration_id, data, user, organized=True)

    async def list_organized(
        self,
        workspace_id: int,
        exam_id: int,
        user: User,
        *,
        project_id: int | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> RegistrationListRead:
        await self._exam_service.require_organizer(workspace_id, exam_id, user)
        rows = await self._repository.list_registrations(
            workspace_id, exam_id, author_id=None, project_id=project_id, status=status, limit=limit, offset=offset
        )
        return RegistrationListRead(
            items=[RegistrationRead.model_validate(r) for r in rows[:limit]],
            limit=limit,
            offset=offset,
            has_more=len(rows) > limit,
        )

    async def claim_for_attempt(
        self,
        workspace_id: int,
        exam_id: int,
        registration_id: int,
        *,
        expected_version: int,
        actor: User,
        started_at: datetime,
    ) -> RegistrationAttemptBinding:
        data = RegistrationVersion(expected_version=expected_version)
        try:
            started_at = ExamService._utc(started_at)
        except OverflowError as error:
            raise ValueError("Timestamp is outside the supported UTC range") from error
        row, project, _, _ = await self._change(
            workspace_id, exam_id, registration_id, data, actor, organized=True, target_exam_id=exam_id
        )
        row.started_at = started_at
        self._touch(row, actor, started_at)
        self._event(
            row,
            action="defense_started",
            source="organizer",
            user=actor,
            now=started_at,
            from_slot_id=row.slot_id,
            to_slot_id=row.slot_id,
        )
        await self._flush()
        return RegistrationAttemptBinding(
            registration_id=row.id,
            workspace_id=workspace_id,
            exam_id=exam_id,
            project_id=project.id,
            project_type_id=project.project_type_id,
            started_at=started_at,
        )
