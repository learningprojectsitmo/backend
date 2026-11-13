from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.core.exceptions import NotFoundError
from src.schema.exam_attempt import AttemptRead, AttemptWindowRead
from src.schema.exam_live import ExamLiveSnapshotRead
from src.schema.exam_queue import QueueEtaRead, QueueItemRead, QueueRead
from src.services.exam_live_service import ExamLiveService

NOW = datetime(2026, 11, 30, 14, 0, tzinfo=UTC)


def attempt(*, attempt_id: int = 31, window: AttemptWindowRead | None = None) -> AttemptRead:
    return AttemptRead(
        id=attempt_id,
        workspace_id=7,
        exam_id=12,
        registration_id=91,
        project_id=42,
        project_type_id=8,
        status="finished" if window else "questions",
        version=3,
        settings_version=2,
        started_at=NOW,
        phase_started_at=NOW,
        phase_deadline=NOW,
        paused_at=None,
        postponed_at=None,
        postponed_phase=None,
        paused_seconds=0,
        finished_at=NOW if window else None,
        created_by=17,
        created_at=NOW,
        updated_at=NOW,
        remaining_seconds=0 if window else 180,
        server_now=NOW,
        assessment_window=window,
    )


def window(*, closes_at: datetime) -> AttemptWindowRead:
    return AttemptWindowRead(opened_at=NOW, closes_at=closes_at, settings_version=2, project_type_id=8)


def queue(*, items: list[QueueItemRead] | None = None, now: datetime = NOW) -> QueueRead:
    return QueueRead(
        queue_revision=17,
        server_now=now,
        settings_version=3,
        eta_stale=False,
        items=items or [],
        eta=QueueEtaRead(current=None, items=[]),
    )


def service(*, exam_status: str = "published", seq_values: list[int] | None = None, read: QueueRead | None = None):
    exams = SimpleNamespace(event_seq=AsyncMock(side_effect=seq_values or [5, 5]))
    exam_service = SimpleNamespace(
        read_access=AsyncMock(
            return_value=(
                SimpleNamespace(id=12, workspace_id=7, status=exam_status),
                exam_status == "published",
            )
        )
    )
    queue_service = SimpleNamespace(read=AsyncMock(return_value=read or queue()))
    return ExamLiveService(
        SimpleNamespace(),
        exams=exams,
        exam_service=exam_service,
        queue=queue_service,
        clock=lambda: NOW,
    )


async def test_snapshot_nests_http_queue_and_exposes_only_window_metadata():
    opened = window(closes_at=datetime(2026, 11, 30, 14, 3, tzinfo=UTC))
    item = QueueItemRead(
        registration_id=91,
        project_id=42,
        project_type_id=8,
        slot_id=None,
        planned_start_at=None,
        planned_end_at=None,
        position=None,
        state="finished",
        registration_version=2,
        started_at=NOW,
        attempt=attempt(window=opened),
    )
    http_snapshot = queue(items=[item])
    svc = service(read=http_snapshot)

    snapshot = await svc.snapshot(7, 12, SimpleNamespace(id=7), reason="connected")

    assert isinstance(snapshot, ExamLiveSnapshotRead)
    assert snapshot.queue is http_snapshot
    assert snapshot.server_now == snapshot.queue.server_now
    assert snapshot.stream_seq == 5
    assert snapshot.stale is False
    assert snapshot.reason == "connected"
    assert snapshot.exam == snapshot.exam.model_validate(
        {"id": 12, "workspace_id": 7, "status": "published", "settings_version": 3}
    )
    assert len(snapshot.assessment_windows) == 1
    live_window = snapshot.assessment_windows[0]
    assert (live_window.attempt_id, live_window.registration_id) == (31, 91)
    assert (live_window.project_id, live_window.project_type_id) == (42, 8)
    assert live_window.closes_at == opened.closes_at
    assert live_window.state == "open"
    dumped = snapshot.model_dump()
    assert "admitted" not in dumped["assessment_windows"][0]
    assert "excluded" not in dumped["assessment_windows"][0]
    assert "can_submit" not in dumped["assessment_windows"][0]


async def test_snapshot_marks_closed_window_by_absolute_server_time():
    closed = window(closes_at=datetime(2026, 11, 30, 13, 58, tzinfo=UTC))
    item = QueueItemRead(
        registration_id=91,
        project_id=42,
        project_type_id=8,
        slot_id=None,
        planned_start_at=None,
        planned_end_at=None,
        position=None,
        state="finished",
        registration_version=2,
        started_at=NOW,
        attempt=attempt(window=closed),
    )

    snapshot = await service(read=queue(items=[item])).snapshot(7, 12, SimpleNamespace(id=7), reason="changed")

    assert snapshot.assessment_windows[0].state == "closed"


async def test_snapshot_retries_until_stream_seq_is_stable():
    svc = service(seq_values=[5, 6, 6, 6])

    snapshot = await svc.snapshot(
        7, 12, SimpleNamespace(id=7), reason="changed", changed=("attempt", "queue", "attempt")
    )

    assert snapshot.stream_seq == 6
    assert snapshot.stale is False
    assert snapshot.changed == ["attempt", "queue"]
    assert svc._exams.event_seq.await_count == 4


async def test_snapshot_reports_stale_after_three_unstable_reads():
    svc = service(seq_values=[1, 2, 3, 4, 5, 6])

    snapshot = await svc.snapshot(7, 12, SimpleNamespace(id=7), reason="changed")

    assert snapshot.stale is True
    assert snapshot.stream_seq == 6


async def test_snapshot_keeps_queue_eta_stale_flag():
    http_snapshot = queue()
    http_snapshot.eta_stale = True
    svc = service(read=http_snapshot, seq_values=[5, 5, 5, 5, 5, 5])

    snapshot = await svc.snapshot(7, 12, SimpleNamespace(id=7), reason="resync")

    assert snapshot.queue.eta_stale is True
    assert snapshot.stale is True


async def test_snapshot_propagates_hidden_or_foreign_exam():
    svc = service()
    svc._exam_service.read_access = AsyncMock(side_effect=NotFoundError("Exam not found"))

    with pytest.raises(NotFoundError):
        await svc.snapshot(7, 12, SimpleNamespace(id=7), reason="connected")
