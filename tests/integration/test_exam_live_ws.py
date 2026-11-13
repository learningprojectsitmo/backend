from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt
import pytest
import test_exam_registrations_db as registration_cases
import websockets
from sqlalchemy import delete, select

from src.model.exam import Exam
from src.model.workspace import WorkSpaceParticipation

pytestmark = pytest.mark.integration

seeded = registration_cases.seeded
REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET = "test-secret"
RECEIVE_TIMEOUT = 5.0


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def token_for(user) -> str:
    return jwt.encode(
        {
            "sub": user.email,
            "user_id": user.id,
            "type": "access",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        SECRET,
        algorithm="HS256",
    )


async def wait_http(port: int, proc: subprocess.Popen) -> None:
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=2) as client:
        for _ in range(100):
            if proc.poll() is not None:
                raise RuntimeError(f"server exited with {proc.returncode}")
            try:
                response = await client.get("/")
            except httpx.HTTPError:
                await asyncio.sleep(0.1)
                continue
            if response.status_code == 200:
                return
            await asyncio.sleep(0.1)
    raise RuntimeError("server did not start")


@contextlib.asynccontextmanager
async def run_server(database_url: str, *, max_per_exam: int = 250) -> AsyncIterator[str]:
    port = free_port()
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "AUTO_CREATE_TABLES": "false",
        "ENVIRONMENT": "ci",
        "SECRET_KEY": SECRET,
        "EXAM_LIVE_HEARTBEAT_SECONDS": "1",
        "EXAM_LIVE_RECONCILE_SECONDS": "1",
        "EXAM_LIVE_ACCESS_CHECK_SECONDS": "1",
        "EXAM_LIVE_AUTH_TIMEOUT_SECONDS": "2",
        "EXAM_LIVE_SEND_TIMEOUT_SECONDS": "2",
        "EXAM_LIVE_COALESCE_SECONDS": "0.02",
        "EXAM_LIVE_MAX_CONNECTIONS_PER_EXAM": str(max_per_exam),
        "LOG_LEVEL": "WARNING",
    }
    log = REPO_ROOT / ".superpowers" / "sdd" / "2026-11-13-exam-live" / f"ws-{port}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as handle:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=REPO_ROOT,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        try:
            await wait_http(port, proc)
            yield f"http://127.0.0.1:{port}"
        finally:
            proc.terminate()
            try:
                await asyncio.to_thread(proc.wait, 5)
            except subprocess.TimeoutExpired:
                proc.kill()
                await asyncio.to_thread(proc.wait, 5)


@contextlib.asynccontextmanager
async def live_socket(
    base_url: str,
    workspace_id: int,
    exam_id: int,
    token: str,
    *,
    last_stream_seq: int | None = None,
    origin: str | None = None,
):
    uri = f"{base_url.replace('http://', 'ws://')}/v1/workspaces/{workspace_id}/exams/{exam_id}/live"
    headers = {"Origin": origin} if origin is not None else None
    async with websockets.connect(uri, additional_headers=headers) as websocket:
        auth = {"type": "auth", "token": token}
        if last_stream_seq is not None:
            auth["last_stream_seq"] = last_stream_seq
        await websocket.send(json.dumps(auth))
        yield websocket


async def wait_for_close(websocket, timeout: float = 5.0) -> int:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("connection did not close")
        try:
            await asyncio.wait_for(websocket.recv(), remaining)
        except websockets.ConnectionClosed as error:
            return int(error.code or 0)


async def receive(websocket, message_type: str = "snapshot", timeout: float = RECEIVE_TIMEOUT) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"did not receive {message_type}")
        raw = await asyncio.wait_for(websocket.recv(), remaining)
        message = json.loads(raw)
        if message.get("type") == message_type:
            return message


