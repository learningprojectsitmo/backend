from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.core.config import settings
from src.core.exceptions import NotFoundError, PermissionError
from src.schema.exam_live import ExamLiveErrorRead
from src.services.exam_live_hub import ExamLiveConnection, ExamLiveHub, ExamLiveLimitError

exam_live_router = APIRouter(tags=["exam-live"])

MAX_PATH_ID = 2**31 - 1
HTTP_UNAUTHORIZED = 401


async def _close_with_error(websocket: WebSocket, code: str, message: str, close_code: int) -> None:
    if websocket.client_state is WebSocketState.CONNECTED:
        with contextlib.suppress(RuntimeError, OSError):
            await websocket.send_json(ExamLiveErrorRead(code=code, message=message).model_dump(mode="json"))
        with contextlib.suppress(RuntimeError, OSError):
            await websocket.close(code=close_code, reason=message)


def _parse_id(raw: str) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < 1 or value > MAX_PATH_ID:
        return None
    return value


async def _receive_auth(websocket: WebSocket, hub: ExamLiveHub) -> tuple[str, int | None] | None:
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), hub.config.auth_timeout_seconds)
    except TimeoutError:
        await _close_with_error(websocket, "unauthorized", "Authentication timeout", 4401)
        return None
    except WebSocketDisconnect:
        return None
    if len(raw.encode("utf-8")) > hub.config.max_incoming_bytes:
        await _close_with_error(websocket, "protocol_error", "Message is too large", 4409)
        return None
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        await _close_with_error(websocket, "protocol_error", "Invalid JSON", 4400)
        return None
    if not isinstance(message, dict) or message.get("type") != "auth":
        await _close_with_error(websocket, "protocol_error", "First message must be auth", 4400)
        return None
    token = message.get("token")
    if not isinstance(token, str) or not token:
        await _close_with_error(websocket, "unauthorized", "Token is required", 4401)
        return None
    last_stream_seq = message.get("last_stream_seq")
    if last_stream_seq is not None and (
        not isinstance(last_stream_seq, int) or isinstance(last_stream_seq, bool) or last_stream_seq < 0
    ):
        await _close_with_error(websocket, "protocol_error", "Invalid last_stream_seq", 4400)
        return None
    return token, last_stream_seq


@exam_live_router.websocket("/workspaces/{workspace_id}/exams/{exam_id}/live")
async def exam_live(websocket: WebSocket, workspace_id: str, exam_id: str) -> None:
    await websocket.accept()
    hub: ExamLiveHub = websocket.app.state.exam_live_hub

    parsed_workspace = _parse_id(workspace_id)
    parsed_exam = _parse_id(exam_id)
    if parsed_workspace is None or parsed_exam is None:
        await _close_with_error(websocket, "protocol_error", "Invalid exam path", 4400)
        return

    origin = websocket.headers.get("origin")
    if origin is not None and origin not in settings.CORS_ORIGINS:
        await _close_with_error(websocket, "forbidden", "Origin is not allowed", 4403)
        return

    auth = await _receive_auth(websocket, hub)
    if auth is None:
        return
    token, last_stream_seq = auth

    try:
        user, writer, _exam = await hub.authenticate(token, parsed_workspace, parsed_exam)
    except (NotFoundError, PermissionError):
        await _close_with_error(websocket, "not_found", "Exam not found", 4404)
        return
    except Exception as error:
        if getattr(error, "status_code", None) == HTTP_UNAUTHORIZED:
            await _close_with_error(websocket, "unauthorized", "Invalid token", 4401)
        else:
            await _close_with_error(websocket, "snapshot_unavailable", "Authentication is unavailable", 1011)
        return

    connection = ExamLiveConnection(
        websocket,
        workspace_id=parsed_workspace,
        exam_id=parsed_exam,
        user=user,
        token=token,
        role="organizer" if writer else "viewer",
        can_manage=writer,
        reason="reconnect" if last_stream_seq is not None else "connected",
        config=hub.config,
        clock=hub.clock,
    )
    await websocket.send_json(connection.hello())
    try:
        await hub.serve(connection)
    except ExamLiveLimitError:
        await _close_with_error(websocket, "too_many_connections", "Connection limit reached", 4429)
    except Exception:
        await _close_with_error(websocket, "snapshot_unavailable", "Snapshot is unavailable", 1011)
