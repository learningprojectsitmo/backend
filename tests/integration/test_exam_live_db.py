from __future__ import annotations

import asyncio
import json

import asyncpg
import pytest
import test_exam_registrations_db as registration_cases
from sqlalchemy import select
from test_exam_eta_db import finish_attempt, pause_attempt, place, set_settings, start, to_questions
from test_exam_queue_db import attempt_service, read_queue, register
from test_exam_registrations_db import reg_service

from src.core.exam_live_protocol import EXAM_LIVE_CHANNEL
from src.model.exam import Exam
from src.repository.exam_registration_repository import ExamRegistrationRepository
from src.repository.exam_repository import ExamRepository
from src.schema.exam_attempt import AttemptCommand
from src.schema.exam_registration import RegistrationMove
from src.services.exam_live_service import ExamLiveService

pytestmark = pytest.mark.integration

seeded = registration_cases.seeded


def dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def listener(url: str):
    connection = await asyncpg.connect(dsn(url))
    queue: asyncio.Queue[dict] = asyncio.Queue()
    await connection.add_listener(
        EXAM_LIVE_CHANNEL,
        lambda _connection, _pid, _channel, payload: queue.put_nowait(json.loads(payload)),
    )
    return connection, queue


async def stream_seq(s, exam: int = 0) -> int:
    async with s["uow"]() as u:
        value = await u.session.scalar(select(Exam.stream_seq).where(Exam.id == s["exams"][exam]))
    assert value is not None
    return int(value)


async def test_commit_bumps_stream_seq_once_and_notifies_after_commit(seeded):
    s = seeded
    connection, notifications = await listener(s["url"])
    try:
        before = await stream_seq(s)
        async with s["uow"]() as u:
            u.mark_exam_changed(s["exams"][0], "attempt")
            u.mark_exam_changed(s["exams"][0], "queue")
            await u.session.flush()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(notifications.get(), 0.2)
            await u.commit()

        after = await stream_seq(s)
        assert after == before + 1
        note = await asyncio.wait_for(notifications.get(), 2)
        assert note == {"exam_id": s["exams"][0], "stream_seq": after, "changed": ["attempt", "queue"]}
    finally:
        await connection.close()


async def test_rollback_does_not_bump_stream_seq_or_notify(seeded):
    s = seeded
    connection, notifications = await listener(s["url"])
    try:
        before = await stream_seq(s)
        with pytest.raises(RuntimeError):
            async with s["uow"]() as u:
                u.mark_exam_changed(s["exams"][0], "attempt")
                await u.session.flush()
                raise RuntimeError("stop")
        assert await stream_seq(s) == before
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(notifications.get(), 0.2)
    finally:
        await connection.close()


async def test_transaction_without_marks_does_not_bump_or_notify(seeded):
    s = seeded
    connection, notifications = await listener(s["url"])
    try:
        before = await stream_seq(s)
        async with s["uow"]():
            pass
        assert await stream_seq(s) == before
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(notifications.get(), 0.2)
    finally:
        await connection.close()


async def test_two_exams_get_independent_stream_seq_and_notifications(seeded):
    s = seeded
    connection, notifications = await listener(s["url"])
    try:
        first_before = await stream_seq(s, 0)
        second_before = await stream_seq(s, 1)
        async with s["uow"]() as u:
            u.mark_exam_changed(s["exams"][1], "attempt")
            u.mark_exam_changed(s["exams"][0], "queue")
        assert await stream_seq(s, 0) == first_before + 1
        assert await stream_seq(s, 1) == second_before + 1
        notes = [await asyncio.wait_for(notifications.get(), 2) for _ in range(2)]
        assert notes == [
            {"exam_id": s["exams"][0], "stream_seq": first_before + 1, "changed": ["queue"]},
            {"exam_id": s["exams"][1], "stream_seq": second_before + 1, "changed": ["attempt"]},
        ]
    finally:
        await connection.close()


async def test_queue_revision_bump_marks_queue_and_moves_stream_seq(seeded):
    s = seeded
    connection, notifications = await listener(s["url"])
    try:
        before = await stream_seq(s)
        async with s["uow"]() as u:
            await ExamRepository(u).bump_queue_revision(s["exams"][0])
        assert await stream_seq(s) == before + 1
        note = await asyncio.wait_for(notifications.get(), 2)
        assert note == {"exam_id": s["exams"][0], "stream_seq": before + 1, "changed": ["queue"]}
    finally:
        await connection.close()


async def live_snapshot(s, *, user="teacher", exam=0):
    async with s["uow"]() as u:
        return await ExamLiveService(u).snapshot(
            s["workspace"], s["exams"][exam] if exam != "draft" else s["draft"], s["users"][user], reason="connected"
        )


