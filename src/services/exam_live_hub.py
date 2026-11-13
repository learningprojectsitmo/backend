from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.engine import make_url

from src.core.exam_live_protocol import EXAM_LIVE_CHANNEL, ExamLiveNotification
from src.core.uow import IUnitOfWork
from src.repository.exam_repository import ExamRepository
from src.repository.password_reset_repository import PasswordResetRepository
from src.repository.role_repository import RolePermissionRepository
from src.repository.session_repository import SessionRepository
from src.repository.user_repository import UserPermissionRepository, UserRepository
from src.schema.exam_live import (
    ExamLiveAccessRead,
    ExamLiveErrorRead,
    ExamLiveHeartbeatRead,
    ExamLiveHelloRead,
    ExamLiveSnapshotRead,
)
from src.services.auth_service import AuthService
from src.services.exam_live_service import ExamLiveService
from src.services.session_service import SessionService

logger = logging.getLogger(__name__)

_RESYNC_COOLDOWN_SECONDS = 5.0
_HTTP_UNAUTHORIZED = 401

ExamKey = tuple[int, int]
SnapshotBuilder = Callable[..., Awaitable[ExamLiveSnapshotRead]]


@dataclass(frozen=True, slots=True)
class ExamLiveConfig:
    heartbeat_seconds: float = 20.0
    reconcile_seconds: float = 10.0
    access_check_seconds: float = 30.0
    auth_timeout_seconds: float = 5.0
    send_timeout_seconds: float = 5.0
    coalesce_seconds: float = 0.1
    listener_wait_seconds: float = 5.0
    max_connections_per_exam: int = 250
    max_connections_per_process: int = 1000
    max_incoming_bytes: int = 4096
    max_messages: int = 2
    listener_enabled: bool = True


class ExamLiveLimitError(Exception):
    pass


class OutboundBuffer:
    """Bounded outbound buffer: a newer snapshot replaces a pending one."""

    def __init__(self, max_messages: int = 2) -> None:
        self._items: list[dict] = []
        self._event = asyncio.Event()
        self.max_messages = max_messages
        self.overflowed = False

    def offer(self, message: dict) -> None:
        if message.get("type") == "snapshot":
            self._items = [item for item in self._items if item.get("type") != "snapshot"]
        self._items.append(message)
        if len(self._items) > self.max_messages:
            self.overflowed = True
            self._items = self._items[-self.max_messages :]
        self._event.set()

    async def get(self) -> dict:
        while not self._items:
            self._event.clear()
            await self._event.wait()
        return self._items.pop(0)

    def clear(self) -> None:
        self._items.clear()
        self._event.set()


