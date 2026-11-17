from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_auth_service, get_exam_result_service, get_uow
from src.core.exceptions import AuthError, BusinessLogicError, ValidationError
from src.schema.exam_result import ResultEditionListRead, ResultRead

BASE = "/v1/workspaces/7/exams/12/attempts/31/result"


def make_client(service=None):
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
        yield SimpleNamespace(session=SimpleNamespace())

    app.dependency_overrides[get_uow] = no_database
    if service is not None:
        app.dependency_overrides[get_exam_result_service] = lambda: service
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer valid"}
    )


@pytest.mark.parametrize(
    "method,path",
    [("GET", ""), ("GET", "/editions"), ("POST", "/accept"), ("POST", "/manual"), ("POST", "/publish")],
)
async def test_routes_require_authentication(method, path):
    async with make_client() as client:
        response = await client.request(method, BASE + path, headers={"Authorization": "Bearer invalid"}, json={})
    assert response.status_code == 401


async def test_get_returns_service_payload():
    payload = ResultRead(workspace_id=7, exam_id=12, attempt_id=31, edition=None, preliminary=None, outdated=False)
    service = SimpleNamespace(get=AsyncMock(return_value=payload))
    async with make_client(service) as client:
        response = await client.get(BASE)
    assert response.status_code == 200 and response.json()["outdated"] is False
    service.get.assert_awaited_once()


async def test_editions_endpoint():
    service = SimpleNamespace(editions=AsyncMock(return_value=ResultEditionListRead(items=[])))
    async with make_client(service) as client:
        response = await client.get(BASE + "/editions")
    assert response.json() == {"items": []}


@pytest.mark.parametrize(
    "path,body",
    [
        ("/accept", {}),
        ("/accept", {"expected_version": 1}),
        ("/accept", {"expected_version": "0"}),
        ("/accept", {"expected_version": 0, "final_score": "25"}),
        ("/manual", {}),
        ("/manual", {"expected_version": 0, "final_score": "20"}),
        ("/manual", {"expected_version": 0, "final_score": "20", "reason": "  "}),
        ("/manual", {"expected_version": 0, "final_score": "20.123", "reason": "r"}),
        ("/manual", {"expected_version": 0, "final_score": -1, "reason": "r"}),
        ("/manual", {"expected_version": 0, "final_score": True, "reason": "r"}),
        ("/manual", {"expected_version": 0, "final_score": "20", "reason": "r", "kind": "manual"}),
        ("/manual", {"expected_version": 0, "final_score": "20", "reason": "r", "calculated_score": "1"}),
        ("/publish", {"expected_version": 0}),
        ("/publish", {}),
    ],
)
async def test_invalid_body_is_422(path, body):
    service = SimpleNamespace(accept=AsyncMock(), manual=AsyncMock(), publish=AsyncMock())
    async with make_client(service) as client:
        response = await client.post(BASE + path, json=body)
    assert response.status_code == 422
    service.accept.assert_not_awaited()
    service.manual.assert_not_awaited()
    service.publish.assert_not_awaited()


async def test_conflict_is_409_with_code():
    error = BusinessLogicError({"code": "no_calculation", "message": "no calculation"})
    service = SimpleNamespace(accept=AsyncMock(side_effect=error))
    async with make_client(service) as client:
        response = await client.post(BASE + "/accept", json={"expected_version": 0})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_calculation"


async def test_out_of_range_path_is_422():
    async with make_client(SimpleNamespace()) as client:
        response = await client.get("/v1/workspaces/7/exams/12/attempts/0/result")
    assert response.status_code == 422


async def test_manual_endpoint_passes_parsed_body_to_service():
    payload = ResultRead(workspace_id=7, exam_id=12, attempt_id=31, edition=None, preliminary=None, outdated=False)
    service = SimpleNamespace(manual=AsyncMock(return_value=payload))
    async with make_client(service) as client:
        response = await client.post(
            BASE + "/manual", json={"expected_version": 0, "final_score": 12.5, "reason": " why "}
        )
    assert response.status_code == 200
    data = service.manual.await_args.args[3]
    assert (str(data.final_score), data.reason, data.expected_version) == ("12.50", "why", 0)


async def test_manual_out_of_range_is_422_with_code():
    error = ValidationError({"code": "final_score_out_of_range", "message": "range"})
    service = SimpleNamespace(manual=AsyncMock(side_effect=error))
    async with make_client(service) as client:
        response = await client.post(BASE + "/manual", json={"expected_version": 0, "final_score": 99, "reason": "r"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "final_score_out_of_range"