async def test_snapshot_uses_http_queue_and_reports_finished_window(seeded):
    s = seeded
    registration = await register(s, "manager")
    attempt, _ = await start(s, registration)
    finished = await finish_attempt(s, attempt, attempt.version)

    snapshot = await live_snapshot(s)

    assert snapshot.stream_seq >= 1
    assert snapshot.queue.queue_revision == (await read_queue(s)).queue_revision
    assert snapshot.queue.items[0].registration_id == registration.id
    assert snapshot.queue.items[0].attempt is not None
    assert snapshot.queue.items[0].attempt.status == "finished"
    assert len(snapshot.assessment_windows) == 1
    window = snapshot.assessment_windows[0]
    assert (window.attempt_id, window.registration_id) == (finished.id, registration.id)
    assert window.closes_at == finished.assessment_window.closes_at
    assert window.state == ("open" if snapshot.server_now < window.closes_at else "closed")


async def test_draft_is_hidden_from_viewer_but_visible_to_organizer(seeded):
    s = seeded

    with pytest.raises(Exception) as error:
        await live_snapshot(s, user="manager", exam="draft")
    assert error.value.__class__.__name__ == "NotFoundError"

    snapshot = await live_snapshot(s, user="teacher", exam="draft")
    assert snapshot.exam.status == "draft"


async def resume_attempt(s, attempt, version):
    async with s["uow"]() as u:
        return await attempt_service(u).resume(
            s["workspace"], s["exams"][0], attempt.id, AttemptCommand(expected_version=version), s["users"]["teacher"]
        )


async def test_questions_pause_resume_advance_stream_without_queue_revision(seeded):
    s = seeded
    registration = await register(s, "manager")
    attempt, _ = await start(s, registration)
    before_queue = await read_queue(s)
    before_seq = await stream_seq(s)

    questions = await to_questions(s, attempt, attempt.version)
    assert (await read_queue(s)).queue_revision == before_queue.queue_revision
    assert await stream_seq(s) == before_seq + 1

    paused = await pause_attempt(s, questions, questions.version)
    assert (await read_queue(s)).queue_revision == before_queue.queue_revision
    assert await stream_seq(s) == before_seq + 2

    resumed = await resume_attempt(s, paused, paused.version)
    assert (await read_queue(s)).queue_revision == before_queue.queue_revision
    assert await stream_seq(s) == before_seq + 3
    snapshot = await live_snapshot(s)
    assert snapshot.queue.queue_revision == before_queue.queue_revision
    assert snapshot.queue.items[0].attempt.version == resumed.version
    assert snapshot.queue.items[0].attempt.status == "questions"
    assert snapshot.stream_seq == before_seq + 3


async def test_repeat_pause_is_noop_for_stream_and_queue(seeded):
    s = seeded
    registration = await register(s, "manager")
    attempt, _ = await start(s, registration)
    paused = await pause_attempt(s, attempt, attempt.version)
    before_seq = await stream_seq(s)
    before_revision = (await read_queue(s)).queue_revision

    repeated = await pause_attempt(s, paused, paused.version)

    assert repeated.version == paused.version
    assert await stream_seq(s) == before_seq
    assert (await read_queue(s)).queue_revision == before_revision


async def test_settings_change_advances_stream_without_queue_revision(seeded):
    s = seeded
    registration = await register(s, "manager")
    await start(s, registration)
    before_queue = await read_queue(s)
    before_seq = await stream_seq(s)

    await set_settings(s, expected_version=1, presentation_minutes=8)

    after_queue = await read_queue(s)
    assert after_queue.queue_revision == before_queue.queue_revision
    assert after_queue.settings_version == before_queue.settings_version + 1
    assert await stream_seq(s) == before_seq + 1
    snapshot = await live_snapshot(s)
    assert snapshot.queue.settings_version == after_queue.settings_version
    assert snapshot.stream_seq == before_seq + 1


async def test_slot_change_advances_stream_without_queue_revision(seeded):
    s = seeded
    async with s["uow"]() as u:
        await reg_service(u).add_slots(
            s["workspace"], s["exams"][0], registration_cases.intervals(), s["users"]["teacher"]
        )
    async with s["uow"]() as u:
        slots = await ExamRegistrationRepository(u).all_slots(s["exams"][0])
    registration = await register(s, "manager", slot_id=slots[0].id)
    before_queue = await read_queue(s)
    before_seq = await stream_seq(s)

    async with s["uow"]() as u:
        moved = await reg_service(u).move_organized(
            s["workspace"],
            s["exams"][0],
            registration.id,
            RegistrationMove(
                expected_version=registration.version,
                target_exam_id=s["exams"][0],
                target_slot_id=slots[1].id,
                reason="Перенос внутри экзамена",
            ),
            s["users"]["teacher"],
        )

    after_queue = await read_queue(s)
    assert moved.target.slot_id == slots[1].id
    assert after_queue.queue_revision == before_queue.queue_revision
    assert await stream_seq(s) == before_seq + 1
    assert after_queue.items[0].planned_start_at == slots[1].starts_at


async def test_queue_place_noop_does_not_advance_stream(seeded):
    s = seeded
    registration = await register(s, "manager")
    before_seq = await stream_seq(s)
    before_revision = (await read_queue(s)).queue_revision

    await place(s, registration.id, registration.version, position=1)

    assert await stream_seq(s) == before_seq
    assert (await read_queue(s)).queue_revision == before_revision
