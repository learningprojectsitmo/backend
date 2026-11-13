from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.schema.exam_attempt import (
    AttemptCommand,
    AttemptPause,
    AttemptRead,
    AttemptStart,
    AttemptWindowRead,
    CurrentAttemptRead,
)

NOW = datetime(2026, 11, 30, 7, 0, tzinfo=UTC)


@pytest.mark.parametrize("value", [True, False, 0, -1, "1", 1.5, None, 2**31])
def test_start_requires_positive_pg_integer_registration(value):
    with pytest.raises(ValidationError):
        AttemptStart(registration_id=value, expected_version=1)


@pytest.mark.parametrize("value", [True, 0, -1, "2", None, 2**31])
def test_start_requires_positive_pg_integer_expected_version(value):
    with pytest.raises(ValidationError):
        AttemptStart(registration_id=3, expected_version=value)


def test_start_forbids_missing_expected_version_and_extra_client_fields():
    with pytest.raises(ValidationError):
        AttemptStart(registration_id=3)
    for field, value in [
        ("status", "finished"),
        ("version", 2),
        ("started_at", "2026-11-30T07:00:00Z"),
        ("server_now", "2026-11-30T07:00:00Z"),
        ("actor_id", 7),
        ("attempt_id", 1),
    ]:
        with pytest.raises(ValidationError):
            AttemptStart.model_validate({"registration_id": 3, "expected_version": 1, field: value})


def test_command_requires_positive_expected_version():
    with pytest.raises(ValidationError):
        AttemptCommand()
    with pytest.raises(ValidationError):
        AttemptCommand(expected_version=0)
    assert AttemptCommand(expected_version=2).expected_version == 2


def test_pause_reason_is_optional_and_trimmed():
    assert AttemptPause(expected_version=1).reason is None
    assert AttemptPause(expected_version=1, reason="  Технический перерыв  ").reason == "Технический перерыв"


@pytest.mark.parametrize("reason", ["", "   ", "x" * 1001, "a\x00b"])
def test_pause_rejects_blank_nul_or_oversized_reason(reason):
    with pytest.raises(ValidationError):
        AttemptPause(expected_version=1, reason=reason)


def test_pause_rejects_extra_fields():
    with pytest.raises(ValidationError):
        AttemptPause.model_validate({"expected_version": 1, "reason": "ok", "actor_id": 4})


def payload(**overrides):
    data = {
        "id": 31,
        "workspace_id": 7,
        "exam_id": 12,
        "registration_id": 91,
        "project_id": 42,
        "project_type_id": 8,
        "status": "speaking",
        "version": 1,
        "settings_version": 3,
        "started_at": NOW,
        "phase_started_at": NOW,
        "phase_deadline": NOW,
        "paused_at": None,
        "paused_seconds": 0,
        "finished_at": None,
        "created_by": 17,
        "created_at": NOW,
        "updated_at": NOW,
        "remaining_seconds": 420,
        "server_now": NOW,
        "assessment_window": None,
    }
    data.update(overrides)
    return data


def test_attempt_read_carries_server_state_and_optional_window():
    attempt = AttemptRead.model_validate(payload())
    assert (attempt.status, attempt.remaining_seconds, attempt.assessment_window) == ("speaking", 420, None)
    assert CurrentAttemptRead(attempt=None).attempt is None

    window = AttemptWindowRead(
        opened_at=NOW,
        closes_at=NOW,
        settings_version=3,
        project_type_id=8,
    )
    finished = AttemptRead.model_validate(
        payload(status="finished", finished_at=NOW, assessment_window=window, remaining_seconds=0)
    )
    assert finished.assessment_window is not None
    assert finished.assessment_window.closes_at == NOW


@pytest.mark.parametrize("status", ["paused", "running", ""])
def test_attempt_read_rejects_unknown_status(status):
    with pytest.raises(ValidationError):
        AttemptRead.model_validate(payload(status=status))


def test_attempt_read_forbids_extra_fields():
    with pytest.raises(ValidationError):
        AttemptRead.model_validate(payload(actor_id=3))