async def http_json(client: httpx.AsyncClient, method: str, path: str, token: str, **kwargs):
    response = await client.request(method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
    assert response.status_code < 400, (response.status_code, response.text)
    return response.json()


async def create_running_attempt(client, s, *, exam: int, project: str):
    token = token_for(s["users"]["teacher"])
    registration = await http_json(
        client,
        "POST",
        f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][exam]}/registrations",
        token,
        json={"project_id": s["projects"][project], "slot_id": None},
    )
    attempt = await http_json(
        client,
        "POST",
        f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][exam]}/attempts",
        token,
        json={"registration_id": registration["id"], "expected_version": registration["version"]},
    )
    return registration, attempt


async def test_live_events_are_isolated_and_cross_process(seeded):
    s = seeded
    async with (
        run_server(s["url"]) as first,
        run_server(s["url"]) as second,
        httpx.AsyncClient(base_url=second) as client,
    ):
        registration_a, attempt_a = await create_running_attempt(client, s, exam=0, project="manager")
        registration_b, attempt_b = await create_running_attempt(client, s, exam=1, project="manager2")
        teacher = token_for(s["users"]["teacher"])
        async with live_socket(first, s["workspace"], s["exams"][0], teacher) as ws_a:
            hello_a = await receive(ws_a, "hello")
            snapshot_a = await receive(ws_a)
            assert hello_a["access"] == {"role": "organizer", "can_manage": True}
            assert snapshot_a["exam"]["id"] == s["exams"][0]
            assert snapshot_a["queue"]["items"][0]["registration_id"] == registration_a["id"]

            async with live_socket(second, s["workspace"], s["exams"][1], teacher) as ws_b:
                await receive(ws_b, "hello")
                snapshot_b = await receive(ws_b)
                assert snapshot_b["exam"]["id"] == s["exams"][1]

                questions = await http_json(
                    client,
                    "POST",
                    f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt_a['id']}/questions",
                    teacher,
                    json={"expected_version": attempt_a["version"]},
                )
                changed = await receive(ws_a)
                assert changed["reason"] == "changed"
                assert changed["exam"]["id"] == s["exams"][0]
                assert changed["queue"]["queue_revision"] == snapshot_a["queue"]["queue_revision"]
                assert changed["queue"]["items"][0]["attempt"]["version"] == questions["version"]
                assert changed["stream_seq"] > snapshot_a["stream_seq"]

                with pytest.raises(TimeoutError):
                    await receive(ws_b, timeout=1.5)
                assert attempt_b["registration_id"] == registration_b["id"]


async def test_reconnect_returns_full_snapshot_without_resetting_timer(seeded):
    s = seeded
    teacher = token_for(s["users"]["teacher"])
    async with run_server(s["url"]) as base, httpx.AsyncClient(base_url=base) as client:
        _, attempt = await create_running_attempt(client, s, exam=0, project="manager")
        async with live_socket(base, s["workspace"], s["exams"][0], teacher) as websocket:
            await receive(websocket, "hello")
            first = await receive(websocket)
            deadline = first["queue"]["items"][0]["attempt"]["phase_deadline"]
            remaining = first["queue"]["items"][0]["attempt"]["remaining_seconds"]
            last_seq = first["stream_seq"]

        await asyncio.sleep(1.2)
        async with live_socket(base, s["workspace"], s["exams"][0], teacher, last_stream_seq=last_seq) as websocket:
            await receive(websocket, "hello")
            second = await receive(websocket)
            attempt_state = second["queue"]["items"][0]["attempt"]
            assert second["reason"] == "reconnect"
            assert second["stream_seq"] >= last_seq
            assert attempt_state["phase_deadline"] == deadline
            assert attempt_state["remaining_seconds"] <= remaining - 1
            assert attempt["registration_id"] == second["queue"]["items"][0]["registration_id"]


