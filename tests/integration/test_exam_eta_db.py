from __future__ import annotations

from datetime import timedelta

import pytest
import test_exam_registrations_db as registration_cases
from sqlalchemy import select
from test_exam_queue_db import START, attempt_service, queue_service, register

from src.model.exam import Exam
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam import ExamSettingsReplace
from src.schema.exam_attempt import (
    AttemptCommand,
    AttemptPause,
    AttemptPostpone,
    AttemptRestart,
    AttemptStart,
)
from src.schema.exam_queue import QueueCommand, QueuePlace, QueueReason
from src.schema.exam_registration import RegistrationMove, SlotBatchCreate
from src.services.exam_service import ExamService

pytestmark = pytest.mark.integration

seeded = registration_cases.seeded


async def read_eta(s, now=START, exam=0):
    async with s["uow"]() as u:
        return await queue_service(u, now).read(s["workspace"], s["exams"][exam], s["users"]["teacher"])


async def revision(s, exam=0):
    async with s["uow"]() as u:
        return await u.session.scalar(select(Exam.queue_revision).where(Exam.id == s["exams"][exam]))


async def set_settings(s, *, expected_version=1, **overrides):
    async with s["uow"]() as u:
        exams = ExamService(ExamRepository(u), ProjectTypeQuestionRepository(u))
        current = await exams.get(s["workspace"], s["exams"][0], s["users"]["teacher"])
        await exams.replace_settings(
            s["workspace"],
            s["exams"][0],
            ExamSettingsReplace(
                expected_version=expected_version,
                reason="Проверка редакции настроек в ETA",
                configuration=current.configuration.model_copy(update=overrides),
            ),
            s["users"]["teacher"],
        )


async def start(s, registration, now=START):
    async with s["uow"]() as u:
        return await attempt_service(u, now).start(
            s["workspace"],
            s["exams"][0],
            AttemptStart(registration_id=registration.id, expected_version=registration.version),
            s["users"]["teacher"],
        )


async def to_questions(s, attempt, version, now=START):
    async with s["uow"]() as u:
        return await attempt_service(u, now).questions(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=version),
            s["users"]["teacher"],
        )


async def pause_attempt(s, attempt, version, now=START):
    async with s["uow"]() as u:
        return await attempt_service(u, now).pause(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPause(expected_version=version, reason="Перерыв"),
            s["users"]["teacher"],
        )


async def postpone_attempt(s, attempt, version, now=START):
    async with s["uow"]() as u:
        return await attempt_service(u, now).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=version, reason="Проектор"),
            s["users"]["teacher"],
        )


async def restart_attempt(s, attempt, version, now=START):
    async with s["uow"]() as u:
        return await attempt_service(u, now).restart(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptRestart(expected_version=version),
            s["users"]["teacher"],
        )


async def finish_attempt(s, attempt, version, now=START):
    async with s["uow"]() as u:
        return await attempt_service(u, now).finish(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptCommand(expected_version=version),
            s["users"]["teacher"],
        )


async def place(s, registration_id, version, position=None, now=START):
    async with s["uow"]() as u:
        return await queue_service(u, now).place(
            s["workspace"],
            s["exams"][0],
            registration_id,
            QueuePlace(expected_version=version, position=position),
            s["users"]["teacher"],
        )


async def place_next(s, registration_id, version, now=START):
    async with s["uow"]() as u:
        return await queue_service(u, now).next(
            s["workspace"],
            s["exams"][0],
            registration_id,
            QueueCommand(expected_version=version),
            s["users"]["teacher"],
        )


async def postpone_from_queue(s, registration_id, version, now=START):
    async with s["uow"]() as u:
        return await queue_service(u, now).postpone(
            s["workspace"],
            s["exams"][0],
            registration_id,
            QueueReason(expected_version=version, reason="Проектор"),
            s["users"]["teacher"],
        )


async def mark_no_show(s, registration_id, version, now=START):
    async with s["uow"]() as u:
        return await queue_service(u, now).no_show(
            s["workspace"],
            s["exams"][0],
            registration_id,
            QueueReason(expected_version=version, reason="Не пришла"),
            s["users"]["teacher"],
        )


async def reference_example(s):
    """A is answering questions with 3 minutes left and B/C have a 10-minute slot."""
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    a = await register(s, "manager")
    b = await register(s, "manager2")
    c = await register(s, "member")
    attempt, _ = await start(s, a, START - timedelta(minutes=6))
    attempt = await to_questions(s, attempt, attempt.version, START - timedelta(minutes=1))
    return a, b, c, attempt


