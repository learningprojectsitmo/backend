# ruff: noqa: ARG002  (fake signatures mirror the real collaborators)
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_auth_service, get_exam_result_service, get_uow
from src.core.exceptions import AuthError, NotFoundError, PermissionError
from src.repository.exam_result_repository import ExamResultRegistryCurrent, ExamResultRegistryRow, escape_like
from src.schema.exam_result import ResultRegistryRead
from src.services.exam_result_service import ExamResultService

NOW = datetime(2026, 11, 30, 7, 0, tzinfo=UTC)
USER = SimpleNamespace(id=5)
WS, EXAM = 7, 12
BASE = f"/v1/workspaces/{WS}/exams/{EXAM}/results"


def current(**overrides):
    values = {
        "version": 2,
        "kind": "manual",
        "calculated_score": Decimal("19.00"),
        "final_score": Decimal("20.50"),
        "max_score": Decimal("25.00"),
        "reason": "Устная защита",
        "decided_by_id": 5,
        "decided_by_first_name": "Анна",
        "decided_by_last_name": "Петрова",
        "decided_at": NOW,
        "published_at": None,
        "published_by_id": None,
    }
    values.update(overrides)
    return ExamResultRegistryCurrent(**values)


def row(attempt_id=1, *, cur=None, **overrides):
    values = {
        "attempt_id": attempt_id,
        "registration_id": attempt_id + 100,
        "project_id": 9,
        "project_name": "Проект",
        "project_type_id": 3,
        "finished_at": NOW,
        "editions_count": 0 if cur is None else cur.version,
        "current": cur,
        "previous_final_score": None,
        "settings_outdated": False,
    }
    values.update(overrides)
    return ExamResultRegistryRow(**values)


class Fakes:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.visibility_error: Exception | None = None
        self.is_teacher = True
        self.calls = []

    async def require_read_access(self, workspace_id, exam_id, user):
        if self.visibility_error is not None:
            raise self.visibility_error

    async def is_workspace_teacher(self, user_id, *, workspace_id):
        return self.is_teacher

    async def list_results(self, workspace_id, exam_id, *, q, state, limit, offset):
        self.calls.append({"workspace_id": workspace_id, "exam_id": exam_id, "q": q, "state": state, "limit": limit})
        return self.rows[offset : offset + limit + 1]


def make(fakes: Fakes):
    repository = SimpleNamespace(list_results=fakes.list_results)
    return ExamResultService(repository, None, None, fakes, None, fakes)


async def registry(service, *, q=None, state=None, limit=50, offset=0, user=USER):
    return await service.registry(WS, EXAM, user, q=q, state=state, limit=limit, offset=offset)


async def test_teacher_gets_rows_with_state_and_flat_current():
    fakes = Fakes(
        [
            row(1),
            row(2, cur=current(), previous_final_score=Decimal("19.00")),
            row(3, cur=current(published_at=NOW, published_by_id=5)),
        ]
    )
    page = await registry(make(fakes))
    assert [item.state for item in page.items] == ["undecided", "accepted", "published"]
    assert page.items[0].current is None
    second = page.items[1]
    assert second.current.decided_by_name == "Анна Петрова" and second.previous_final_score == Decimal("19.00")
    assert page.items[2].current.published_by_id == 5
    assert (page.limit, page.offset, page.has_more) == (50, 0, False)


@pytest.mark.parametrize(
    "first,last,expected",
    [("Анна", "Петрова", "Анна Петрова"), ("Анна", None, "Анна"), ("Анна", "", "Анна"), ("Анна", "  ", "Анна")],
)
async def test_author_name_has_no_dangling_spaces(first, last, expected):
    fakes = Fakes([row(1, cur=current(decided_by_first_name=first, decided_by_last_name=last))])
    page = await registry(make(fakes))
    assert page.items[0].current.decided_by_name == expected


async def test_has_more_uses_the_extra_row():
    fakes = Fakes([row(i) for i in range(1, 4)])
    service = make(fakes)
    first = await registry(service, limit=2)
    assert [i.attempt_id for i in first.items] == [1, 2] and first.has_more is True
    last = await registry(service, limit=2, offset=2)
    assert [i.attempt_id for i in last.items] == [3] and last.has_more is False
    exact = await registry(service, limit=3)
    assert len(exact.items) == 3 and exact.has_more is False
    assert fakes.calls[0]["limit"] == 2  # the repository adds the +1 itself


