from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.services.exam_live_hub import ExamLiveConfig, ExamLiveConnection, ExamLiveHub, OutboundBuffer


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


class SlowWebSocket:
    def __init__(self):
        self.close_code = None

    async def send_json(self, _payload):
        await asyncio.sleep(0.05)

    async def close(self, code: int = 1000, reason: str = ""):
        del reason
        self.close_code = code


async def test_slow_consumer_is_closed_with_4408():
    websocket = SlowWebSocket()
    connection = ExamLiveConnection(
        websocket,
        workspace_id=7,
        exam_id=12,
        user=SimpleNamespace(id=7),
        token="token",
        role="viewer",
        can_manage=False,
        reason="connected",
        config=ExamLiveConfig(max_messages=1, send_timeout_seconds=0.01),
        clock=lambda: None,
    )
    connection.buffer.offer({"type": "heartbeat", "stream_seq": 1})
    connection.buffer.offer({"type": "heartbeat", "stream_seq": 2})

    await connection._send_loop()

    assert websocket.close_code == 4408


async def test_transient_recheck_error_does_not_revoke_access():
    def failing_uow():
        raise RuntimeError("database unavailable")

    hub = ExamLiveHub(
        uow_factory=failing_uow,
        dsn="",
        config=ExamLiveConfig(listener_enabled=False),
        snapshot_builder=None,
    )
    connection = SimpleNamespace(workspace_id=7, exam_id=12, token="token", user=SimpleNamespace(id=7))

    assert await hub.recheck_access(connection) is None
    await hub.stop()


async def test_failed_refresh_marks_last_state_stale():
    async def build(_workspace_id, _exam_id, _user, *, reason, changed, check_access):
        del reason, changed, check_access
        raise RuntimeError("database unavailable")

    hub = ExamLiveHub(
        uow_factory=lambda: None,
        dsn="",
        config=ExamLiveConfig(listener_enabled=False),
        snapshot_builder=build,
    )
    key = (7, 12)
    hub._subscribers.setdefault(key, set()).add(FakeConnection())
    hub._last_meta[key] = {"stream_seq": 4, "queue_revision": 17, "settings_version": 3, "stale": False}

    with pytest.raises(RuntimeError):
        await hub.refresh(key, reason="changed", changed=())

    assert hub._last_meta[key]["stale"] is True
    await hub.stop()


async def test_changed_categories_force_refresh_even_with_same_stream_seq():
    async def build(_workspace_id, _exam_id, _user, *, reason, changed, check_access):
        del reason, changed, check_access
        return snapshot(5)

    hub = ExamLiveHub(
        uow_factory=lambda: None,
        dsn="",
        config=ExamLiveConfig(listener_enabled=False),
        snapshot_builder=build,
    )
    key = (7, 12)
    connection = FakeConnection()
    hub._subscribers.setdefault(key, set()).add(connection)
    hub._last_sent[key] = 5

    await hub.refresh(key, reason="changed", changed=("attempt",))

    assert [item["stream_seq"] for item in connection.offers] == [5]
    await hub.stop()
