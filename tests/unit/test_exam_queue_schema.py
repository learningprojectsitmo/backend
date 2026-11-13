from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.schema.exam_attempt import AttemptRead, AttemptRestart
from src.schema.exam_queue import QueueCommand, QueueItemRead, QueuePlace, QueueRead, QueueReason

NOW = datetime(2026, 11, 30, 7, 0, tzinfo=UTC)


def attempt(**overrides):
    data = {
        "id": 31,
        "workspace_id": 7,
        "exam_id": 12,
        "registration_id": 91,
        "project_id": 42,
        "project_type_id": 8,
        "status": "postponed",
        "version": 3,
        "settings_version": 1,
        "started_at": NOW,
        "phase_started_at": NOW,
        "phase_deadline": NOW,
        "paused_at": None,
        "postponed_at": NOW,
        "postponed_phase": "speaking",
        "paused_seconds": 0,
        "finished_at": None,
        "created_by": 17,
        "created_at": NOW,
        "updated_at": NOW,
        "remaining_seconds": 120,
        "server_now": NOW,
        "assessment_window": None,
    }
    data.update(overrides)
    return AttemptRead.model_validate(data)


def item(**overrides):
    data = {
        "registration_id": 91,
        "project_id": 42,
        "project_type_id": 8,
        "slot_id": None,
        "planned_start_at": None,
        "planned_end_at": None,
        "position": 1,
        "state": "postponed",
        "registration_version": 3,
        "started_at": NOW,
        "attempt": attempt(),
    }
    data.update(overrides)
    return QueueItemRead.model_validate(data)


@pytest.mark.parametrize("position", [None, 1, 2**31 - 1])
def test_place_accepts_null_or_positive_position(position):
    assert QueuePlace(expected_version=1, position=position).position == position


@pytest.mark.parametrize("position", [True, 0, -1, 2**31, "2"])
def test_place_rejects_invalid_position(position):
    with pytest.raises(ValidationError):
        QueuePlace(expected_version=1, position=position)


@pytest.mark.parametrize("body", [{"expected_version": 1, "extra": 1}, {"expected_version": True}, {"position": 1}])
def test_place_body_is_strict(body):
    with pytest.raises(ValidationError):
        QueuePlace.model_validate(body)


def test_next_command_is_strict():
    assert QueueCommand(expected_version=2).expected_version == 2
    with pytest.raises(ValidationError):
        QueueCommand.model_validate({"expected_version": 2, "position": 1})


@pytest.mark.parametrize("reason", ["Причина", "  Проектор  "])
def test_reason_is_trimmed(reason):
    parsed = QueueReason(expected_version=1, reason=reason)
    assert parsed.reason == reason.strip()


@pytest.mark.parametrize("reason", ["", "   ", "a\x00b", None, 5])
def test_reason_is_required_and_rejects_nul(reason):
    with pytest.raises(ValidationError):
        QueueReason(expected_version=1, reason=reason)


def test_reason_length_limit():
    QueueReason(expected_version=1, reason="x" * 1000)
    with pytest.raises(ValidationError):
        QueueReason(expected_version=1, reason="x" * 1001)


def test_restart_reason_is_optional_but_strict():
    assert AttemptRestart(expected_version=1).reason is None
    assert AttemptRestart(expected_version=1, reason="  Продолжаем ").reason == "Продолжаем"
    with pytest.raises(ValidationError):
        AttemptRestart(expected_version=1, reason="a\x00b")
    with pytest.raises(ValidationError):
        AttemptRestart(expected_version=1, reason="")


def test_queue_read_serializes_waiting_and_finished_items():
    waiting = item(
        registration_id=92,
        position=2,
        state="waiting",
        attempt=None,
        started_at=None,
    )
    finished = item(
        state="finished",
        position=None,
        attempt=attempt(status="finished", finished_at=NOW, postponed_at=None, postponed_phase=None),
    )
    payload = QueueRead(queue_revision=5, server_now=NOW, items=[waiting, finished]).model_dump()
    assert payload["items"][0]["attempt"] is None
    assert payload["items"][1]["attempt"]["status"] == "finished"
    assert payload["queue_revision"] == 5


def test_item_state_and_position_are_strict():
    with pytest.raises(ValidationError):
        item(state="cancelled")
    with pytest.raises(ValidationError):
        item(position=0)
