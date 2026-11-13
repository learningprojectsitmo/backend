from __future__ import annotations

import asyncio
import json

import asyncpg
import pytest
import test_exam_registrations_db as registration_cases
from sqlalchemy import select

from src.core.exam_live_protocol import EXAM_LIVE_CHANNEL
from src.model.exam import Exam
from src.repository.exam_repository import ExamRepository

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
