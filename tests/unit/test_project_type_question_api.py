from __future__ import annotations

import json
from importlib.resources import files
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_auth_service, get_uow
from src.core.exceptions import AuthError
from tests.unit.test_question_schema import payload


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routers)

    async def authenticate(token):
        if token != "valid":
            raise AuthError("Invalid test token")
        return SimpleNamespace(id=7, email="teacher@example.test", role=SimpleNamespace(name="teacher"))

    app.dependency_overrides[get_auth_service] = lambda: SimpleNamespace(
        get_current_user=AsyncMock(side_effect=authenticate)
    )

    async def no_database():
        session = SimpleNamespace(
            get=AsyncMock(side_effect=AssertionError("Unexpected DB I/O in validation-only test")),
            execute=AsyncMock(side_effect=AssertionError("Unexpected DB I/O in validation-only test")),
        )
        yield SimpleNamespace(session=session)

    app.dependency_overrides[get_uow] = no_database
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer valid"}
    )


@pytest.mark.asyncio
async def test_templates_http_exposes_all_original_explanations(client):
    async with client:
        response = await client.get("/v1/assessment/question-templates")
    assert response.status_code == 200
    templates = response.json()
    assert [t["code"] for t in templates] == ["product", "technical_integration", "research"]
    source = json.loads(files("src.data.assessment").joinpath("question_templates.json").read_text(encoding="utf-8"))
    for actual, original in zip(templates, source, strict=True):
        assert "version" not in actual
        assert len(actual["questions"]) == 5
        for q, c in zip(actual["questions"], original["criteria"], strict=True):
            assert (q["code"], q["text"], q["description"]) == (c["id"], c["name"], c["description"])
            assert q["levels"] == [{"score": n, "description": c["levels"][str(n)]} for n in range(1, 6)]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_templates_are_read_only(client, method):
    async with client:
        response = await client.request(method, "/v1/assessment/question-templates", json={})
    assert response.status_code == 405


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/assessment/question-templates", "/v1/workspaces/1/project-types/1/questions"])
@pytest.mark.parametrize("token", ["", "Bearer invalid"])
async def test_question_routes_require_authentication(client, path, token):
    async with client:
        response = await client.get(path, headers={"Authorization": token})
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/v1/workspaces/0/project-types/1/questions",
        "/v1/workspaces/1/project-types/-1/questions",
        "/v1/workspaces/no/project-types/1/questions",
    ],
)
async def test_invalid_path_id_is_422(client, path):
    async with client:
        response = await client.get(path)
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect", ["missing_level", "bool_score", "duplicate_score", "blank_explanation", "foreign_key", "duplicate_id"]
)
async def test_invalid_custom_scale_is_422(client, defect):
    data = payload()
    if defect == "missing_level":
        data["levels"].pop()
    elif defect == "bool_score":
        data["levels"][0]["score"] = True
    elif defect == "duplicate_score":
        data["levels"][0]["score"] = 4
    elif defect == "blank_explanation":
        data["levels"][0]["description"] = " "
    elif defect == "foreign_key":
        data["project_type_id"] = 999
    else:
        data["id"] = 17
    questions = [data, data] if defect == "duplicate_id" else [data]
    async with client:
        response = await client.put("/v1/workspaces/1/project-types/1/questions", json={"questions": questions})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_template_code_is_422(client):
    async with client:
        response = await client.post(
            "/v1/workspaces/1/project-types/1/questions/apply-template", json={"template_code": "unknown"}
        )
    assert response.status_code == 422
