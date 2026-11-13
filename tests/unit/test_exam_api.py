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
        yield SimpleNamespace(
            session=SimpleNamespace(
                get=AsyncMock(side_effect=AssertionError("Unexpected DB")),
                execute=AsyncMock(side_effect=AssertionError("Unexpected DB")),
            )
        )

    app.dependency_overrides[get_uow] = no_database
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer valid"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", ""),
        ("POST", ""),
        ("GET", "/1"),
        ("PUT", "/1/settings"),
        ("POST", "/1/publish"),
        ("GET", "/1/settings"),
        ("GET", "/1/settings/1"),
    ],
)
async def test_all_routes_require_authentication(client, method, path):
    async with client:
        response = await client.request(
            method, "/v1/workspaces/1/exams" + path, headers={"Authorization": "Bearer invalid"}
        )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/v1/workspaces/0/exams",
        "/v1/workspaces/1/exams/-1",
        "/v1/workspaces/1/exams?limit=101",
        "/v1/workspaces/1/exams?offset=-1",
        "/v1/workspaces/1/exams?status=running",
        "/v1/workspaces/1/exams/1/settings/0",
    ],
)
async def test_invalid_ids_and_queries(client, path):
    async with client:
        response = await client.get(path)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_client_status(client):
    async with client:
        response = await client.post(
            "/v1/workspaces/1/exams", json={"title": "Exam", "starts_at": "2026-11-30T10:00:00Z", "status": "published"}
        )
    assert response.status_code == 422
