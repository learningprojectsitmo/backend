from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_auth_service, get_exam_attempt_service, get_uow
from src.core.exceptions import AuthError
from src.schema.exam_attempt import AttemptRead, CurrentAttemptRead

NOW = datetime(2026, 11, 30, 7, 0, tzinfo=UTC)
BASE = "/v1/workspaces/7/exams/12/attempts"


def attempt_read(**overrides) -> AttemptRead:
    data = {
        "id": 31,
        "workspace_id": 7,
        "exam_id": 12,
        "registration_id": 91,
        "project_id": 42,
        "project_type_id": 8,
        "status": "speaking",
        "version": 1,
        "settings_version": 1,
        "started_at": NOW,
        "phase_started_at": NOW,
        "phase_deadline": NOW,
        "paused_at": None,
        "paused_seconds": 0,
        "finished_at": None,
        "created_by": 17,
        "created_at": NOW,
        "updated_at": NOW,
        "remaining_seconds": 420,
        "server_now": NOW,
        "assessment_window": None,
    }
    data.update(overrides)
    return AttemptRead.model_validate(data)


def app_with(service: object | None = None) -> FastAPI:
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
    if service is not None:
        app.dependency_overrides[get_exam_attempt_service] = lambda: service
    return app


def client(app: FastAPI, *, token: str = "valid", raise_app_exceptions: bool = False) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", ""),
        ("GET", "/current"),
        ("GET", "/31"),
        ("GET", "/31/events"),
        ("POST", "/31/questions"),
        ("POST", "/31/pause"),
        ("POST", "/31/resume"),
        ("POST", "/31/finish"),
    ],
)
async def test_attempt_routes_require_authentication(method, path):
    async with client(app_with(), token="invalid") as http:
        response = await http.request(method, BASE + path, json={"registration_id": 1, "expected_version": 1})
    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/v1/workspaces/0/exams/12/attempts/current",
        "/v1/workspaces/7/exams/0/attempts/current",
        f"/v1/workspaces/7/exams/12/attempts/{2**31}/events",
        "/v1/workspaces/7/exams/12/attempts/31/events?limit=101",
        "/v1/workspaces/7/exams/12/attempts/31/events?offset=-1",
    ],
)
async def test_attempt_paths_and_pagination_are_validated(path):
    async with client(app_with()) as http:
        response = await http.get(path)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"registration_id": True, "expected_version": 1},
        {"registration_id": 1, "expected_version": 0},
        {"registration_id": 1, "expected_version": 1, "status": "finished"},
        {"registration_id": 1},
    ],
)
async def test_start_body_is_strict(body):
    async with client(app_with()) as http:
        response = await http.post(BASE, json=body)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "path,body",
    [
        ("/31/questions", {}),
        ("/31/questions", {"expected_version": "2"}),
        ("/31/pause", {"expected_version": 1, "reason": "a\x00b"}),
        ("/31/resume", {"expected_version": 1, "actor_id": 4}),
        ("/31/finish", {"expected_version": 1, "server_now": "2026-11-30T07:00:00Z"}),
    ],
)
async def test_command_body_is_strict(path, body):
    async with client(app_with()) as http:
        response = await http.post(BASE + path, json=body)
    assert response.status_code == 422


async def test_start_reports_created_and_existing():
    service = SimpleNamespace(
        start=AsyncMock(side_effect=[(attempt_read(), True), (attempt_read(), False)]),
        current=AsyncMock(),
    )
    async with client(app_with(service)) as http:
        created = await http.post(BASE, json={"registration_id": 91, "expected_version": 1})
        existing = await http.post(BASE, json={"registration_id": 91, "expected_version": 1})
    assert created.status_code == 201 and created.json()["id"] == 31
    assert existing.status_code == 200


async def test_current_returns_attempt_or_null():
    service = SimpleNamespace(current=AsyncMock(return_value=CurrentAttemptRead(attempt=None)))
    async with client(app_with(service)) as http:
        response = await http.get(BASE + "/current")
    assert response.status_code == 200
    assert response.json() == {"attempt": None}


async def test_finish_returns_window():
    window = attempt_read(status="finished", finished_at=NOW, remaining_seconds=0)
    window = AttemptRead.model_validate(
        {
            **window.model_dump(),
            "assessment_window": {
                "opened_at": NOW,
                "closes_at": NOW,
                "settings_version": 1,
                "project_type_id": 8,
            },
        }
    )
    service = SimpleNamespace(finish=AsyncMock(return_value=window))
    async with client(app_with(service)) as http:
        response = await http.post(BASE + "/31/finish", json={"expected_version": 1})
    assert response.status_code == 200
    assert response.json()["assessment_window"]["settings_version"] == 1