async def test_pause_survives_disconnect_and_resume_moves_deadline(seeded):
    s = seeded
    teacher = token_for(s["users"]["teacher"])
    async with run_server(s["url"]) as base, httpx.AsyncClient(base_url=base) as client:
        _, attempt = await create_running_attempt(client, s, exam=0, project="manager")
        async with live_socket(base, s["workspace"], s["exams"][0], teacher) as websocket:
            await receive(websocket, "hello")
            first = await receive(websocket)
            deadline = first["queue"]["items"][0]["attempt"]["phase_deadline"]

        paused = await http_json(
            client,
            "POST",
            f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt['id']}/pause",
            teacher,
            json={"expected_version": attempt["version"], "reason": "Перерыв"},
        )
        async with live_socket(
            base, s["workspace"], s["exams"][0], teacher, last_stream_seq=first["stream_seq"]
        ) as websocket:
            await receive(websocket, "hello")
            snapshot = await receive(websocket)
            state = snapshot["queue"]["items"][0]["attempt"]
            assert state["paused_at"] is not None
            assert state["phase_deadline"] == deadline
            assert state["remaining_seconds"] == paused["remaining_seconds"]

            resumed = await http_json(
                client,
                "POST",
                f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt['id']}/resume",
                teacher,
                json={"expected_version": paused["version"]},
            )
            changed = await receive(websocket)
            state = changed["queue"]["items"][0]["attempt"]
            assert state["paused_at"] is None
            assert state["phase_deadline"] != deadline
            assert state["phase_deadline"] == resumed["phase_deadline"]


async def test_stream_sequence_is_strictly_increasing_and_after_commit(seeded):
    s = seeded
    teacher = token_for(s["users"]["teacher"])
    async with run_server(s["url"]) as base, httpx.AsyncClient(base_url=base) as client:
        _, attempt = await create_running_attempt(client, s, exam=0, project="manager")
        async with live_socket(base, s["workspace"], s["exams"][0], teacher) as websocket:
            await receive(websocket, "hello")
            snapshot = await receive(websocket)
            sequences = [snapshot["stream_seq"]]
            version = attempt["version"]

            for action in ("questions", "pause", "resume"):
                if action == "pause":
                    body = {"expected_version": version, "reason": "Перерыв"}
                else:
                    body = {"expected_version": version}
                result = await http_json(
                    client,
                    "POST",
                    f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt['id']}/{action}",
                    teacher,
                    json=body,
                )
                version = result["version"]
                message = await receive(websocket)
                sequences.append(message["stream_seq"])
                async with s["uow"]() as u:
                    persisted = await u.session.scalar(select(Exam.stream_seq).where(Exam.id == s["exams"][0]))
                assert message["stream_seq"] == persisted

            assert sequences == sorted(set(sequences))
            assert len(sequences) == 4
            assert message["queue"]["queue_revision"] == snapshot["queue"]["queue_revision"]


async def test_rollback_does_not_publish_a_live_snapshot(seeded):
    s = seeded
    teacher = token_for(s["users"]["teacher"])
    async with run_server(s["url"]) as base, live_socket(base, s["workspace"], s["exams"][0], teacher) as websocket:
        await receive(websocket, "hello")
        snapshot = await receive(websocket)
        before = snapshot["stream_seq"]
        with pytest.raises(RuntimeError):
            async with s["uow"]() as u:
                u.mark_exam_changed(s["exams"][0], "attempt")
                await u.session.flush()
                raise RuntimeError("rollback")
        with pytest.raises(TimeoutError):
            await receive(websocket, timeout=1.5)
        async with s["uow"]() as u:
            persisted = await u.session.scalar(select(Exam.stream_seq).where(Exam.id == s["exams"][0]))
        assert persisted == before


async def test_finish_delivers_window_metadata_without_admission(seeded):
    s = seeded
    teacher = token_for(s["users"]["teacher"])
    async with run_server(s["url"]) as base, httpx.AsyncClient(base_url=base) as client:
        _, attempt = await create_running_attempt(client, s, exam=0, project="manager")
        async with live_socket(base, s["workspace"], s["exams"][0], teacher) as websocket:
            await receive(websocket, "hello")
            await receive(websocket)
            finished = await http_json(
                client,
                "POST",
                f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt['id']}/finish",
                teacher,
                json={"expected_version": attempt["version"]},
            )
            snapshot = await receive(websocket)
            assert "window" in snapshot["changed"]
            assert finished["assessment_window"] is not None
            windows = snapshot["assessment_windows"]
            assert len(windows) == 1
            assert windows[0]["closes_at"] == finished["assessment_window"]["closes_at"]
            assert "admitted" not in windows[0]
            assert "can_submit" not in windows[0]


