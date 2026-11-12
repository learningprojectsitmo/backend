from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from itertools import pairwise

from src.core.exceptions import BusinessLogicError, NotFoundError
from src.model.exam_registration import ExamSlot
from src.model.user import User
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam_registration import SlotBatchCreate, SlotListRead, SlotRead
from src.services.exam_service import ExamService


class ExamRegistrationService:
    def __init__(
        self,
        repository: ExamRegistrationRepository,
        exam_service: ExamService,
        questions: ProjectTypeQuestionRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repository = repository
        self._exam_service = exam_service
        self._questions = questions
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
