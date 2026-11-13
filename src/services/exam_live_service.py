from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from src.core.exceptions import NotFoundError
from src.core.uow import IUnitOfWork
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam_live import (
    ExamLiveExamRead,
    ExamLiveReason,
    ExamLiveSnapshotRead,
    ExamLiveWindowRead,
)
from src.services.exam_queue_service import ExamQueueService
from src.services.exam_service import ExamService

SNAPSHOT_RETRIES = 3


class ExamLiveService:
    def __init__(
        self,
        uow: IUnitOfWork,
        *,
        exams: ExamRepository | None = None,
        exam_service: ExamService | None = None,
        queue: ExamQueueService | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        self._uow = uow
        self._exams = exams or ExamRepository(uow)
        self._exam_service = exam_service or ExamService(
            self._exams,
            ProjectTypeQuestionRepository(uow),
        )
        self._queue = queue or ExamQueueService(
            ExamRegistrationRepository(uow),
            ExamAttemptRepository(uow),
            self._exams,
            self._exam_service,
            clock=clock or (lambda: datetime.now(UTC)),
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    async def check_read_access(self, workspace_id: int, exam_id: int, user):
        return await self._exam_service.read_access(workspace_id, exam_id, user)

    async def snapshot(
        self,
        workspace_id: int,
        exam_id: int,
        user=None,
        *,
        reason: ExamLiveReason,
        changed: tuple[str, ...] | list[str] = (),
        check_access: bool = True,
    ) -> ExamLiveSnapshotRead:
        if check_access:
            if user is None:
                raise NotFoundError("Exam not found")
            exam, _writer = await self._exam_service.read_access(workspace_id, exam_id, user)
        else:
            exam = await self._exams.get_scoped(workspace_id, exam_id)
            if exam is None or exam.status == "draft":
                raise NotFoundError("Exam not found")
        stale = False
        queue = None
        stream_seq = None
        for attempt_number in range(SNAPSHOT_RETRIES):
            stream_seq_before = await self._exams.event_seq(workspace_id, exam_id)
            if stream_seq_before is None:
                raise NotFoundError("Exam not found")
            queue = await self._queue.read(workspace_id, exam_id, user)
            stream_seq_after = await self._exams.event_seq(workspace_id, exam_id)
            if stream_seq_after is None:
                raise NotFoundError("Exam not found")
            stream_seq = stream_seq_after
            stale = queue.eta_stale or stream_seq_before != stream_seq_after
            if not stale:
                break
            if attempt_number == SNAPSHOT_RETRIES - 1:
                break
        if queue is None or stream_seq is None:
            raise NotFoundError("Exam not found")

        windows: list[ExamLiveWindowRead] = []
        for item in queue.items:
            attempt = item.attempt
            if attempt is None or attempt.assessment_window is None:
                continue
            window = attempt.assessment_window
            windows.append(
                ExamLiveWindowRead(
                    attempt_id=attempt.id,
                    registration_id=item.registration_id,
                    project_id=item.project_id,
                    project_type_id=item.project_type_id,
                    opened_at=window.opened_at,
                    closes_at=window.closes_at,
                    settings_version=window.settings_version,
                    state="open" if queue.server_now < window.closes_at else "closed",
                )
            )

        return ExamLiveSnapshotRead(
            reason=reason,
            stream_seq=stream_seq,
            server_now=queue.server_now,
            stale=stale,
            changed=sorted({change for change in changed if change in _EXAM_LIVE_CHANGES}),
            exam=ExamLiveExamRead(
                id=exam.id,
                workspace_id=exam.workspace_id,
                status=exam.status,
                settings_version=queue.settings_version,
            ),
            queue=queue,
            assessment_windows=windows,
        )


_EXAM_LIVE_CHANGES = {"queue", "attempt", "settings", "window", "exam"}