class ExamLiveConnection:
    def __init__(
        self,
        websocket: WebSocket,
        *,
        workspace_id: int,
        exam_id: int,
        user,
        token: str,
        role: str,
        can_manage: bool,
        reason: str,
        config: ExamLiveConfig,
        clock: Callable[[], datetime],
    ) -> None:
        self.websocket = websocket
        self.workspace_id = workspace_id
        self.exam_id = exam_id
        self.user = user
        self.token = token
        self.role = role
        self.can_manage = can_manage
        self.reason = reason
        self.config = config
        self.clock = clock
        self.buffer = OutboundBuffer(config.max_messages)
        self.closed = False
        self._send_task: asyncio.Task | None = None
        self._guard_task: asyncio.Task | None = None
        self._last_resync = 0.0

    @property
    def key(self) -> ExamKey:
        return self.workspace_id, self.exam_id

    def hello(self) -> dict:
        return ExamLiveHelloRead(
            access=ExamLiveAccessRead(role=self.role, can_manage=self.can_manage),
            server_now=self.clock(),
        ).model_dump(mode="json")

    def offer(self, message: dict) -> None:
        if not self.closed:
            self.buffer.offer(message)

    async def send_error_and_close(self, code: str, message: str, close_code: int) -> None:
        if self.closed:
            return
        current = asyncio.current_task()
        if self._send_task is not None and self._send_task is not current:
            self._send_task.cancel()
            await asyncio.gather(self._send_task, return_exceptions=True)
        payload = ExamLiveErrorRead(code=code, message=message).model_dump(mode="json")
        with contextlib.suppress(TimeoutError, RuntimeError):
            await asyncio.wait_for(self.websocket.send_json(payload), self.config.send_timeout_seconds)
        await self.close(close_code)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed:
            return
        self.closed = True
        self.buffer.clear()
        with contextlib.suppress(RuntimeError, OSError):
            await self.websocket.close(code=code, reason=reason)

    async def run(self, hub: ExamLiveHub) -> None:
        self._send_task = asyncio.create_task(self._send_loop())
        self._guard_task = asyncio.create_task(self._guard_loop(hub))
        try:
            while not self.closed:
                raw = await self.websocket.receive_text()
                if len(raw.encode("utf-8")) > self.config.max_incoming_bytes:
                    await self.send_error_and_close("protocol_error", "Message is too large", 4409)
                    break
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await self.send_error_and_close("protocol_error", "Invalid JSON", 4400)
                    break
                if not await self._handle_message(message, hub):
                    break
        except WebSocketDisconnect:
            pass
        finally:
            for task in (self._send_task, self._guard_task):
                if task is not None:
                    task.cancel()
            tasks = [task for task in (self._send_task, self._guard_task) if task is not None]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await self.close()

    async def _handle_message(self, message, hub: ExamLiveHub) -> bool:
        if not isinstance(message, dict):
            await self.send_error_and_close("protocol_error", "Message must be an object", 4400)
            return False
        message_type = message.get("type")
        if message_type == "auth":
            await self.send_error_and_close("protocol_error", "Already authenticated", 4400)
            return False
        if message_type == "resync":
            try:
                await hub.request_resync(self)
            except Exception:
                logger.exception("Exam live resync failed")
                await self.send_error_and_close("snapshot_unavailable", "Snapshot is unavailable", 1011)
                return False
        elif message_type == "ping":
            self.offer({"type": "pong", "contract_version": 1, "server_now": self.clock().isoformat()})
        return True

    async def _send_loop(self) -> None:
        try:
            while not self.closed:
                if self.buffer.overflowed:
                    await self.send_error_and_close("slow_consumer", "Outbound buffer overflow", 4408)
                    return
                message = await self.buffer.get()
                await asyncio.wait_for(
                    self.websocket.send_json(message),
                    self.config.send_timeout_seconds,
                )
        except (TimeoutError, RuntimeError, OSError):
            await self.close(4408, "Send timeout")
        except asyncio.CancelledError:
            raise

    async def _guard_loop(self, hub: ExamLiveHub) -> None:
        while not self.closed:
            await asyncio.sleep(self.config.access_check_seconds)
            if self.closed:
                return
            error = await hub.recheck_access(self)
            if error is not None:
                code, close_code = error
                await self.send_error_and_close(code, "Access is no longer available", close_code)
                return


