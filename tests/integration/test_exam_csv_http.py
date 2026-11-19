from __future__ import annotations

import asyncio
import csv
import io
import socket
import zipfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import test_exam_live_ws as live_cases
import test_exam_results_db as results_cases
import uvicorn
from fastapi import FastAPI
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from test_exam_assessment_submit_db import draft, result_service, submit
from test_exam_attempts_db import organized, set_settings
from test_exam_results_db import finished_attempt

from src.api.v1.routes import routers
from src.core import container
from src.core.config import settings
from src.core.exam_csv_dependencies import get_exam_csv_user
from src.core.uow import SqlAlchemyUoW
from src.repository.exam_csv_repository import ExamCsvRepository
from src.schema.exam_result import ResultManual
from src.services.exam_csv_service import ExamCsvService
from src.util.csv_export import CsvExporter

pytestmark = pytest.mark.integration
seeded_base = results_cases.seeded_base
seeded = results_cases.seeded


def app_for(s, actor="teacher", **kwargs):
    app = FastAPI()
    app.include_router(routers)
    app.dependency_overrides[get_exam_csv_user] = lambda: s["users"][actor]
    app.dependency_overrides[container.get_exam_csv_service] = lambda: ExamCsvService(s["uow"], **kwargs)
    return app


def url(s, *, workspace=None, exam=0):
    return f"/v1/workspaces/{workspace or s['workspace']}/exams/{s['exams'][exam]}/exports/csv"


async def download(s, *, actor="teacher", path=None, **kwargs):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_for(s, actor, **kwargs)), base_url="http://test"
    ) as client:
        return await client.get(path or url(s))


def parse(response):
    assert response.status_code == 200, response.text if response.status_code != 200 else ""
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["assessment-register.csv", "assessment-participation.csv"]
        output = []
        for name in archive.namelist():
            raw = archive.read(name)
            assert raw.startswith(b"\xef\xbb\xbf") and raw.count(b"\xef\xbb\xbf") == 1
            assert b"\r\n" in raw
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter=";")
            output.append((reader.fieldnames, list(reader)))
        return output


async def test_empty_http_pair_has_stable_headers(seeded):
    (register_header, register), (participation_header, participation) = parse(await download(seeded))
    assert not register and not participation
    assert "registration_id" in register_header and "criterion_5_score" in participation_header
    assert (await download(seeded)).headers["cache-control"] == "no-store"


async def test_live_tcp_http_pair_reconciles_every_attempt_and_all_registered_states(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "teacher", 4)
    await submit(s, attempt, "teacher")
    await draft(s, attempt, "member", 2)  # draft is not a vote
    async with s["uow"]() as u:
        await result_service(u).manual(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            ResultManual(expected_version=0, final_score="17.50", reason='Устно; "да"\nстрока'),
            s["users"]["teacher"],
        )
    for project, hold, status in [
        ("manager2", None, "active"),
        ("member", "postponed", "active"),
        ("local_manager", "no_show", "active"),
        ("demoted", None, "cancelled"),
        ("null_manager", None, "moved"),
    ]:
        reg = await organized(s, project=project)
        async with s["uow"]() as u:
            await u.session.execute(
                text("UPDATE exam_registration SET queue_position=NULL, queue_hold=:h,status=:s WHERE id=:i"),
                {"h": hold, "s": status, "i": reg.id},
            )
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE project SET name=:n WHERE id=:p"),
            {"n": '  =Команда; "Альфа"\nвторая строка', "p": s["projects"]["manager"]},
        )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app_for(s), log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                await asyncio.sleep(0.01)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            response = await client.get(url(s))
        (_, register), (_, participation) = parse(response)
    finally:
        server.should_exit = True
        await task
        sock.close()
    assert len(register) == 6
    assert {r["registration_status"] for r in register} == {"active", "cancelled", "moved"}
    assert {r["defense_status"] for r in register} >= {"finished", "not_started", "postponed", "no_show"}
    for row in register:
        people = [p for p in participation if p["attempt_id"] == row["attempt_id"]]
        if row["attempt_id"]:
            counts = Counter(p["response_status"] for p in people)
            assert int(row["submitted_count"]) == counts["submitted"]
            assert int(row["eligible_count"]) == counts["submitted"] + counts["not_submitted"]
            assert int(row["excluded_count"]) == counts["excluded"]
            assert len(people) == len({p["assessor_id"] for p in people})
            assert row["calculated_score"] == "20.00" and row["final_score"] == "17.50"
            assert row["project_name"].startswith("'  =Команда;")
            assert row["reason"] == 'Устно; "да"\nстрока'
        else:
            assert row["eligible_count"] == row["calculated_score"] == row["final_score"] == ""
    assert {r["export_id"] for r in register} == {p["export_id"] for p in participation}
    assert {r["snapshot_at"] for r in register} == {p["snapshot_at"] for p in participation}
    assert not s["engine"].pool.checkedout()


