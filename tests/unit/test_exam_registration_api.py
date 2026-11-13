from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_auth_service, get_uow
from src.core.exceptions import AuthError


@pytest.fixture
def client():
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
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer valid"}
    )


@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_slots_require_authentication(client, method):
    async with client:
        response = await client.request(
            method, "/v1/workspaces/1/exams/1/slots", headers={"Authorization": "Bearer invalid"}
        )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/v1/workspaces/0/exams/1/slots",
        "/v1/workspaces/1/exams/0/slots",
        "/v1/workspaces/1/exams/1/slots?limit=101",
        "/v1/workspaces/1/exams/1/slots?offset=-1",
    ],
)
async def test_slot_paths_and_pagination_are_validated(client, path):
    async with client:
        response = await client.get(path)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/registrations/self"),
        ("POST", "/registrations/self"),
        ("POST", "/registrations/1/self-cancel"),
        ("POST", "/registrations/1/self-move"),
        ("GET", "/registrations/1/history"),
    ],
)
async def test_self_registration_routes_require_authentication(client, method, path):
    async with client:
        response = await client.request(
            method, "/v1/workspaces/1/exams/1" + path, headers={"Authorization": "Bearer invalid"}
        )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "body", [{"project_id": True}, {"project_id": 1, "source": "organizer"}, {"project_id": 1, "actor_id": 1}]
)
async def test_registration_http_rejects_spoofed_identity_and_boolean_id(client, body):
    async with client:
        response = await client.post("/v1/workspaces/1/exams/1/registrations/self", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        f"/v1/workspaces/{2**65}/exams/1/slots",
        f"/v1/workspaces/1/exams/1/slots?offset={2**65}",
        f"/v1/workspaces/1/exams/1/registrations/{2**65}/history",
    ],
)
async def test_http_rejects_database_integer_overflow(client, path):
    async with client:
        response = await client.get(path)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/registrations"),
        ("POST", "/registrations"),
        ("POST", "/registrations/1/cancel"),
        ("POST", "/registrations/1/move"),
    ],
)
async def test_organizer_registration_routes_require_authentication(client, method, path):
    async with client:
        response = await client.request(
            method, "/v1/workspaces/1/exams/1" + path, headers={"Authorization": "Bearer invalid"}
        )
    assert response.status_code == 401
