from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import (
    get_auth_service,
    get_project_relations_service,
    get_uow,
)
from src.core.exceptions import AuthError, NotFoundError, PermissionError
from src.services.project_relations import ProjectRelations

MANAGER_ID = 7
TEACHER_ID = 99
MEMBER_ID = 100
PROJECT_ID = 42
WORKSPACE_ID = 5


def _relations(**overrides) -> ProjectRelations:
    base = dict(
        project_id=PROJECT_ID,
        workspace_id=WORKSPACE_ID,
        manager_id=MANAGER_ID,
        member_ids=[MEMBER_ID],
        workspace_teacher_ids=[TEACHER_ID],
    )
    base.update(overrides)
    return ProjectRelations(**base)


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

        # Override the relations service with a stub that records calls.
        records = {}

        class StubService:
            async def get_manager_id(self, project_id, *, workspace_id):
                records["workspace_id"] = workspace_id
                if workspace_id != WORKSPACE_ID or project_id != PROJECT_ID:
                    raise NotFoundError("Project not found in this workspace")
                return MANAGER_ID

            async def is_workspace_teacher(self, user_id, *, workspace_id):
                return user_id == TEACHER_ID and workspace_id == WORKSPACE_ID

            async def get_project_relations(self, project_id, *, workspace_id):
                return _relations(manager_id=MANAGER_ID)

        app.dependency_overrides[get_project_relations_service] = lambda: StubService()

        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer valid"},
        ), records

    return _make


@pytest.mark.asyncio
async def test_requires_authentication(make_client):
    app = FastAPI()
    app.include_router(routers)

    async def authenticate(token):
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
        response = await client.get(
            f"/v1/workspaces/{WORKSPACE_ID}/projects/{PROJECT_ID}/relations"
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_manager_can_access(make_client):
    client, records = make_client(MANAGER_ID, "manager")
    async with client:
        response = await client.get(
            f"/v1/workspaces/{WORKSPACE_ID}/projects/{PROJECT_ID}/relations"
        )
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == PROJECT_ID
    assert body["manager_id"] == MANAGER_ID
    assert body["member_ids"] == [MEMBER_ID]
    assert body["workspace_teacher_ids"] == [TEACHER_ID]
    assert body["contract_version"] == 1


@pytest.mark.asyncio
async def test_teacher_can_access(make_client):
    client, records = make_client(TEACHER_ID, "teacher")
    async with client:
        response = await client.get(
            f"/v1/workspaces/{WORKSPACE_ID}/projects/{PROJECT_ID}/relations"
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_member_gets_403(make_client):
    client, records = make_client(MEMBER_ID, "member")
    async with client:
        response = await client.get(
            f"/v1/workspaces/{WORKSPACE_ID}/projects/{PROJECT_ID}/relations"
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_foreign_user_gets_403(make_client):
    client, records = make_client(200, "member")
    async with client:
        response = await client.get(
            f"/v1/workspaces/{WORKSPACE_ID}/projects/{PROJECT_ID}/relations"
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_wrong_workspace_returns_404(make_client):
    client, records = make_client(TEACHER_ID, "teacher")
    async with client:
        response = await client.get(
            f"/v1/workspaces/999/projects/{PROJECT_ID}/relations"
        )
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        f"/v1/workspaces/0/projects/{PROJECT_ID}/relations",
        "/v1/workspaces/5/projects/0/relations",
        "/v1/workspaces/5/projects/-1/relations",
    ],
)
async def test_invalid_ids_return_422(make_client, path):
    client, records = make_client(TEACHER_ID, "teacher")
    async with client:
        response = await client.get(path)
    assert response.status_code == 422