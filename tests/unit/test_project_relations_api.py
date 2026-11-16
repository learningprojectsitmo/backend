"""Tests for the project relations HTTP endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_auth_service, get_project_relations_service
from src.core.exceptions import AuthError, NotFoundError
from src.services.project_relations import ProjectRelations

MANAGER_ID = 7
TEACHER_ID = 99
MEMBER_ID = 100
PROJECT_ID = 42
WORKSPACE_ID = 5


def _relations(**overrides) -> ProjectRelations:
    base = {
        "project_id": PROJECT_ID,
        "workspace_id": WORKSPACE_ID,
        "manager_id": MANAGER_ID,
        "member_ids": [MEMBER_ID],
        "workspace_teacher_ids": [TEACHER_ID],
    }
    base.update(overrides)
    return ProjectRelations(**base)


class StubService:
    def __init__(self) -> None:
        self.used_workspace_id = None

    async def get_manager_id(self, project_id, *, workspace_id):
        self.used_workspace_id = workspace_id
        if workspace_id != WORKSPACE_ID or project_id != PROJECT_ID:
            raise NotFoundError("Project not found in this workspace")
        return MANAGER_ID

    async def is_workspace_teacher(self, user_id, *, workspace_id):
        return user_id == TEACHER_ID and workspace_id == WORKSPACE_ID

    async def get_project_relations(self, project_id, *, workspace_id):
        return _relations(manager_id=MANAGER_ID, workspace_id=workspace_id, project_id=project_id)


@pytest.fixture
def make_client():
    def _make(user_id: int, role: str):
        app = FastAPI()
        app.include_router(routers)

        async def authenticate(token):
            if token != "valid":
                raise AuthError("Invalid token")
            return SimpleNamespace(
                id=user_id,
                email=f"{role}@example.test",
                role=SimpleNamespace(name=role),
            )

        app.dependency_overrides[get_auth_service] = lambda: SimpleNamespace(
            get_current_user=AsyncMock(side_effect=authenticate)
        )

        stub = StubService()
        app.dependency_overrides[get_project_relations_service] = lambda: stub

        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer valid"},
        ), stub

    return _make


def _url(workspace_id: int = WORKSPACE_ID, project_id: int = PROJECT_ID) -> str:
    return f"/v1/workspaces/{workspace_id}/projects/{project_id}/relations"


@pytest.mark.asyncio
async def test_requires_authentication(make_client):
    app = FastAPI()
    app.include_router(routers)

    def authenticate(_token):
        raise AuthError("Invalid token")

    app.dependency_overrides[get_auth_service] = lambda: SimpleNamespace(
        get_current_user=AsyncMock(side_effect=authenticate)
    )

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer invalid"},
    )
    async with client:
        response = await client.get(_url())
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_manager_can_access(make_client):
    client, _stub = make_client(MANAGER_ID, "manager")
    async with client:
        response = await client.get(_url())
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == PROJECT_ID
    assert body["manager_id"] == MANAGER_ID
    assert body["member_ids"] == [MEMBER_ID]
    assert body["workspace_teacher_ids"] == [TEACHER_ID]
    assert body["contract_version"] == 1


@pytest.mark.asyncio
async def test_teacher_can_access(make_client):
    client, _stub = make_client(TEACHER_ID, "teacher")
    async with client:
        response = await client.get(_url())
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_member_gets_403(make_client):
    client, _stub = make_client(MEMBER_ID, "member")
    async with client:
        response = await client.get(_url())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_foreign_user_gets_403(make_client):
    client, _stub = make_client(200, "member")
    async with client:
        response = await client.get(_url())
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_wrong_workspace_returns_404(make_client):
    client, _stub = make_client(TEACHER_ID, "teacher")
    async with client:
        response = await client.get(_url(workspace_id=999))
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        _url(workspace_id=0),
        _url(project_id=0),
        _url(project_id=-1),
    ],
)
async def test_invalid_ids_return_422(make_client, path):
    client, _stub = make_client(TEACHER_ID, "teacher")
    async with client:
        response = await client.get(path)
    assert response.status_code == 422
