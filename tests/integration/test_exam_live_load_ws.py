"""Consistent WebSocket load of one exam: ~150 clients, mutations while connecting, mass reconnect (#118).

Real uvicorn processes with a shared PostgreSQL (two "workers", like production). The number of clients is
`EXAM_LOAD_CLIENTS` (150 locally, CI lowers it). Run with `-s` to see the measured numbers.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import io
import json
import os
import statistics
import time
import zipfile
from dataclasses import dataclass, field

import httpx
import pytest
import pytest_asyncio
import test_exam_live_ws as live
import websockets
from sqlalchemy import select, text
from test_exam_acceptance_db import apply_template
from test_exam_reliability_db import add_assessors
from test_exam_results_db import set_participation

from src.core.config import settings
from src.model.exam import Exam

pytestmark = pytest.mark.integration

seeded = live.seeded
CLIENTS = int(os.environ.get("EXAM_LOAD_CLIENTS", "150"))
ASSESSORS = int(os.environ.get("EXAM_LOAD_ASSESSORS", "120"))
OTHER_CLIENTS = max(CLIENTS // 5, 3)
BASE_CLIENTS = 5
FORBIDDEN_CLOSES = {4408, 4429, 4404, 4401, 4403, 4400, 4409, 1011}
# Idle intervals are long on purpose: the only database work left is the connection setup and real mutations.
QUIET_ENV = {
    "EXAM_LIVE_HEARTBEAT_SECONDS": "3600",
    "EXAM_LIVE_RECONCILE_SECONDS": "3600",
    "EXAM_LIVE_ACCESS_CHECK_SECONDS": "3600",
    "EXAM_LIVE_AUTH_TIMEOUT_SECONDS": "30",
    "EXAM_LIVE_SEND_TIMEOUT_SECONDS": "30",
}


@dataclass
class Client:
    exam_id: int
    workspace_id: int
    last_seq: int = -1
    snapshots: int = 0
    reasons: list[str] = field(default_factory=list)
    foreign: int = 0
    non_monotonic: int = 0
    close_code: int | None = None
    first: dict | None = None
    latest: dict | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None


async def client_loop(base: str, client: Client, token: str, *, last_stream_seq: int | None = None) -> None:
    uri = f"{base.replace('http://', 'ws://')}/v1/workspaces/{client.workspace_id}/exams/{client.exam_id}/live"
    try:
        async with websockets.connect(uri, open_timeout=60, max_size=None) as websocket:
            auth = {"type": "auth", "token": token}
            if last_stream_seq is not None:
                auth["last_stream_seq"] = last_stream_seq
            await websocket.send(json.dumps(auth))
            while not client.stop.is_set():
                try:
                    raw = await asyncio.wait_for(websocket.recv(), 0.25)
                except TimeoutError:
                    continue
                message = json.loads(raw)
                if message.get("type") != "snapshot":
                    continue
                if message["exam"]["id"] != client.exam_id or message["exam"]["workspace_id"] != client.workspace_id:
                    client.foreign += 1
                if message["stream_seq"] < client.last_seq:
                    client.non_monotonic += 1
                client.last_seq = max(client.last_seq, message["stream_seq"])
                client.snapshots += 1
                client.reasons.append(message["reason"])
                client.latest = message
                if client.first is None:
                    client.first = message
                client.ready.set()
    except websockets.ConnectionClosed as error:
        client.close_code = int(error.code or 0)
    except Exception as error:
        client.close_code = -1
        client.latest = {"error": repr(error)}
    finally:
        client.ready.set()


def spawn(base, client, token, **kwargs):
    client.task = asyncio.create_task(client_loop(base, client, token, **kwargs))


async def stop_all(clients):
    for client in clients:
        client.stop.set()
    await asyncio.gather(*(c.task for c in clients if c.task), return_exceptions=True)


@contextlib.asynccontextmanager
async def sample_connections(engine):
    peak = {"max": 0, "samples": [], "paused": False}
    stop = asyncio.Event()

    async def sampler():
        while not stop.is_set():
            if peak["paused"]:
                await asyncio.sleep(0.05)
                continue
            async with engine.connect() as connection:
                count = await connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                        "AND application_name = ''"
                    )
                )
            peak["samples"].append(int(count))
            peak["max"] = max(peak["max"], int(count))
            await asyncio.sleep(0.1)

    task = asyncio.create_task(sampler())
    try:
        yield peak
    finally:
        stop.set()
        await task


class Driver:
    """HTTP side of the scenario: the teacher drives the queue of one exam."""

    def __init__(self, client: httpx.AsyncClient, s: dict, exam: int):
        self.client = client
        self.s = s
        self.exam = exam
        self.token = live.token_for(s["users"]["teacher"])
        self.prefix = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][exam]}"

    async def call(self, method: str, path: str, **kwargs):
        return await live.http_json(self.client, method, f"{self.prefix}{path}", self.token, **kwargs)

    async def register(self, project: str) -> dict:
        return await self.call(
            "POST", "/registrations", json={"project_id": self.s["projects"][project], "slot_id": None}
        )

    async def start(self, registration: dict) -> dict:
        return await self.call(
            "POST",
            "/attempts",
            json={"registration_id": registration["id"], "expected_version": registration["version"]},
        )

    async def attempt_command(self, attempt: dict, command: str, **extra) -> dict:
        return await self.call(
            "POST",
            f"/attempts/{attempt['id']}/{command}",
            json={"expected_version": attempt["version"], **extra},
        )

    async def queue(self) -> dict:
        return await self.call("GET", "/queue")

    async def registration_version(self, registration_id: int) -> int:
        for item in (await self.queue())["items"]:
            if item["registration_id"] == registration_id:
                return item["registration_version"]
        raise AssertionError("registration is not in the queue")

    async def queue_command(self, registration_id: int, command: str, **extra) -> dict:
        version = await self.registration_version(registration_id)
        return await self.call(
            "POST", f"/queue/{registration_id}/{command}", json={"expected_version": version, **extra}
        )


async def queue_scenario(driver: Driver, attempt: dict) -> dict:
    """Pauses/resumes the running defence, queues two more teams, postpones and returns one. Ends paused."""
    for _ in range(2):
        attempt = await driver.attempt_command(attempt, "pause", reason="Перерыв")
        attempt = await driver.attempt_command(attempt, "resume")
    second = await driver.register("manager2")
    third = await driver.register("member")
    await driver.queue_command(second["id"], "postpone", reason="Проектор")
    await driver.queue_command(second["id"], "place")
    await driver.queue_command(third["id"], "no-show", reason="Не пришли")
    attempt = await driver.attempt_command(attempt, "pause", reason="Финальная пауза")
    return attempt


async def toggle(driver: Driver, attempt: dict, pairs: int) -> dict:
    """`pairs` pause/resume pairs = 2*pairs mutations that each change the live state exactly once (starts running)."""
    for _ in range(pairs):
        attempt = await driver.attempt_command(attempt, "pause", reason="Замер")
        attempt = await driver.attempt_command(attempt, "resume")
    return attempt


async def converged(clients, engine, exam_id, timeout=20.0) -> int:
    """Waits until every client holds the exam's final stream_seq (the database is read once, polling is in memory)."""
    async with engine.connect() as connection:
        seq = int(await connection.scalar(select(Exam.stream_seq).where(Exam.id == exam_id)))
    deadline = time.monotonic() + timeout
    while True:
        laggards = [c for c in clients if c.last_seq != seq]
        if not laggards:
            return seq
        if time.monotonic() > deadline:
            raise AssertionError(
                f"{len(laggards)} of {len(clients)} clients did not reach stream_seq={seq}: "
                f"{sorted({c.last_seq for c in laggards})}, closes={[c.close_code for c in laggards if c.close_code]}"
            )
        await asyncio.sleep(0.05)