def slot_batch():
    return SlotBatchCreate(
        slots=[
            {"starts_at": START, "ends_at": START + timedelta(minutes=15)},
            {"starts_at": START + timedelta(minutes=15), "ends_at": START + timedelta(minutes=30)},
            {"starts_at": START + timedelta(minutes=30), "ends_at": START + timedelta(minutes=45)},
        ]
    )


async def test_reference_example_4_plus_10(seeded):
    s = seeded
    a, b, c, attempt = await reference_example(s)

    state = await read_eta(s, START)

    assert state.server_now == START
    assert state.queue_revision == await revision(s)
    current = state.eta.current
    assert current is not None
    assert (current.registration_id, current.attempt_id) == (a.id, attempt.id)
    assert (current.status, current.paused, current.overdue_seconds) == ("questions", False, 0)
    assert (current.phase_remaining_seconds, current.slot_remaining_seconds) == (180, 240)
    assert current.settings_version == attempt.settings_version == 2

    items = state.eta.items
    assert [item.registration_id for item in items] == [b.id, c.id]
    assert [item.position for item in items] == [1, 2]
    assert [item.eta_seconds for item in items] == [240, 840]
    assert [item.eta_at for item in items] == [
        START + timedelta(minutes=4),
        START + timedelta(minutes=14),
    ]
    assert [(item.certainty, item.reason) for item in items] == [("certain", None), ("certain", None)]
    assert items[1].eta_at == state.server_now + timedelta(seconds=items[1].eta_seconds)


async def test_finish_removes_current_from_eta(seeded):
    s = seeded
    _, b, c, attempt = await reference_example(s)
    before = await read_eta(s, START)

    await finish_attempt(s, attempt, attempt.version, START)
    after = await read_eta(s, START)

    assert after.eta.current is None
    assert [item.registration_id for item in after.eta.items] == [b.id, c.id]
    assert [item.eta_seconds for item in after.eta.items] == [0, 600]
    assert after.queue_revision == before.queue_revision + 1


