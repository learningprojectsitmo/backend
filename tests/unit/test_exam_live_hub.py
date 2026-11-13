from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.services.exam_live_hub import ExamLiveConfig, ExamLiveHub, OutboundBuffer


class FakeConnection:
    def __init__(self):
        self.offers: list[dict] = []
        self.closed = False

    def offer(self, message: dict) -> None:
        self.offers.append(message)

    async def close(self, _code: int = 1000, _reason: str = "") -> None:
        self.closed = True


def snapshot(seq: int, *, stale: bool = False):
    return SimpleNamespace(
        stream_seq=seq,
        stale=stale,
        queue=SimpleNamespace(queue_revision=17, settings_version=3),
        server_now=None,
        model_dump=lambda **_: {
            "type": "snapshot",
            "stream_seq": seq,
            "stale": stale,
        },
    )


async def drain(buffer: OutboundBuffer) -> list[dict]:
    items = []
    while True:
        try:
            items.append(await asyncio.wait_for(buffer.get(), 0.01))
        except TimeoutError:
            return items


async def test_snapshot_replaces_an_older_pending_snapshot():
    buffer = OutboundBuffer()
    buffer.offer({"type": "snapshot", "stream_seq": 1})
    buffer.offer({"type": "snapshot", "stream_seq": 2})

    assert await drain(buffer) == [{"type": "snapshot", "stream_seq": 2}]


async def test_control_message_is_kept_when_a_snapshot_is_replaced():
    buffer = OutboundBuffer()
    buffer.offer({"type": "heartbeat", "stream_seq": 1})
    buffer.offer({"type": "snapshot", "stream_seq": 1})
    buffer.offer({"type": "snapshot", "stream_seq": 2})

    assert await drain(buffer) == [
        {"type": "heartbeat", "stream_seq": 1},
        {"type": "snapshot", "stream_seq": 2},
    ]


async def test_buffer_marks_overflow_instead_of_growing_without_bound():
    buffer = OutboundBuffer(max_messages=2)
    buffer.offer({"type": "heartbeat", "stream_seq": 1})
    buffer.offer({"type": "heartbeat", "stream_seq": 2})
    buffer.offer({"type": "heartbeat", "stream_seq": 3})

    assert buffer.overflowed is True


async def test_notifications_coalesce_and_union_changed_categories():
    calls = []

    async def build(workspace_id, exam_id, user, *, reason, changed, check_access):
        calls.append((workspace_id, exam_id, reason, tuple(sorted(changed)), check_access))
        return snapshot(7)

    hub = ExamLiveHub(
        uow_factory=lambda: None,
        dsn="",
        config=ExamLiveConfig(listener_enabled=False, coalesce_seconds=0.02),
        snapshot_builder=build,
    )
    connection = FakeConnection()
    key = (7, 12)
    hub._subscribers.setdefault(key, set()).add(connection)

    hub.handle_notification(SimpleNamespace(workspace_id=7, exam_id=12, stream_seq=6, changed=("attempt",)))
    hub.handle_notification(SimpleNamespace(workspace_id=7, exam_id=12, stream_seq=7, changed=("queue",)))
    await asyncio.sleep(0.1)

    assert calls == [(7, 12, "changed", ("attempt", "queue"), False)]
    assert [item["stream_seq"] for item in connection.offers] == [7]
    await hub.stop()


async def test_duplicate_or_older_stream_seq_is_not_broadcast():
    async def build(workspace_id, exam_id, user, *, reason, changed, check_access):
        return snapshot(5)

    hub = ExamLiveHub(
        uow_factory=lambda: None,
        dsn="",
        config=ExamLiveConfig(listener_enabled=False),
        snapshot_builder=build,
    )
    connection = FakeConnection()
    key = (7, 12)
    hub._subscribers.setdefault(key, set()).add(connection)
    hub._last_sent[key] = 5

    await hub.refresh(key, reason="changed", changed=())

    assert connection.offers == []
    await hub.stop()
