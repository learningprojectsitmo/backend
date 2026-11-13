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
from src.schema.exam_attempt import AttemptRead
from src.schema.exam_queue import QueueItemRead, QueueMutationRead, QueueRead

NOW = datetime(2026, 11, 30, 7, 0, tzinfo=UTC)
BASE = "/v1/workspaces/7/exams/12/queue"
ATTEMPTS = "/v1/workspaces/7/exams/12/attempts"


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
        "postponed_at": None,
        "postponed_phase": None,
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


def queue_item(**overrides) -> QueueItemRead:
    data = {
        "registration_id": 91,
        "project_id": 42,
        "project_type_id": 8,
        "slot_id": None,
        "planned_start_at": None,
        "planned_end_at": None,
        "position": 1,
        "state": "waiting",
        "registration_version": 2,
        "started_at": None,
        "attempt": None,
    }
    data.update(overrides)
    return QueueItemRead.model_validate(data)


def mutation(**overrides) -> QueueMutationRead:
    data = {"item": queue_item(), "queue_revision": 4, "server_now": NOW}
    data.update(overrides)
    return QueueMutationRead.model_validate(data)


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
        ("/91/next", {"expected_version": 1, "position": 2}),
        ("/91/postpone", {"expected_version": 1}),
        ("/91/postpone", {"expected_version": 1, "reason": "  "}),
        ("/91/postpone", {"expected_version": 1, "reason": "a\x00b"}),
        ("/91/no-show", {"expected_version": 1, "reason": "x" * 1001}),
    ],
)
async def test_queue_body_and_path_are_strict(path, body):
    async with client(app_with()) as http:
        response = await http.post(BASE + path, json=body)
    assert response.status_code == 422


async def test_queue_read_returns_snapshot():
    snapshot = QueueRead(queue_revision=4, server_now=NOW, items=[queue_item()])
    service = SimpleNamespace(read=AsyncMock(return_value=snapshot))
    async with client(app_with(queue_service=service)) as http:
        response = await http.get(BASE)
    assert response.status_code == 200
    assert response.json()["queue_revision"] == 4
    assert response.json()["items"][0]["state"] == "waiting"


async def test_place_and_next_delegate_to_service():
    service = SimpleNamespace(
        place=AsyncMock(return_value=mutation()),
        next=AsyncMock(return_value=mutation(item=queue_item(position=1, registration_version=3))),
    )
    async with client(app_with(queue_service=service)) as http:
        placed = await http.post(BASE + "/91/place", json={"expected_version": 2, "position": None})
        nxt = await http.post(BASE + "/91/next", json={"expected_version": 2})
    assert placed.status_code == 200
    assert placed.json()["item"]["position"] == 1
    assert nxt.status_code == 200
    service.place.assert_awaited_once()
    service.next.assert_awaited_once()


async def test_postpone_and_no_show_return_mutation():
    service = SimpleNamespace(
        postpone=AsyncMock(return_value=mutation(item=queue_item(state="postponed", position=None))),
        no_show=AsyncMock(return_value=mutation(item=queue_item(state="no_show", position=None))),
    )
    async with client(app_with(queue_service=service)) as http:
        postponed = await http.post(BASE + "/91/postpone", json={"expected_version": 2, "reason": "Проектор"})
        no_show = await http.post(BASE + "/91/no-show", json={"expected_version": 3, "reason": "Не пришла"})
    assert postponed.json()["item"]["state"] == "postponed"
    assert no_show.json()["item"]["state"] == "no_show"


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


async def test_attempt_postpone_and_restart_routes():
    service = SimpleNamespace(
        postpone=AsyncMock(return_value=attempt_read(status="postponed", postponed_at=NOW, postponed_phase="speaking")),
        restart=AsyncMock(return_value=attempt_read(status="speaking", version=4)),
    )
    async with client(app_with(attempt_service=service)) as http:
        postponed = await http.post(ATTEMPTS + "/31/postpone", json={"expected_version": 3, "reason": "Проектор"})
        restarted = await http.post(ATTEMPTS + "/31/restart", json={"expected_version": 4})
    assert postponed.status_code == 200
    assert postponed.json()["postponed_phase"] == "speaking"
    assert restarted.status_code == 200
    assert restarted.json()["status"] == "speaking"


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