async def test_filters_are_passed_and_blank_search_is_dropped():
    fakes = Fakes()
    service = make(fakes)
    await registry(service, q="  алго  ", state="accepted")
    await registry(service, q="   ")
    assert (fakes.calls[0]["q"], fakes.calls[0]["state"]) == ("алго", "accepted")
    assert fakes.calls[1]["q"] is None
    assert fakes.calls[0]["workspace_id"] == WS and fakes.calls[0]["exam_id"] == EXAM


async def test_user_without_teacher_role_is_forbidden_and_repository_is_not_called():
    fakes = Fakes([row(1)])
    fakes.is_teacher = False  # member / manager / global admin outside the workspace
    with pytest.raises(PermissionError):
        await registry(make(fakes))
    assert fakes.calls == []


@pytest.mark.parametrize("error", [NotFoundError("Exam not found")])
async def test_hidden_exam_is_404_before_the_role_check(error):
    fakes = Fakes()
    fakes.visibility_error = error
    fakes.is_teacher = False
    with pytest.raises(NotFoundError):
        await registry(make(fakes))


def test_row_state_is_derived_from_current_edition():
    assert row(1).state == "undecided"
    assert row(1, cur=current()).state == "accepted"
    assert row(1, cur=current(published_at=NOW, published_by_id=5)).state == "published"


def test_escape_like_neutralises_wildcards():
    assert escape_like("100%_a\\b") == "100\\%\\_a\\\\b"
    assert escape_like("plain") == "plain"


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


async def test_endpoint_requires_authentication():
    async with make_client() as client:
        response = await client.get(BASE, headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


async def test_endpoint_defaults_and_payload():
    page = ResultRegistryRead(items=[], limit=50, offset=0, has_more=False)
    service = SimpleNamespace(registry=AsyncMock(return_value=page))
    async with make_client(service) as client:
        response = await client.get(BASE)
    assert response.status_code == 200
    assert response.json() == {"items": [], "limit": 50, "offset": 0, "has_more": False}
    kwargs = service.registry.await_args.kwargs
    assert kwargs == {"q": None, "state": None, "limit": 50, "offset": 0}


async def test_endpoint_passes_query_and_serializes_decimals_as_strings():
    item_row = row(1, cur=current(), previous_final_score=Decimal("19.00"))
    page = ResultRegistryRead(items=[ExamResultService._registry_item(item_row)], limit=10, offset=5, has_more=True)
    service = SimpleNamespace(registry=AsyncMock(return_value=page))
    async with make_client(service) as client:
        response = await client.get(BASE, params={"q": "a%b", "state": "published", "limit": 10, "offset": 5})
    body = response.json()
    assert response.status_code == 200 and body["has_more"] is True
    assert body["items"][0]["current"]["final_score"] == "20.50"
    assert body["items"][0]["previous_final_score"] == "19.00"
    assert service.registry.await_args.kwargs == {"q": "a%b", "state": "published", "limit": 10, "offset": 5}


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": "x"},
        {"offset": -1},
        {"state": "done"},
        {"state": "ACCEPTED"},
        {"q": "x" * 201},
    ],
)
async def test_invalid_query_is_422(params):
    service = SimpleNamespace(registry=AsyncMock())
    async with make_client(service) as client:
        response = await client.get(BASE, params=params)
    assert response.status_code == 422
    service.registry.assert_not_awaited()


@pytest.mark.parametrize("params", [{"limit": 1}, {"limit": 100}, {"offset": 0}, {"state": "undecided"}])
async def test_boundary_query_is_accepted(params):
    page = ResultRegistryRead(items=[], limit=50, offset=0, has_more=False)
    service = SimpleNamespace(registry=AsyncMock(return_value=page))
    async with make_client(service) as client:
        response = await client.get(BASE, params=params)
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/v1/workspaces/0/exams/1/results", "/v1/workspaces/1/exams/0/results"])
async def test_path_ids_are_validated(path):
    async with make_client(SimpleNamespace(registry=AsyncMock())) as client:
        assert (await client.get(path)).status_code == 422


async def test_extra_fields_are_forbidden_in_response_schema():
    with pytest.raises(ValueError):
        ResultRegistryRead(items=[], limit=1, offset=0, has_more=False, total=0)
