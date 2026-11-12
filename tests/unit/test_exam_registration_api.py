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
