from __future__ import annotations

import json
from importlib.resources import files
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_auth_service
from src.core.exceptions import AuthError


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(routers)

    async def authenticate(token):
        if token != "valid-test-token":
            raise AuthError("Invalid token")
        return SimpleNamespace(id=7, email="teacher@example.com")

    auth = SimpleNamespace(get_current_user=AsyncMock(side_effect=authenticate))
    app.dependency_overrides[get_auth_service] = lambda: auth
    return app


@pytest.fixture
def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def headers():
    return {"Authorization": "Bearer valid-test-token"}


@pytest.mark.asyncio
async def test_list_catalog_with_all_explanations(client):
    async with client:
        response = await client.get("/v1/assessment/rubrics", headers=headers())
    assert response.status_code == 200
    rubrics = response.json()
    assert [r["assessment_kind"] for r in rubrics] == ["product", "technical_integration", "research"]
    original = json.loads(files("src.data.assessment").joinpath("rubrics.v1.json").read_text(encoding="utf-8"))
    assert len(rubrics) == 3
    for rubric, source in zip(rubrics, original, strict=True):
        assert rubric["version"] == 1
        assert rubric["max_raw_score"] == 25
        assert rubric["name"] == source["name"]
        assert len(rubric["criteria"]) == 5
        for criterion, expected in zip(rubric["criteria"], source["criteria"], strict=True):
            assert (criterion["code"], criterion["name"], criterion["description"]) == (
                expected["id"],
                expected["name"],
                expected["description"],
            )
            assert criterion["levels"] == [
                {"score": i, "description": expected["levels"][str(i)]} for i in [1, 2, 3, 4, 5]
            ]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["product", "technical_integration", "research"])
async def test_detail_matches_list_and_survives_response_mutation(client, kind):
    path = f"/v1/assessment/rubrics/{kind}/versions/1"
    async with client:
        listed = (await client.get("/v1/assessment/rubrics", headers=headers())).json()
        response = await client.get(path, headers=headers())
        assert response.status_code == 200
        detail = response.json()
        assert detail == next(r for r in listed if r["assessment_kind"] == kind)
        detail["criteria"][0]["levels"][0]["description"] = "changed by client"
        fresh = await client.get(path, headers=headers())
    assert fresh.json()["criteria"][0]["levels"][0]["description"] != "changed by client"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/assessment/rubrics", "/v1/assessment/rubrics/research/versions/1"])
@pytest.mark.parametrize("auth", [None, "Bearer invalid-token"])
async def test_catalog_requires_authentication(client, path, auth):
    async with client:
        response = await client.get(path, headers={"Authorization": auth} if auth else {})
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "status"),
    [
        ("other/versions/1", 404),
        ("research/versions/2", 404),
        ("product/versions/0", 422),
        ("product/versions/-1", 422),
        ("product/versions/abc", 422),
    ],
)
async def test_detail_errors(client, suffix, status):
    async with client:
        response = await client.get(f"/v1/assessment/rubrics/{suffix}", headers=headers())
    assert response.status_code == status


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/v1/assessment/rubrics", "/v1/assessment/rubrics/product/versions/1"])
async def test_catalog_has_no_public_write_api(client, method, path):
    async with client:
        response = await client.request(method, path, headers=headers(), json={})
    assert response.status_code == 405