async def test_bad_origin_is_rejected(seeded):
    s = seeded
    teacher = token_for(s["users"]["teacher"])
    async with run_server(s["url"]) as base:
        with pytest.raises(websockets.ConnectionClosed) as error:
            async with live_socket(
                base, s["workspace"], s["exams"][0], teacher, origin="https://evil.example"
            ) as websocket:
                await websocket.recv()
        assert error.value.code == 4403


async def test_access_revocation_closes_the_connection(seeded):
    s = seeded
    member = s["users"]["member"]
    token = token_for(member)
    async with run_server(s["url"]) as base, live_socket(base, s["workspace"], s["exams"][0], token) as websocket:
        await receive(websocket, "hello")
        await receive(websocket)
        async with s["uow"]() as u:
            await u.session.execute(
                delete(WorkSpaceParticipation).where(
                    WorkSpaceParticipation.workspace_id == s["workspace"],
                    WorkSpaceParticipation.participant_id == member.id,
                )
            )
        assert await wait_for_close(websocket) == 4404


async def test_connection_limit_is_enforced(seeded):
    s = seeded
    teacher = token_for(s["users"]["teacher"])
    async with (
        run_server(s["url"], max_per_exam=1) as base,
        live_socket(base, s["workspace"], s["exams"][0], teacher) as first,
    ):
        await receive(first, "hello")
        await receive(first)
        async with live_socket(base, s["workspace"], s["exams"][0], teacher) as second:
            assert await wait_for_close(second) == 4429


async def test_invalid_token_is_rejected_before_any_data(seeded):
    s = seeded
    async with (
        run_server(s["url"]) as base,
        live_socket(base, s["workspace"], s["exams"][0], "not-a-token") as websocket,
    ):
        assert await wait_for_close(websocket) == 4401


async def test_draft_is_rejected_for_viewer(seeded):
    s = seeded
    async with (
        run_server(s["url"]) as base,
        live_socket(base, s["workspace"], s["draft"], token_for(s["users"]["manager"])) as websocket,
    ):
        assert await wait_for_close(websocket) == 4404


async def test_first_message_must_be_auth(seeded):
    s = seeded
    async with run_server(s["url"]) as base:
        uri = f"{base.replace('http://', 'ws://')}/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/live"
        async with websockets.connect(uri) as websocket:
            await websocket.send(json.dumps({"type": "resync"}))
            assert await wait_for_close(websocket) == 4400


async def test_heartbeat_and_client_resync(seeded):
    s = seeded
    teacher = token_for(s["users"]["teacher"])
    async with (
        run_server(s["url"]) as base,
        live_socket(base, s["workspace"], s["exams"][0], teacher) as websocket,
    ):
        await receive(websocket, "hello")
        snapshot = await receive(websocket)
        heartbeat = await receive(websocket, "heartbeat")
        assert heartbeat["stream_seq"] == snapshot["stream_seq"]
        assert heartbeat["queue_revision"] == snapshot["queue"]["queue_revision"]
        assert heartbeat["settings_version"] == snapshot["queue"]["settings_version"]

        await websocket.send(json.dumps({"type": "resync"}))
        resynced = await receive(websocket)
        assert resynced["reason"] == "resync"
        assert resynced["exam"]["id"] == s["exams"][0]


async def test_viewer_receives_queue_without_manage_flag(seeded):
    s = seeded
    async with (
        run_server(s["url"]) as base,
        live_socket(base, s["workspace"], s["exams"][0], token_for(s["users"]["manager"])) as websocket,
    ):
        hello = await receive(websocket, "hello")
        snapshot = await receive(websocket)
        assert hello["access"] == {"role": "viewer", "can_manage": False}
        assert snapshot["exam"]["id"] == s["exams"][0]
        assert "queue" in snapshot