class ExamLiveHub:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], IUnitOfWork],
        dsn: str,
        config: ExamLiveConfig | None = None,
        snapshot_builder: SnapshotBuilder | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._dsn = dsn
        self.config = config or ExamLiveConfig()
        self._snapshot_builder = snapshot_builder
        self._clock = clock or (lambda: datetime.now(UTC))
        self._subscribers: dict[ExamKey, set[ExamLiveConnection]] = {}
        self._locks: dict[ExamKey, asyncio.Lock] = {}
        self._last_sent: dict[ExamKey, int] = {}
        self._last_meta: dict[ExamKey, dict] = {}
        self._last_stale: dict[ExamKey, int] = {}
        self._pending: dict[ExamKey, set[str]] = {}
        self._refresh_tasks: dict[ExamKey, asyncio.Task] = {}
        self._started = False
        self._stop = asyncio.Event()
        self._listening = asyncio.Event()
        self._listener_connection: asyncpg.Connection | None = None
        self._listener_task: asyncio.Task | None = None
        self._reconcile_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        if self.config.listener_enabled:
            self._listener_task = asyncio.create_task(self._listener_loop())
            try:
                await asyncio.wait_for(self._listening.wait(), self.config.listener_wait_seconds)
            except TimeoutError:
                logger.warning("Exam live listener did not become ready; reconciliation remains active")
        else:
            self._listening.set()
        self._reconcile_task = asyncio.create_task(self._reconcile_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        self._stop.set()
        for connections in list(self._subscribers.values()):
            for connection in list(connections):
                await connection.close(1001, "Server shutdown")
        tasks = [
            task
            for task in (
                self._listener_task,
                self._reconcile_task,
                self._heartbeat_task,
                *self._refresh_tasks.values(),
            )
            if task is not None
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._listener_connection is not None:
            await self._listener_connection.close()
            self._listener_connection = None
        self._subscribers.clear()
        self._refresh_tasks.clear()

    async def serve(self, connection: ExamLiveConnection) -> None:
        await self.add(connection)
        try:
            await connection.run(self)
        finally:
            await self.remove(connection)

    async def add(self, connection: ExamLiveConnection) -> None:
        await self.start()
        key = connection.key
        connections = self._subscribers.setdefault(key, set())
        if len(connections) >= self.config.max_connections_per_exam:
            raise ExamLiveLimitError("Too many connections for this exam")
        if self.total_connections >= self.config.max_connections_per_process:
            raise ExamLiveLimitError("Too many connections for this process")
        connections.add(connection)
        try:
            async with self._lock(key):
                snapshot = await self._build(
                    key,
                    user=connection.user,
                    reason=connection.reason,
                    changed=(),
                    check_access=True,
                )
                connection.offer(snapshot.model_dump(mode="json"))
                self._remember(key, snapshot)
        except Exception:
            connections.discard(connection)
            if not connections:
                self._subscribers.pop(key, None)
            raise

    async def remove(self, connection: ExamLiveConnection) -> None:
        key = connection.key
        connections = self._subscribers.get(key)
        if connections is not None:
            connections.discard(connection)
            if not connections:
                self._subscribers.pop(key, None)
                task = self._refresh_tasks.pop(key, None)
                if task is not None:
                    task.cancel()

    @property
    def clock(self) -> Callable[[], datetime]:
        return self._clock

    @property
    def total_connections(self) -> int:
        return sum(len(connections) for connections in self._subscribers.values())

    def _lock(self, key: ExamKey) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    def _remember(self, key: ExamKey, snapshot: ExamLiveSnapshotRead) -> None:
        if not snapshot.stale:
            self._last_sent[key] = max(self._last_sent.get(key, -1), snapshot.stream_seq)
        self._last_meta[key] = {
            "stream_seq": snapshot.stream_seq,
            "queue_revision": snapshot.queue.queue_revision,
            "settings_version": snapshot.queue.settings_version,
            "stale": snapshot.stale,
        }

    def _mark_stale(self, key: ExamKey) -> None:
        meta = self._last_meta.get(key)
        if meta is not None:
            meta["stale"] = True

    @staticmethod
    def _auth_service(uow: IUnitOfWork) -> AuthService:
        return AuthService(
            UserRepository(uow),
            SessionService(SessionRepository(uow)),
            PasswordResetRepository(uow),
            UserPermissionRepository(uow),
            RolePermissionRepository(uow),
        )

    async def authenticate(self, token: str, workspace_id: int, exam_id: int):
        async with self._uow_factory() as uow:
            user = await self._auth_service(uow).get_current_user(token)
            service = ExamLiveService(uow, clock=self._clock)
            exam, writer = await service.check_read_access(workspace_id, exam_id, user)
            return user, writer, exam

    async def _build(
        self,
        key: ExamKey,
        *,
        user,
        reason: str,
        changed: tuple[str, ...],
        check_access: bool,
    ) -> ExamLiveSnapshotRead:
        workspace_id, exam_id = key
        if self._snapshot_builder is not None:
            return await self._snapshot_builder(
                workspace_id,
                exam_id,
                user,
                reason=reason,
                changed=changed,
                check_access=check_access,
            )
        async with self._uow_factory() as uow:
            service = ExamLiveService(uow, clock=self._clock)
            return await service.snapshot(
                workspace_id,
                exam_id,
                user,
                reason=reason,
                changed=changed,
                check_access=check_access,
            )

    async def refresh(self, key: ExamKey, *, reason: str, changed: tuple[str, ...]) -> None:
        connections = self._subscribers.get(key)
        if not connections:
            return
        async with self._lock(key):
            connections = self._subscribers.get(key)
            if not connections:
                return
            try:
                snapshot = await self._build(key, user=None, reason=reason, changed=changed, check_access=False)
            except Exception:
                self._mark_stale(key)
                raise
            previous = self._last_sent.get(key, -1)
            if snapshot.stale:
                if snapshot.stream_seq <= self._last_stale.get(key, -1):
                    return
                self._last_stale[key] = snapshot.stream_seq
            elif snapshot.stream_seq <= previous and not changed:
                return
            payload = snapshot.model_dump(mode="json")
            for connection in list(connections):
                connection.offer(payload)
            self._remember(key, snapshot)

    def handle_notification(self, notification: ExamLiveNotification) -> None:
        key = notification.workspace_id, notification.exam_id
        if not self._subscribers.get(key):
            return
        self._pending.setdefault(key, set()).update(notification.changed)
        self._schedule_refresh(key)

    def _schedule_refresh(self, key: ExamKey) -> None:
        current = self._refresh_tasks.get(key)
        if current is not None and not current.done():
            return
        task = asyncio.create_task(self._delayed_refresh(key))
        self._refresh_tasks[key] = task

    async def _delayed_refresh(self, key: ExamKey) -> None:
        try:
            await asyncio.sleep(self.config.coalesce_seconds)
            changed = tuple(sorted(self._pending.pop(key, set())))
            await self.refresh(key, reason="changed", changed=changed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Exam live refresh failed for %s", key)
        finally:
            self._refresh_tasks.pop(key, None)
            if self._pending.get(key) and self._subscribers.get(key):
                self._schedule_refresh(key)

    async def request_resync(self, connection: ExamLiveConnection) -> None:
        now = asyncio.get_running_loop().time()
        if now - connection._last_resync < _RESYNC_COOLDOWN_SECONDS:
            return
        connection._last_resync = now
        async with self._lock(connection.key):
            try:
                snapshot = await self._build(
                    connection.key,
                    user=connection.user,
                    reason="resync",
                    changed=(),
                    check_access=True,
                )
            except Exception:
                self._mark_stale(connection.key)
                raise
            connection.offer(snapshot.model_dump(mode="json"))
            self._remember(connection.key, snapshot)

    async def recheck_access(self, connection: ExamLiveConnection) -> tuple[str, int] | None:
        try:
            async with self._uow_factory() as uow:
                user = await self._auth_service(uow).get_current_user(connection.token)
                service = ExamLiveService(uow, clock=self._clock)
                await service.check_read_access(connection.workspace_id, connection.exam_id, user)
                connection.user = user
                return None
        except Exception as error:
            if error.__class__.__name__ == "NotFoundError":
                return "not_found", 4404
            if getattr(error, "status_code", None) == _HTTP_UNAUTHORIZED:
                return "unauthorized", 4401
            logger.exception("Exam live access recheck failed; will retry")
            return None

    async def _wait_or_stop(self, seconds: float) -> bool:
        try:
            await asyncio.wait_for(self._stop.wait(), seconds)
        except TimeoutError:
            return False
        return True

    async def _reconcile_loop(self) -> None:
        while not self._stop.is_set():
            if await self._wait_or_stop(self.config.reconcile_seconds):
                return
            for key in list(self._subscribers):
                if not self._subscribers.get(key):
                    continue
                try:
                    async with self._uow_factory() as uow:
                        seq = await ExamRepository(uow).event_seq(*key)
                except Exception:
                    logger.exception("Exam live reconciliation failed for %s", key)
                    continue
                if seq is not None and seq > self._last_sent.get(key, -1):
                    try:
                        await self.refresh(key, reason="changed", changed=())
                    except Exception:
                        logger.exception("Exam live reconciliation refresh failed for %s", key)

    async def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            if await self._wait_or_stop(self.config.heartbeat_seconds):
                return
            now = self._clock()
            for key, connections in list(self._subscribers.items()):
                meta = self._last_meta.get(key)
                if meta is None:
                    continue
                payload = ExamLiveHeartbeatRead(
                    stream_seq=meta["stream_seq"],
                    server_now=now,
                    queue_revision=meta["queue_revision"],
                    settings_version=meta["settings_version"],
                    stale=meta["stale"],
                ).model_dump(mode="json")
                for connection in list(connections):
                    connection.offer(payload)

    async def _listener_loop(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            connection = None
            try:
                connection = await asyncpg.connect(self._dsn)
                await connection.add_listener(EXAM_LIVE_CHANNEL, self._notification_callback)
                self._listener_connection = connection
                self._listening.set()
                backoff = 1.0
                while not self._stop.is_set() and not connection.is_closed():
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Exam live listener failed; retrying in %.1fs", backoff)
            finally:
                self._listening.clear()
                if connection is not None:
                    try:
                        await connection.close()
                    except Exception:
                        logger.debug("Failed to close exam live listener", exc_info=True)
                self._listener_connection = None
            if self._stop.is_set():
                return
            if await self._wait_or_stop(backoff):
                return
            backoff = min(backoff * 2, 30.0)

    def _notification_callback(self, _connection, _pid, _channel, payload: str) -> None:
        try:
            notification = ExamLiveNotification.from_payload(payload)
        except (ValueError, TypeError):
            logger.warning("Ignoring malformed exam live notification")
            return
        self.handle_notification(notification)


def database_dsn(url: str) -> str:
    parsed = make_url(url)
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)
