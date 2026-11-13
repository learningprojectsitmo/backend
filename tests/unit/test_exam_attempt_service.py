from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.model.exam_attempt import ExamAttempt
from src.services.exam_attempt_mapping import remaining_seconds

NOW = datetime(2026, 11, 30, 7, 0, tzinfo=UTC)


def attempt(**overrides) -> ExamAttempt:
    values = {
        "id": 1,
        "workspace_id": 7,
        "exam_id": 12,
        "registration_id": 91,
        "project_id": 42,
        "project_type_id": 8,
        "status": "speaking",
        "version": 1,
        "settings_version": 1,
        "started_at": NOW,
        "phase_started_at": NOW,
        "phase_deadline": NOW + timedelta(minutes=7),
        "paused_at": None,
        "paused_seconds": 0,
        "finished_at": None,
        "created_by": 17,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return ExamAttempt(**values)


def test_remaining_floors_sub_second_overrun_to_negative():
    deadline = NOW + timedelta(minutes=7)
    row = attempt(phase_deadline=deadline)
    assert remaining_seconds(row, deadline + timedelta(seconds=0.5)) == -1
    assert remaining_seconds(row, deadline) == 0
    assert remaining_seconds(row, deadline - timedelta(seconds=1)) == 1


def test_remaining_is_frozen_during_postponement():
    row = attempt(
        status="postponed",
        postponed_at=NOW + timedelta(minutes=2),
        postponed_phase="speaking",
    )
    assert remaining_seconds(row, NOW + timedelta(minutes=30)) == 300


def test_remaining_is_frozen_during_pause_and_zero_after_finish():
    deadline = NOW + timedelta(minutes=7)
    paused = attempt(phase_deadline=deadline, paused_at=NOW + timedelta(minutes=3))
    assert remaining_seconds(paused, NOW + timedelta(minutes=6)) == 240
    finished = attempt(phase_deadline=deadline, status="finished", finished_at=NOW)
    assert remaining_seconds(finished, NOW + timedelta(hours=1)) == 0
