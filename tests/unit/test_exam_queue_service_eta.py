from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.schema.exam_queue import QueueItemRead
from src.services.exam_queue_service import ExamQueueService

NOW = datetime(2026, 11, 30, 14, 0, tzinfo=UTC)


def settings(version: int, presentation: int, questions: int, transition: int):
    return SimpleNamespace(
        version=version,
        starts_at=NOW,
        presentation_minutes=presentation,
        questions_minutes=questions,
        transition_minutes=transition,
    )


def registration(
    registration_id: int,
    *,
    position: int | None,
    hold: str | None = None,
    started_at: datetime | None = None,
):
    return SimpleNamespace(
        id=registration_id,
        project_id=1000 + registration_id,
        project_type_id_at_registration=7,
        slot_id=None,
        queue_position=position,
        queue_hold=hold,
        status="active",
        version=1,
        started_at=started_at,
        updated_at=NOW,
    )


def attempt(
    registration_id: int,
    *,
    status: str = "speaking",
    version: int = 1,
    settings_version: int = 1,
    paused_at: datetime | None = None,
    postponed_at: datetime | None = None,
    postponed_phase: str | None = None,
    deadline: datetime | None = None,
):
    return SimpleNamespace(
        id=30 + registration_id,
        registration_id=registration_id,
        status=status,
        version=version,
        settings_version=settings_version,
        paused_at=paused_at,
        postponed_at=postponed_at,
        postponed_phase=postponed_phase,
        phase_deadline=deadline or NOW + timedelta(seconds=60),
        finished_at=None,
    )


class FakeExamService:
    async def require_read_access(self, _workspace_id, _exam_id, _user):
        return None


class FakeExamRepository:
    def __init__(self, exam, revisions):
        self.exam = exam
        self.revisions = revisions
        self.get_scoped_calls = 0
        self.revision_state_value = (exam.queue_revision, exam.current_settings_version)
        self.revision_state_calls = 0

    async def get_scoped(self, _workspace_id, _exam_id, *, lock=False):
        del lock
        self.get_scoped_calls += 1
        return self.exam

    async def get_revision(self, _exam_id, version):
        return self.revisions.get(version)

    async def revision_state(self, _workspace_id, _exam_id):
        self.revision_state_calls += 1
        return self.revision_state_value


class FakeRegistrationRepository:
    def __init__(self, rows):
        self.rows = rows

    async def list_active(self, _workspace_id, _exam_id):
        return list(self.rows)

    async def all_slots(self, _exam_id):
        return []


class FakeAttemptRepository:
    def __init__(self, attempts):
        self.attempts = attempts
        self.version_map_value = {attempt.id: attempt.version for attempt in attempts.values()}

    async def for_exam(self, _workspace_id, _exam_id, *, lock=False):
        del lock
        return dict(self.attempts)

    async def version_map(self, _workspace_id, _exam_id):
        return dict(self.version_map_value)


def make_service(*, rows, attempts, revisions, current_version=1, revision_state=None, version_map=None):
    exam = SimpleNamespace(
        id=12,
        workspace_id=7,
        status="published",
        queue_revision=17,
        current_settings_version=current_version,
    )
    exams = FakeExamRepository(exam, revisions)
    if revision_state is not None:
        exams.revision_state_value = revision_state
    attempts_repo = FakeAttemptRepository(attempts)
    if version_map is not None:
        attempts_repo.version_map_value = version_map
    service = ExamQueueService(
        FakeRegistrationRepository(rows),
        attempts_repo,
        exams,
        FakeExamService(),
        clock=lambda: NOW,
    )

    async def fake_item(reg, current_attempt, slot, now):
        if current_attempt is not None:
            state = "running" if current_attempt.status in ("speaking", "questions") else current_attempt.status
        elif reg.queue_hold is not None:
            state = reg.queue_hold
        else:
            state = "waiting"
        return QueueItemRead(
            registration_id=reg.id,
            project_id=reg.project_id,
            project_type_id=reg.project_type_id_at_registration,
            slot_id=None,
            planned_start_at=None,
            planned_end_at=None,
            position=reg.queue_position,
            state=state,
            registration_version=1,
            started_at=reg.started_at,
            attempt=None,
        )

    service._item = fake_item  # type: ignore[method-assign]
    return service, exams, attempts_repo


