from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.schema.exam_queue import EtaCurrentRead, EtaItemRead, QueueEtaRead, QueueRead
from src.services.exam_eta import (
    EtaCurrentState,
    EtaTiming,
    EtaWaitingState,
    build_queue_eta,
    current_slot_seconds,
    full_slot_seconds,
    waiting_slot_seconds,
)

NOW = datetime(2026, 11, 30, 14, 0, tzinfo=UTC)


def timing(presentation: int = 300, questions: int = 240, transition: int = 60) -> EtaTiming:
    return EtaTiming(presentation_seconds=presentation, questions_seconds=questions, transition_seconds=transition)


def current(
    *,
    status: str = "questions",
    paused: bool = False,
    phase_remaining: int = 180,
    overdue: int = 0,
    settings_version: int = 2,
    t: EtaTiming | None = None,
) -> EtaCurrentState:
    return EtaCurrentState(
        registration_id=92,
        attempt_id=31,
        status=status,  # type: ignore[arg-type]
        paused=paused,
        phase_remaining_seconds=phase_remaining,
        overdue_seconds=overdue,
        settings_version=settings_version,
        timing=t or timing(),
    )


def waiting(
    registration_id: int,
    position: int,
    *,
    state: str = "waiting",
    postponed_phase: str | None = None,
    t: EtaTiming | None = None,
) -> EtaWaitingState:
    return EtaWaitingState(
        registration_id=registration_id,
        position=position,
        state=state,  # type: ignore[arg-type]
        timing=t or timing(),
        postponed_phase=postponed_phase,  # type: ignore[arg-type]
    )


def test_reference_example_4_plus_10_is_14():
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=NOW - timedelta(minutes=30),
        current=current(phase_remaining=180, t=timing(300, 240, 60)),
        waiting=[waiting(91, 1), waiting(90, 2)],
    )

    assert eta.current is not None
    assert eta.current.slot_remaining_seconds == 240
    assert [(item.registration_id, item.eta_seconds) for item in eta.items] == [(91, 240), (90, 840)]
    assert eta.items[0].eta_at == NOW + timedelta(minutes=4)
    assert eta.items[1].eta_at == NOW + timedelta(minutes=14)
    assert eta.items[0].certainty == "certain"
    assert eta.items[0].reason is None


def test_questions_phase_uses_remaining_and_transition_only():
    # questions_minutes is not added again: current phase 3 min + transition 1.
    assert current_slot_seconds(current(status="questions", phase_remaining=180)) == 240


def test_speaking_phase_includes_questions_and_transition():
    state = current(status="speaking", phase_remaining=60, t=timing(420, 420, 60))
    assert current_slot_seconds(state) == 540


def test_questions_zero_still_uses_transition():
    state = current(status="speaking", phase_remaining=60, t=timing(420, 0, 60))
    assert current_slot_seconds(state) == 120


def test_full_slot_includes_transition_once():
    assert full_slot_seconds(timing()) == 600


def test_no_current_first_waiting_zero():
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=NOW - timedelta(minutes=30),
        current=None,
        waiting=[waiting(91, 1), waiting(90, 2)],
    )

    assert eta.current is None
    assert [(item.registration_id, item.eta_seconds) for item in eta.items] == [(91, 0), (90, 600)]
    assert eta.items[0].certainty == "certain"
    assert eta.items[0].reason is None


def test_before_start_floor():
    starts_at = NOW + timedelta(minutes=10)
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=starts_at,
        current=None,
        waiting=[waiting(91, 1), waiting(90, 2)],
    )

    assert [(item.registration_id, item.eta_seconds) for item in eta.items] == [(91, 600), (90, 1200)]
    assert eta.items[0].eta_at == starts_at
    assert eta.items[0].reason == "before_start"
    assert eta.items[0].certainty == "certain"


def test_started_exam_ignores_the_starts_at_floor():
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=NOW + timedelta(minutes=10),
        current=None,
        waiting=[waiting(91, 1)],
        exam_started=True,
    )
    assert eta.items[0].eta_seconds == 0
    assert eta.items[0].reason is None


def test_empty_queue():
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=NOW,
        current=current(),
        waiting=[],
    )
    assert eta.items == []
    assert eta.current is not None


def test_positioned_postponed_uses_full_restart_slot():
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=NOW,
        current=None,
        waiting=[
            waiting(91, 1, state="postponed", postponed_phase="speaking"),
            waiting(90, 2),
        ],
    )
    assert [(item.registration_id, item.eta_seconds) for item in eta.items] == [(91, 0), (90, 600)]


def test_postponed_questions_uses_questions_and_transition():
    waiting_state = waiting(91, 1, state="postponed", postponed_phase="questions")
    assert waiting_slot_seconds(waiting_state) == 300


def test_paused_current_is_lower_bound():
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=NOW,
        current=current(paused=True, phase_remaining=180),
        waiting=[waiting(91, 1), waiting(90, 2)],
    )

    assert eta.current is not None
    assert eta.current.paused is True
    assert eta.current.slot_remaining_seconds == 240
    assert eta.items[0].eta_seconds == 240
    assert {item.certainty for item in eta.items} == {"lower_bound"}
    assert {item.reason for item in eta.items} == {"paused"}


def test_overdue_current_is_lower_bound_zero():
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=NOW,
        current=current(phase_remaining=0, overdue=120),
        waiting=[waiting(91, 1), waiting(90, 2)],
    )

    assert eta.current is not None
    assert eta.current.slot_remaining_seconds == 0
    assert eta.current.overdue_seconds == 120
    assert eta.items[0].eta_seconds == 0
    assert eta.items[1].eta_seconds == 600
    assert {item.certainty for item in eta.items} == {"lower_bound"}
    assert {item.reason for item in eta.items} == {"overdue"}
    assert all(item.eta_seconds >= 0 for item in eta.items)


def test_pause_has_priority_over_overdue_reason():
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=NOW,
        current=current(paused=True, phase_remaining=0, overdue=120),
        waiting=[waiting(91, 1)],
    )
    assert eta.items[0].reason == "paused"
    assert eta.items[0].certainty == "lower_bound"


def test_eta_never_negative():
    eta = build_queue_eta(
        now=NOW,
        exam_starts_at=NOW,
        current=None,
        waiting=[waiting(91, 1)],
    )
    assert eta.items[0].eta_seconds == 0
    assert eta.items[0].eta_at == NOW


def test_contract_dto_fields():
    eta = QueueEtaRead(current=None, items=[])
    assert eta.current is None
    assert eta.items == []
    # Contract version is part of the read envelope, not the ETA block.
    assert "contract_version" in QueueRead.model_fields
    assert "settings_version" in QueueRead.model_fields
    assert "eta_stale" in QueueRead.model_fields
    assert "eta" in QueueRead.model_fields
    assert EtaCurrentRead.model_fields["slot_remaining_seconds"]
    assert EtaItemRead.model_fields["eta_at"]