def strip_time(queue: dict) -> dict:
    """Queue without the fields that legitimately depend on the moment of reading."""
    cleaned = json.loads(json.dumps(queue))

    def drop_clock(node):
        if isinstance(node, dict):
            node.pop("server_now", None)
            for value in node.values():
                drop_clock(value)
        elif isinstance(node, list):
            for value in node:
                drop_clock(value)

    drop_clock(cleaned)
    for item in cleaned["items"]:
        attempt = item.get("attempt")
        if attempt:
            attempt.pop("remaining_seconds", None) if not attempt.get("paused_at") else None
    for eta in cleaned["eta"]["items"]:
        eta.pop("eta_seconds", None)
        eta.pop("eta_at", None)
    current = cleaned["eta"]["current"]
    if current:
        for key in ("phase_remaining_seconds", "slot_remaining_seconds", "overdue_seconds"):
            current.pop(key, None)
    return cleaned


async def test_consistent_load_with_mutations_and_mass_reconnect(seeded):
    s = seeded
    teacher = live.token_for(s["users"]["teacher"])
    workspace, exam_main, exam_other = s["workspace"], s["exams"][0], s["exams"][1]
    report: dict[str, object] = {"clients": CLIENTS, "other_clients": OTHER_CLIENTS}
    async with (
        live.run_server(s["url"], extra_env=QUIET_ENV) as server_a,
        live.run_server(s["url"], extra_env=QUIET_ENV) as server_b,
        httpx.AsyncClient(base_url=server_b, timeout=60) as http,
        sample_connections(s["engine"]) as connections,
    ):
        servers = [server_a, server_b]
        main_driver, other_driver = Driver(http, s, 0), Driver(http, s, 1)
        main = [Client(exam_main, workspace) for _ in range(CLIENTS)]
        other = [Client(exam_other, workspace) for _ in range(OTHER_CLIENTS)]

        # Phase 1: a few clients on a quiet exam.
        first_attempt = await main_driver.start(await main_driver.register("manager"))
        for index, client in enumerate(main[:BASE_CLIENTS]):
            spawn(servers[index % 2], client, teacher)
        await asyncio.gather(*(c.ready.wait() for c in main[:BASE_CLIENTS]))
        await converged(main[:BASE_CLIENTS], s["engine"], exam_main)
        first_attempt = await toggle(main_driver, first_attempt, 3)
        await converged(main[:BASE_CLIENTS], s["engine"], exam_main)
        await stop_all(main[:BASE_CLIENTS])
        main[:BASE_CLIENTS] = [Client(exam_main, workspace) for _ in range(BASE_CLIENTS)]

        # Phase 2: everybody connects at once while the queue is being mutated.
        started = time.monotonic()
        for index, client in enumerate(main):
            spawn(servers[index % 2], client, teacher)
        for index, client in enumerate(other):
            spawn(servers[index % 2], client, teacher)
        other_attempt = await other_driver.start(await other_driver.register("local_manager"))
        final_attempt = await queue_scenario(main_driver, first_attempt)
        await asyncio.gather(*(c.ready.wait() for c in [*main, *other]))
        report["connect_seconds"] = round(time.monotonic() - started, 2)
        await other_driver.attempt_command(other_attempt, "pause", reason="Другой экзамен")
        seq_main = await converged(main, s["engine"], exam_main)
        seq_other = await converged(other, s["engine"], exam_other)

        assert all(c.close_code is None for c in [*main, *other]), [c.close_code for c in main if c.close_code]
        assert all(c.foreign == 0 and c.non_monotonic == 0 for c in [*main, *other])
        assert {c.latest["exam"]["id"] for c in main} == {exam_main}
        assert {c.latest["exam"]["id"] for c in other} == {exam_other}
        main_attempts = {item["attempt"]["id"] for c in main for item in c.latest["queue"]["items"] if item["attempt"]}
        other_attempts = {
            item["attempt"]["id"] for c in other for item in c.latest["queue"]["items"] if item["attempt"]
        }
        assert main_attempts.isdisjoint(other_attempts)

        # Phase 3: a second burst of mutations with every client connected still reaches everybody.
        resumed = await main_driver.attempt_command(final_attempt, "resume")
        await toggle(main_driver, resumed, 3)
        seq_main = await converged(main, s["engine"], exam_main)

        # Phase 4: stop the world, reconnect everybody at once, compare with HTTP.
        await main_driver.attempt_command(
            await main_driver.call("GET", f"/attempts/{final_attempt['id']}"), "pause", reason="Перед reconnect"
        )
        seq_main = await converged(main, s["engine"], exam_main)
        remembered = {id(c): c.last_seq for c in [*main, *other]}
        await stop_all([*main, *other])
        reconnected = [Client(exam_main, workspace) for _ in range(CLIENTS)] + [
            Client(exam_other, workspace) for _ in range(OTHER_CLIENTS)
        ]
        for index, (old, client) in enumerate(zip([*main, *other], reconnected, strict=True)):
            spawn(servers[(index + 1) % 2], client, teacher, last_stream_seq=remembered[id(old)])
        started = time.monotonic()
        await asyncio.gather(*(c.ready.wait() for c in reconnected))
        report["reconnect_seconds"] = round(time.monotonic() - started, 2)
        assert all(c.close_code is None for c in reconnected), [c.close_code for c in reconnected if c.close_code]
        assert all(c.first and c.first["reason"] == "reconnect" and not c.first["stale"] for c in reconnected)
        http_queue = strip_time(await main_driver.queue())
        for client in reconnected[:CLIENTS]:
            assert client.first["stream_seq"] == seq_main
            assert strip_time(client.first["queue"]) == http_queue
        other_queue = strip_time(await other_driver.queue())
        for client in reconnected[CLIENTS:]:
            assert strip_time(client.first["queue"]) == other_queue
        assert seq_other == reconnected[CLIENTS].first["stream_seq"]
        await stop_all(reconnected)
        assert all(c.close_code is None for c in reconnected)

    cap = 2 * (settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW + 1)
    assert connections["max"] <= cap + 6, (connections["max"], cap)
    report["peak_database_connections"] = connections["max"]
    report["median_database_connections"] = statistics.median(connections["samples"] or [0])
    report["server_processes"] = 2
    print("\nEXAM_LOAD_REPORT " + json.dumps(report, ensure_ascii=False, sort_keys=True))
    assert seq_main > 0


