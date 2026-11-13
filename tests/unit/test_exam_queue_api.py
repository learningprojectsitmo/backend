from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_auth_service, get_exam_attempt_service, get_exam_queue_service, get_uow
from src.core.exceptions import AuthError, BusinessLogicError, NotFoundError, PermissionError
from src.schema.exam_queue import QueueEtaRead, QueueRead

BASE = "/v1/workspaces/7/exams/12/queue"
ATTEMPTS = "/v1/workspaces/7/exams/12/attempts"


def app_with(*, queue_service=None, attempt_service=None) -> FastAPI:
    app = FastAPI()
    app.include_router(routers)

    async def authenticate(token):
        if token != "valid":
            raise AuthError("Invalid token")
        return SimpleNamespace(id=7, email="teacher@example.test", role=SimpleNamespace(name="teacher"))

    app.dependency_overrides[get_auth_service] = lambda: SimpleNamespace(
        get_current_user=AsyncMock(side_effect=authenticate)
    )

    async def no_database():
        yield SimpleNamespace(session=SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("Unexpected DB"))))

    app.dependency_overrides[get_uow] = no_database
    if queue_service is not None:
        app.dependency_overrides[get_exam_queue_service] = lambda: queue_service
    if attempt_service is not None:
        app.dependency_overrides[get_exam_attempt_service] = lambda: attempt_service
    return app


def client(app: FastAPI, *, token: str = "valid") -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", ""),
        ("POST", "/91/place"),
        ("POST", "/91/next"),
        ("POST", "/91/postpone"),
        ("POST", "/91/no-show"),
    ],
)
async def test_queue_routes_require_authentication(method, path):
    async with client(app_with(), token="invalid") as http:
        response = await http.request(method, BASE + path, json={"expected_version": 1, "reason": "x"})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "path,body",
    [
        ("/0/place", {"expected_version": 1}),
        ("/91/place", {"expected_version": 0}),
        ("/91/place", {"expected_version": 1, "position": 0}),
        ("/91/place", {"expected_version": 1, "position": True}),
        ("/91/place", {"expected_version": 1, "position": 2**31}),
        ("/91/place", {"expected_version": 1, "extra": 1}),
        ("/91/place", {"expected_version": True}),
        ("/91/place", {"position": 1}),
        ("/91/next", {"expected_version": 1, "position": 2}),
        ("/91/postpone", {"expected_version": 1}),
        ("/91/postpone", {"expected_version": 1, "reason": "  "}),
        ("/91/postpone", {"expected_version": 1, "reason": "a\x00b"}),
        ("/91/postpone", {"expected_version": 1, "reason": None}),
        ("/91/postpone", {"expected_version": 1, "reason": 5}),
        ("/91/postpone", {"expected_version": 1, "reason": "x" * 1001}),
        ("/91/no-show", {"expected_version": 1, "reason": "x" * 1001}),
    ],
)
async def test_queue_body_and_path_are_strict(path, body):
    async with client(app_with()) as http:
        response = await http.post(BASE + path, json=body)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "error,status",
    [
        (PermissionError("no"), 403),
        (NotFoundError("no"), 404),
        (BusinessLogicError({"code": "attempt_finished", "message": "attempt finished"}), 409),
    ],
)
async def test_queue_errors_are_mapped(error, status):
    service = SimpleNamespace(place=AsyncMock(side_effect=error))
    async with client(app_with(queue_service=service)) as http:
        response = await http.post(BASE + "/91/place", json={"expected_version": 1})
    assert response.status_code == status
    if status == 409:
        assert response.json()["detail"]["code"] == "attempt_finished"


@pytest.mark.parametrize(
    "body",
    [
        {"expected_version": 1, "reason": "a\x00b"},
        {"expected_version": 1, "reason": ""},
        {"expected_version": 0},
        {"expected_version": 1, "extra": 1},
    ],
)
async def test_restart_body_is_strict(body):
    async with client(app_with()) as http:
        response = await http.post(ATTEMPTS + "/31/restart", json=body)
    assert response.status_code == 422


async def test_attempt_postpone_and_restart_require_authentication():
    async with client(app_with(), token="invalid") as http:
        postponed = await http.post(ATTEMPTS + "/31/postpone", json={"expected_version": 1, "reason": "x"})
        restarted = await http.post(ATTEMPTS + "/31/restart", json={"expected_version": 1})
    assert postponed.status_code == 401
    assert restarted.status_code == 401


async def test_queue_read_exposes_eta_contract():
    read_model = QueueRead(
        queue_revision=17,
        server_now=datetime(2026, 11, 30, 14, 0, tzinfo=UTC),
        settings_version=3,
        eta_stale=False,
        items=[],
        eta=QueueEtaRead(current=None, items=[]),
    )
    service = SimpleNamespace(read=AsyncMock(return_value=read_model))
    async with client(app_with(queue_service=service)) as http:
        response = await http.get(BASE)
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == 1
    assert body["settings_version"] == 3
    assert body["eta_stale"] is False
    assert body["eta"] == {"current": None, "items": []}
    assert body["server_now"].endswith("Z")
