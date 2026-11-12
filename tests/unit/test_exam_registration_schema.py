from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.schema.exam_registration import RegistrationCancel, RegistrationCreate, RegistrationMove, SlotBatchCreate


@pytest.mark.parametrize("value", [True, False, 0, -1, "1", 1.5, None])
def test_project_identifier_rejects_non_positive_integer(value):
    with pytest.raises(ValidationError):
        RegistrationCreate(project_id=value)


@pytest.mark.parametrize(
    "field,value",
    [("actor_id", 1), ("source", "organizer"), ("status", "active"), ("created_at", "2026-11-01T10:00:00Z")],
)
def test_client_cannot_supply_server_identity_or_state(field, value):
    with pytest.raises(ValidationError):
        RegistrationCreate.model_validate({"project_id": 3, field: value})


@pytest.mark.parametrize("value", [True, 0, -1, "2", None])
def test_cancel_requires_positive_integer_expected_version(value):
    with pytest.raises(ValidationError):
        RegistrationCancel(expected_version=value, reason="Новое расписание")


@pytest.mark.parametrize("reason", ["", "  ", "x" * 1001, None])
def test_cancel_requires_bounded_nonempty_reason(reason):
    with pytest.raises(ValidationError):
        RegistrationCancel(expected_version=1, reason=reason)


def test_move_preserves_target_and_trims_reason():
    data = RegistrationMove(expected_version=2, target_exam_id=8, target_slot_id=4, reason="  Другая дата  ")
    assert data.reason == "Другая дата"
    assert (data.target_exam_id, data.target_slot_id) == (8, 4)
    assert RegistrationCreate(project_id=3).slot_id is None


def slot(start="2026-11-30T10:00:00+03:00", end="2026-11-30T10:15:00+03:00"):
    return {"starts_at": start, "ends_at": end}


def test_slot_times_are_utc_and_adjacent_intervals_are_supported():
    data = SlotBatchCreate(slots=[slot(), slot("2026-11-30T10:15:00+03:00", "2026-11-30T10:30:00+03:00")])
    assert data.slots[0].starts_at == datetime(2026, 11, 30, 7, tzinfo=UTC)
    assert data.slots[0].ends_at == data.slots[1].starts_at


@pytest.mark.parametrize(
    "slots",
    [
        [],
        [slot()] * 101,
        [slot(), slot()],
        [slot(end="2026-11-30T10:00:00+03:00")],
        [slot(start="2026-11-30T10:00:00")],
        [slot(start="0001-01-01T00:00:00+14:00")],
        [slot(end="2026-11-30T09:00:00+03:00")],
    ],
)
def test_slot_batch_rejects_invalid_intervals(slots):
    with pytest.raises(ValidationError):
        SlotBatchCreate(slots=slots)