async def test_no_show_removes_team_and_shifts_eta(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    b = await register(s, "manager")
    c = await register(s, "manager2")
    before = await read_eta(s, START)
    assert before.eta.current is None
    assert [item.eta_seconds for item in before.eta.items] == [0, 600]

    await mark_no_show(s, b.id, b.version, START)
    after = await read_eta(s, START)

    assert [item.registration_id for item in after.eta.items] == [c.id]
    assert [item.position for item in after.eta.items] == [1]
    assert [item.eta_seconds for item in after.eta.items] == [0]
    assert after.queue_revision == before.queue_revision + 1


async def test_place_next_returns_team_and_shifts_eta(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    b = await register(s, "manager")
    c = await register(s, "manager2")
    before = await read_eta(s, START)
    assert [item.eta_seconds for item in before.eta.items] == [0, 600]

    placed = await place_next(s, c.id, c.version, START)
    assert placed.item.position == 1
    assert placed.queue_revision == before.queue_revision + 1

    after = await read_eta(s, START)
    assert [item.registration_id for item in after.eta.items] == [c.id, b.id]
    assert [item.eta_seconds for item in after.eta.items] == [0, 600]


async def test_reorder_changes_eta_order(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    b = await register(s, "manager")
    c = await register(s, "manager2")
    before = await read_eta(s, START)
    assert [item.registration_id for item in before.eta.items] == [b.id, c.id]
    assert [item.eta_seconds for item in before.eta.items] == [0, 600]

    reordered = await place(s, b.id, b.version, 2, START)
    assert reordered.queue_revision == before.queue_revision + 1

    after = await read_eta(s, START)
    assert [item.registration_id for item in after.eta.items] == [c.id, b.id]
    assert [item.position for item in after.eta.items] == [1, 2]
    assert [item.eta_seconds for item in after.eta.items] == [0, 600]


async def test_postponed_without_position_does_not_delay(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    c = await register(s, "manager")
    d = await register(s, "manager2")
    before = await read_eta(s, START)
    assert [item.eta_seconds for item in before.eta.items] == [0, 600]

    await postpone_from_queue(s, d.id, d.version, START)
    middle = await read_eta(s, START)
    assert [item.registration_id for item in middle.eta.items] == [c.id]
    assert middle.eta.items[0].eta_seconds == before.eta.items[0].eta_seconds

    await place(s, d.id, d.version + 1, 1, START)
    after = await read_eta(s, START)
    assert [item.registration_id for item in after.eta.items] == [d.id, c.id]
    assert [item.position for item in after.eta.items] == [1, 2]
    assert [item.state for item in after.eta.items] == ["waiting", "waiting"]
    assert [item.eta_seconds for item in after.eta.items] == [0, 600]


async def test_positioned_postponed_uses_full_restart_slot(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    a = await register(s, "manager")
    b = await register(s, "manager2")
    c = await register(s, "member")
    attempt, _ = await start(s, a, START - timedelta(minutes=6))
    attempt = await to_questions(s, attempt, attempt.version, START - timedelta(minutes=1))
    postponed = await postpone_attempt(s, attempt, attempt.version, START)

    await place(s, a.id, a.version + 1, 1, START)
    state = await read_eta(s, START)

    assert state.eta.current is None
    items = state.eta.items
    assert [item.registration_id for item in items] == [a.id, b.id, c.id]
    assert [item.position for item in items] == [1, 2, 3]
    assert [item.state for item in items] == ["postponed", "waiting", "waiting"]
    assert [item.eta_seconds for item in items] == [0, 300, 900]
    assert [item.eta_at for item in items] == [
        START,
        START + timedelta(minutes=5),
        START + timedelta(minutes=15),
    ]
    assert postponed.status == "postponed"


async def test_postponed_attempt_without_position_does_not_delay(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    a = await register(s, "manager")
    b = await register(s, "manager2")
    c = await register(s, "member")
    attempt, _ = await start(s, a, START)
    attempt = await to_questions(s, attempt, attempt.version, START)
    await postpone_attempt(s, attempt, attempt.version, START)

    without_place = await read_eta(s, START)
    assert without_place.eta.current is None
    assert [item.registration_id for item in without_place.eta.items] == [b.id, c.id]
    assert [item.eta_seconds for item in without_place.eta.items] == [0, 600]

    await place(s, a.id, a.version + 1, 1, START)
    after = await read_eta(s, START)
    assert [item.registration_id for item in after.eta.items] == [a.id, b.id, c.id]
    assert [item.state for item in after.eta.items] == ["postponed", "waiting", "waiting"]
    assert [item.eta_seconds for item in after.eta.items] == [0, 300, 900]


async def test_restart_makes_team_current(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    a = await register(s, "manager")
    b = await register(s, "manager2")
    c = await register(s, "member")
    attempt, _ = await start(s, a, START)
    attempt = await to_questions(s, attempt, attempt.version, START)
    postponed = await postpone_attempt(s, attempt, attempt.version, START)
    await place(s, a.id, a.version + 1, 1, START)
    before = await read_eta(s, START)
    assert before.eta.items[0].registration_id == a.id
    assert before.eta.items[0].position == 1

    restarted = await restart_attempt(s, postponed, postponed.version, START)
    assert restarted.id == attempt.id

    after = await read_eta(s, START)
    assert after.eta.current is not None
    assert (after.eta.current.attempt_id, after.eta.current.status) == (attempt.id, "questions")
    assert after.eta.current.slot_remaining_seconds == 300
    assert [item.registration_id for item in after.eta.items] == [b.id, c.id]
    assert [item.eta_seconds for item in after.eta.items] == [300, 900]
    assert all(item.position is None for item in after.items if item.registration_id == a.id)
    assert after.queue_revision == before.queue_revision + 1


async def test_pause_marks_lower_bound(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    a = await register(s, "manager")
    await register(s, "manager2")
    await register(s, "member")
    attempt, _ = await start(s, a, START)
    await pause_attempt(s, attempt, attempt.version, START + timedelta(minutes=1))

    state = await read_eta(s, START + timedelta(minutes=3))

    current = state.eta.current
    assert current is not None
    assert (current.registration_id, current.status, current.paused) == (a.id, "speaking", True)
    assert (current.phase_remaining_seconds, current.slot_remaining_seconds, current.overdue_seconds) == (
        240,
        540,
        0,
    )
    assert [item.eta_seconds for item in state.eta.items] == [540, 1140]
    assert [(item.certainty, item.reason) for item in state.eta.items] == [
        ("lower_bound", "paused"),
        ("lower_bound", "paused"),
    ]
    assert all(item.eta_seconds >= 0 for item in state.eta.items)


async def test_overdue_marks_lower_bound_and_zero_current(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    a = await register(s, "manager")
    await register(s, "manager2")
    await register(s, "member")
    await start(s, a, START)

    state = await read_eta(s, START + timedelta(minutes=7))

    current = state.eta.current
    assert current is not None
    assert (current.registration_id, current.status, current.paused) == (a.id, "speaking", False)
    assert current.overdue_seconds == 120
    assert current.phase_remaining_seconds == 0
    assert current.slot_remaining_seconds == 0
    assert [item.eta_seconds for item in state.eta.items] == [0, 600]
    assert [(item.certainty, item.reason) for item in state.eta.items] == [
        ("lower_bound", "overdue"),
        ("lower_bound", "overdue"),
    ]
    assert all(item.eta_seconds >= 0 for item in state.eta.items)


async def test_settings_change_affects_waiting_not_current(seeded):
    s = seeded
    a = await register(s, "manager")
    b = await register(s, "manager2")
    c = await register(s, "member")
    attempt, _ = await start(s, a, START)

    before = await read_eta(s, START)
    assert (before.settings_version, before.eta.current.settings_version) == (1, 1)
    assert before.eta.current.slot_remaining_seconds == 900
    assert [item.eta_seconds for item in before.eta.items] == [900, 1800]

    # v2 deliberately has a different total (5 + 5 + 0 = 10 min) so the numeric
    # waiting ETA proves that the current edition, not v1, is used.
    await set_settings(s, presentation_minutes=5, questions_minutes=5, transition_minutes=0)
    after = await read_eta(s, START)

    assert after.settings_version == 2
    assert after.eta.current.settings_version == 1
    assert after.eta.current.slot_remaining_seconds == 900
    assert after.queue_revision == before.queue_revision
    assert [item.registration_id for item in after.eta.items] == [b.id, c.id]
    assert [item.eta_seconds for item in after.eta.items] == [900, 1500]
    assert attempt.settings_version == 1


async def test_slot_change_does_not_change_eta(seeded):
    s = seeded
    await set_settings(s, presentation_minutes=5, questions_minutes=4, transition_minutes=1)
    async with s["uow"]() as u:
        slots = await registration_cases.reg_service(u).add_slots(
            s["workspace"], s["exams"][0], slot_batch(), s["users"]["teacher"]
        )
    a = await register(s, "manager", slot_id=slots[0].id)
    b = await register(s, "manager2", slot_id=slots[1].id)
    before = await read_eta(s, START)
    assert [item.eta_seconds for item in before.eta.items] == [0, 600]
    assert before.items[1].planned_start_at == slots[1].starts_at
    revision_before = before.queue_revision

    async with s["uow"]() as u:
        moved = await registration_cases.reg_service(u).move_organized(
            s["workspace"],
            s["exams"][0],
            b.id,
            RegistrationMove(
                expected_version=b.version,
                target_exam_id=s["exams"][0],
                target_slot_id=slots[2].id,
                reason="Другой слот",
            ),
            s["users"]["teacher"],
        )
    assert moved.target.slot_id == slots[2].id

    after = await read_eta(s, START)
    assert after.queue_revision == revision_before
    assert [item.registration_id for item in after.eta.items] == [a.id, b.id]
    assert [item.eta_seconds for item in after.eta.items] == [0, 600]
    assert after.items[1].planned_start_at == slots[2].starts_at
    assert after.items[1].planned_end_at == slots[2].ends_at
    assert after.items[1].planned_start_at != before.items[1].planned_start_at


async def test_started_exam_before_starts_at_uses_now(seeded):
    s = seeded
    a = await register(s, "manager")
    b = await register(s, "manager2")
    c = await register(s, "member")
    attempt, _ = await start(s, a, START - timedelta(minutes=10))
    await finish_attempt(s, attempt, attempt.version, START - timedelta(minutes=8))

    state = await read_eta(s, START - timedelta(minutes=5))

    assert state.eta.current is None
    assert [item.registration_id for item in state.eta.items] == [b.id, c.id]
    assert [item.eta_seconds for item in state.eta.items] == [0, 900]
    assert [item.reason for item in state.eta.items] == [None, None]


async def test_before_start_uses_starts_at(seeded):
    s = seeded
    b = await register(s, "manager")
    c = await register(s, "manager2")

    state = await read_eta(s, START - timedelta(minutes=10))

    assert state.server_now == START - timedelta(minutes=10)
    assert state.eta.current is None
    assert [item.registration_id for item in state.eta.items] == [b.id, c.id]
    assert [item.eta_seconds for item in state.eta.items] == [600, 1500]
    assert [item.eta_at for item in state.eta.items] == [
        START,
        START + timedelta(minutes=15),
    ]
    assert [(item.certainty, item.reason) for item in state.eta.items] == [
        ("certain", "before_start"),
        ("certain", "before_start"),
    ]


async def test_empty_queue_returns_empty_eta(seeded):
    s = seeded

    state = await read_eta(s, START)

    assert state.eta.items == []
    assert state.eta.current is None


async def test_queue_revision_and_settings_version_are_exposed(seeded):
    s = seeded
    a = await register(s, "manager")
    b = await register(s, "manager2")

    state = await read_eta(s, START)
    assert (state.contract_version, state.settings_version, state.eta_stale) == (1, 1, False)
    assert [item.registration_id for item in state.eta.items] == [a.id, b.id]
    revision_before = state.queue_revision

    placed = await place(s, b.id, b.version, 1, START)
    assert placed.queue_revision == revision_before + 1

    after = await read_eta(s, START)
    assert after.queue_revision == revision_before + 1
    assert after.contract_version == 1
    assert after.eta_stale is False