@pytest.mark.parametrize(
    "actor,code", [("teacher", 200), ("local_admin", 200), ("member", 403), ("admin", 403), ("outsider", 404)]
)
async def test_http_permissions(seeded, actor, code):
    assert (await download(seeded, actor=actor)).status_code == code


async def test_api_startup_preserves_workspace_roles_for_results_and_exports(seeded):
    await results_cases.set_participation(seeded, "teacher", local="member")
    registry = url(seeded).removesuffix("/exports/csv") + "/results"

    async with live_cases.run_server(seeded["url"]) as base, httpx.AsyncClient(base_url=base) as client:
        for actor, expected in (("teacher", 403), ("local_teacher", 200), ("local_admin", 200), ("admin", 403)):
            token = live_cases.token_for(seeded["users"][actor])
            for path in (registry, url(seeded)):
                response = await client.get(path, headers={"Authorization": f"Bearer {token}"})
                assert response.status_code == expected, (actor, path, response.text)

    async with seeded["engine"].connect() as connection:
        role = (
            await connection.execute(
                text("SELECT role_id FROM workspace_participation WHERE workspace_id=:w AND participant_id=:u"),
                {"w": seeded["workspace"], "u": seeded["users"]["null_manager"].id},
            )
        ).scalar_one()
    assert role is None


async def test_http_foreign_workspace_and_invalid_ids(seeded):
    assert (await download(seeded, path=url(seeded, workspace=seeded["foreign_workspace"]))).status_code == 404
    assert (await download(seeded, path="/v1/workspaces/0/exams/1/exports/csv")).status_code == 422


async def test_parallel_change_between_source_reads_cannot_split_pair(seeded, monkeypatch):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "teacher", 4)
    await submit(s, attempt, "teacher")
    original = ExamCsvRepository.registrations

    async def concurrent_write(repo):
        rows = await original(repo)
        await draft(s, attempt, "teacher", 5)
        await submit(s, attempt, "teacher")
        return rows

    monkeypatch.setattr(ExamCsvRepository, "registrations", concurrent_write)
    (_, register), (_, participation) = parse(await download(s))
    teacher = next(p for p in participation if int(p["assessor_id"]) == s["users"]["teacher"].id)
    assert teacher["total"] == "4" and teacher["submission_version"] == "1"
    assert register[0]["calculated_score"] == "20.00"
    monkeypatch.setattr(ExamCsvRepository, "registrations", original)
    (_, register), (_, participation) = parse(await download(s))
    teacher = next(p for p in participation if int(p["assessor_id"]) == s["users"]["teacher"].id)
    assert teacher["total"] == "5" and register[0]["calculated_score"] == "25.00"


async def test_http_source_row_limit_is_explicit_and_closes_db(seeded):
    await organized(seeded)
    response = await download(seeded, max_rows=0)
    assert response.status_code == 413 and response.json()["detail"]["code"] == "csv_export_limit_exceeded"
    assert not seeded["engine"].pool.checkedout()


async def test_http_combined_byte_limit_and_second_writer_failure(seeded, monkeypatch):
    response = await download(seeded, max_bytes=10)
    assert response.status_code == 413
    original = CsvExporter.write
    calls = []

    def fail_second(self, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("second-file-write")
        return original(self, **kwargs)

    monkeypatch.setattr(CsvExporter, "write", fail_second)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_for(seeded), raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.get(url(seeded))
    assert response.status_code == 500 and response.content == b"Internal Server Error"
    assert not seeded["engine"].pool.checkedout()


async def test_cancellation_during_snapshot_releases_connection(seeded, monkeypatch):
    entered = asyncio.Event()
    original = ExamCsvRepository.registrations

    async def blocked(repo):
        await original(repo)
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ExamCsvRepository, "registrations", blocked)
    task = asyncio.create_task(download(seeded))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not seeded["engine"].pool.checkedout()