@pytest.mark.asyncio
async def test_read_retries_when_attempt_version_changes_without_queue_revision():
    running = attempt(92, status="questions", deadline=NOW + timedelta(seconds=180))
    service, exams, attempts = make_service(
        rows=[registration(92, position=None), registration(91, position=1)],
        attempts={92: running},
        revisions={1: settings(1, 7, 7, 1)},
    )

    for_exam_calls = 0
    original_for_exam = attempts.for_exam

    async def changing_for_exam(workspace_id, exam_id, *, lock=False):
        nonlocal for_exam_calls
        for_exam_calls += 1
        if for_exam_calls > 1:
            running.version = 2
        return await original_for_exam(workspace_id, exam_id, lock=lock)

    attempts.for_exam = changing_for_exam  # type: ignore[method-assign]
    attempts.version_map_value = {running.id: 2}
    result = await service.read(7, 12, SimpleNamespace(id=17))

    assert result.eta_stale is False
    assert result.eta.current is not None
    assert exams.get_scoped_calls == 2
    assert result.eta.items[0].eta_seconds == 240  # 3 min phase + 1 min transition


@pytest.mark.asyncio
async def test_read_marks_stale_after_three_unstable_snapshots():
    running = attempt(92)
    service, exams, _attempts = make_service(
        rows=[registration(92, position=None)],
        attempts={92: running},
        revisions={1: settings(1, 7, 7, 1)},
    )
    exams.revision_state_value = (18, 1)  # queue moved every time

    result = await service.read(7, 12, SimpleNamespace(id=17))

    assert result.eta_stale is True
    assert exams.get_scoped_calls == 3
    assert result.eta.current is not None


@pytest.mark.asyncio
async def test_read_uses_start_settings_for_current_and_current_settings_for_waiting():
    running = attempt(92, settings_version=1, deadline=NOW + timedelta(seconds=60))
    service, _exams, _attempts = make_service(
        rows=[registration(92, position=None), registration(91, position=1)],
        attempts={92: running},
        revisions={1: settings(1, 7, 7, 1), 2: settings(2, 5, 5, 5)},
        current_version=2,
    )

    result = await service.read(7, 12, SimpleNamespace(id=17))

    assert result.settings_version == 2
    assert result.eta.current is not None
    assert result.eta.current.settings_version == 1
    assert result.eta.current.slot_remaining_seconds == 60 + 7 * 60 + 60  # v1 speaking + questions + transition
    assert result.eta.items[0].eta_seconds == 60 + 7 * 60 + 60
    # The waiting team's slot is from v2: 5 + 5 + 5 minutes.
    assert result.eta.items[0].eta_at == NOW + timedelta(seconds=60 + 7 * 60 + 60)


@pytest.mark.asyncio
async def test_read_skips_finished_no_show_and_damaged_rows():
    finished = attempt(90, status="finished")
    postponed = attempt(88, status="postponed", postponed_at=NOW, postponed_phase="questions")
    service, _exams, _attempts = make_service(
        rows=[
            registration(91, position=1),
            registration(90, position=2),
            registration(89, position=3, hold="no_show"),
            registration(88, position=None),
        ],
        attempts={90: finished, 88: postponed},
        revisions={1: settings(1, 7, 7, 1)},
    )

    result = await service.read(7, 12, SimpleNamespace(id=17))

    assert [item.registration_id for item in result.eta.items] == [91]
    assert result.eta.current is None


@pytest.mark.asyncio
async def test_read_before_start():
    service, _exams, _attempts = make_service(
        rows=[registration(91, position=1)],
        attempts={},
        revisions={1: SimpleNamespace(
            version=1,
            starts_at=NOW + timedelta(minutes=10),
            presentation_minutes=7,
            questions_minutes=7,
            transition_minutes=1,
        )},
    )

    result = await service.read(7, 12, SimpleNamespace(id=17))

    assert result.eta.current is None
    assert result.eta.items[0].eta_seconds == 600
    assert result.eta.items[0].reason == "before_start"