@pytest_asyncio.fixture(loop_scope="function")
async def five(seeded):
    """Seeded exam: five criteria on the project type, the teacher takes part in the workspace (CSV needs it)."""
    await set_participation(seeded, "teacher", local=None)
    await apply_template(seeded)
    return seeded


async def test_burst_of_submits_with_parallel_websocket_keeps_the_pool_bounded_and_the_export_consistent(five):
    s = five
    names = await add_assessors(s, ASSESSORS)
    teacher = live.token_for(s["users"]["teacher"])
    workspace, exam = s["workspace"], s["exams"][0]
    report: dict[str, object] = {"assessors": ASSESSORS, "websocket_clients": CLIENTS // 2}
    async with (
        live.run_server(s["url"], extra_env=QUIET_ENV) as server_a,
        live.run_server(s["url"], extra_env=QUIET_ENV) as server_b,
        httpx.AsyncClient(base_url=server_a, timeout=120, limits=httpx.Limits(max_connections=None)) as http_a,
        httpx.AsyncClient(base_url=server_b, timeout=120, limits=httpx.Limits(max_connections=None)) as http_b,
        sample_connections(s["engine"]) as connections,
    ):
        driver = Driver(http_a, s, 0)
        attempt = await driver.start(await driver.register("manager"))
        sockets = [Client(exam, workspace) for _ in range(CLIENTS // 2)]
        for index, client in enumerate(sockets):
            spawn((server_a, server_b)[index % 2], client, teacher)
        await asyncio.gather(*(c.ready.wait() for c in sockets))
        finished = await driver.attempt_command(attempt, "finish")
        window = finished["assessment_window"]
        assert window is not None
        await converged(sockets, s["engine"], exam)

        async def assessor(index: int, name: str) -> int:
            client = (http_a, http_b)[index % 2]
            token = live.token_for(s["users"][name])
            path = f"{driver.prefix}/attempts/{attempt['id']}/assessment"
            headers = {"Authorization": f"Bearer {token}"}
            form = await client.get(path, headers=headers)
            if form.status_code != 200:
                return form.status_code
            answers = [{"question_id": q["id"], "score": 1 + index % 5} for q in form.json()["questions"]]
            saved = await client.put(f"{path}/draft", headers=headers, json={"answers": answers})
            if saved.status_code != 200:
                return saved.status_code
            return (await client.post(f"{path}/submit", headers=headers)).status_code

        started = time.monotonic()
        statuses = await asyncio.gather(*(assessor(i, n) for i, n in enumerate(names)))
        report["burst_seconds"] = round(time.monotonic() - started, 2)
        assert set(statuses) == {200}, {code: statuses.count(code) for code in set(statuses)}
        assert all(c.close_code is None for c in sockets)

        async with s["engine"].connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT sh.user_id, count(su.id), max(su.version) FROM exam_assessment_sheet sh "
                        "JOIN exam_assessment_submission su ON su.sheet_id = sh.id GROUP BY sh.user_id"
                    )
                )
            ).all()
        assert len(rows) == ASSESSORS and {(r[1], r[2]) for r in rows} == {(1, 1)}  # one edition per assessor

        export = await http_b.get(f"{driver.prefix}/exports/csv", headers={"Authorization": f"Bearer {teacher}"})
        assert export.status_code == 200, export.text[:300]
        report["export_bytes"] = len(export.content)
        await stop_all(sockets)

    with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
        register = list(
            csv.DictReader(io.StringIO(archive.read("assessment-register.csv").decode("utf-8-sig")), delimiter=";")
        )
        people = list(
            csv.DictReader(io.StringIO(archive.read("assessment-participation.csv").decode("utf-8-sig")), delimiter=";")
        )
    row = next(r for r in register if int(r["attempt_id"]) == attempt["id"])
    assert int(row["submitted_count"]) == ASSESSORS
    assert (
        sum(p["response_status"] == "submitted" for p in people if int(p["attempt_id"]) == attempt["id"]) == ASSESSORS
    )

    cap = 2 * (settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW + 1)
    report["peak_database_connections"] = connections["max"]
    report["pool_cap_for_2_processes"] = cap
    print("\nEXAM_BURST_REPORT " + json.dumps(report, sort_keys=True))
    assert connections["max"] <= cap + 6  # + the test's own pooled connections