async def test_disconnect_during_response_has_no_database_or_file_resources(seeded):
    app = app_for(seeded)
    starts = []

    async def send(message):
        if message["type"] == "http.response.start":
            starts.append(message["status"])
            assert not seeded["engine"].pool.checkedout()
        elif message["type"] == "http.response.body":
            raise asyncio.CancelledError()

    async def receive():
        return {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": url(seeded),
        "raw_path": url(seeded).encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 80),
    }
    with pytest.raises(asyncio.CancelledError):
        await app(scope, receive, send)
    assert starts == [200] and not seeded["engine"].pool.checkedout()


async def test_missing_historical_snapshot_returns_409_without_partial_pair(seeded):
    await finished_attempt(seeded)
    async with seeded["uow"]() as u:
        await u.session.execute(text("DELETE FROM assessment_window_audience"))
    response = await download(seeded)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "audience_snapshot_unavailable"


async def test_no_token_is_401_before_opening_export_uow(seeded):
    app = FastAPI()
    app.include_router(routers)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(url(seeded))
    assert response.status_code == 401


async def test_parallel_new_result_and_settings_keep_old_result_edition(seeded, monkeypatch):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "teacher", 4)
    await submit(s, attempt, "teacher")
    async with s["uow"]() as u:
        await result_service(u).manual(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            ResultManual(expected_version=0, final_score="17.50", reason="First"),
            s["users"]["teacher"],
        )
    original = ExamCsvRepository.registrations

    async def concurrent_result(repo):
        rows = await original(repo)
        await set_settings(s, max_score=Decimal("100.00"))
        async with s["uow"]() as u:
            await result_service(u).manual(
                s["workspace"],
                s["exams"][0],
                attempt.id,
                ResultManual(expected_version=1, final_score="70.00", reason="Second"),
                s["users"]["teacher"],
            )
        return rows

    monkeypatch.setattr(ExamCsvRepository, "registrations", concurrent_result)
    (_, register), _ = parse(await download(s))
    assert (
        register[0]["result_version"],
        register[0]["settings_version"],
        register[0]["calculated_score"],
        register[0]["final_score"],
        register[0]["max_score"],
    ) == ("1", "1", "20.00", "17.50", "25.00")
    monkeypatch.setattr(ExamCsvRepository, "registrations", original)
    (_, register), _ = parse(await download(s))
    assert (
        register[0]["result_version"],
        register[0]["settings_version"],
        register[0]["calculated_score"],
        register[0]["final_score"],
        register[0]["max_score"],
    ) == ("2", "2", "80.00", "70.00", "100.00")
    async with s["uow"]() as u:
        old = (
            await u.session.execute(
                text("SELECT calculated_score,final_score,max_score FROM exam_result_edition WHERE version=1")
            )
        ).one()
    assert tuple(map(str, old)) == ("20.00", "17.50", "25.00")


async def test_real_bearer_auth_releases_connection_before_snapshot_and_response(seeded):
    s = seeded
    engine = create_async_engine(s["url"], pool_size=1, max_overflow=0, pool_timeout=0.5)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    def make_uow():
        uow = SqlAlchemyUoW()
        uow.session_factory = factory
        return uow

    app = FastAPI()
    app.include_router(routers)

    async def auth_uow():
        async with make_uow() as uow:
            yield uow

    app.dependency_overrides[container.get_uow] = auth_uow
    app.dependency_overrides[container.get_exam_csv_service] = lambda: ExamCsvService(make_uow)
    app.dependency_overrides[container.get_exam_csv_uow_factory] = lambda: make_uow
    sends = []

    class VerifyReleasedAtSend:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            async def checked_send(message):
                if message["type"] in ("http.response.start", "http.response.body"):
                    sends.append(engine.pool.checkedout())
                await send(message)

            await self.app(scope, receive, checked_send)

    app.add_middleware(VerifyReleasedAtSend)
    token = jwt.encode(
        {"sub": s["users"]["teacher"].email, "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            response = await client.get(url(s))
            parse(response)
            assert sends and all(count == 0 for count in sends)
            responses = await asyncio.gather(*(client.get(url(s)) for _ in range(3)))
            assert all(r.status_code == 200 for r in responses)
            assert not engine.pool.checkedout()
    finally:
        await engine.dispose()
