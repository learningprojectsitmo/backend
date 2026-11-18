# ruff: noqa: ARG002  (fake signatures mirror the real collaborators)
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_auth_service, get_exam_participation_service, get_uow
from src.core.exceptions import AuthError, BusinessLogicError, NotFoundError, PermissionError
from src.repository.exam_participation_repository import (
    ExamParticipation,
    ParticipationAnswer,
    ParticipationRow,
    ParticipationSubmission,
    ParticipationWindow,
)
from src.schema.exam_participation import ParticipationRead
from src.services.exam_participation_service import ExamParticipationService

NOW = datetime(2026, 11, 30, 7, 0, tzinfo=UTC)
OPENED = NOW - timedelta(minutes=1)
CLOSES = NOW + timedelta(minutes=2)
WS, EXAM, ATTEMPT = 7, 12, 31
USER = SimpleNamespace(id=5)
BASE = f"/v1/workspaces/{WS}/exams/{EXAM}/attempts/{ATTEMPT}/participation"


def row(user_id, first, last, role, *, admitted=True, reason=None, submission=None):
    return ParticipationRow(user_id, first, last, role, admitted, reason, submission)


def sub(version=1, total=4, comment="ok"):
    return ParticipationSubmission(version, NOW, total, (ParticipationAnswer(1, total, comment),))


class Fakes:
    def __init__(self, rows=(), window=True):
        self.visibility_error: Exception | None = None
        self.is_teacher = True
        self.attempt = SimpleNamespace(id=ATTEMPT)
        self.data = ExamParticipation(ParticipationWindow(1, OPENED, CLOSES, 3), tuple(rows)) if window else None
        self.calls = 0
        self.now = NOW

    async def require_read_access(self, workspace_id, exam_id, user):
        if self.visibility_error is not None:
            raise self.visibility_error

    async def is_workspace_teacher(self, user_id, *, workspace_id):
        return self.is_teacher

    async def get(self, workspace_id, exam_id, attempt_id):
        return self.attempt if (workspace_id, exam_id, attempt_id) == (WS, EXAM, ATTEMPT) else None

    async def list_participation(self, *, workspace_id, exam_id, attempt_id):
        self.calls += 1
        return self.data

    def service(self):
        return ExamParticipationService(self, self, self, self, clock=lambda: self.now)


MIXED = [
    row(1, "Ann", "Teacher", "teacher", submission=sub(2, 5)),
    row(2, "Bob", None, "manager", admitted=False, reason="manager_of_defending_team"),
    row(3, "Cid", "Member", "member"),
    row(4, "Dan", "Member", "member", admitted=False, reason="member_of_defending_team"),
    row(5, "Eve", "Teacher", "teacher"),
]


async def get(fakes):
    return await fakes.service().get(WS, EXAM, ATTEMPT, USER)


async def test_statuses_reasons_and_submission_are_mapped():
    result = await get(Fakes(MIXED))
    by_id = {item.user_id: item for item in result.items}
    assert by_id[1].status == "submitted" and by_id[1].submission.version == 2 and by_id[1].submission.total == 5
    assert by_id[1].submission.answers[0].comment == "ok"
    assert by_id[2].status == "excluded" and by_id[2].exclusion_reason == "own_project_manager"
    assert by_id[4].status == "excluded" and by_id[4].exclusion_reason == "own_project_member"
    assert by_id[3].status == by_id[5].status == "not_submitted"
    assert by_id[3].exclusion_reason is None and by_id[3].submission is None
    assert result.window.settings_version == 3


async def test_name_has_no_dangling_spaces():
    result = await get(
        Fakes([row(1, "Ann", "Lee", "teacher"), row(2, "Bob", None, "manager"), row(3, "Cid", "", "member")])
    )
    assert [item.name for item in result.items] == ["Ann Lee", "Bob", "Cid"]


async def test_summary_counts_by_role_and_total():
    summary = (await get(Fakes(MIXED))).summary
    assert summary.total.model_dump() == {"admitted": 3, "submitted": 1, "not_submitted": 2, "excluded": 2}
    assert summary.teacher.model_dump() == {"admitted": 2, "submitted": 1, "not_submitted": 1, "excluded": 0}
    assert summary.manager.model_dump() == {"admitted": 0, "submitted": 0, "not_submitted": 0, "excluded": 1}
    assert summary.member.model_dump() == {"admitted": 1, "submitted": 0, "not_submitted": 1, "excluded": 1}


async def test_window_state_follows_the_server_clock():
    fakes = Fakes(MIXED)
    assert (await get(fakes)).state == "open"
    fakes.now = CLOSES - timedelta(seconds=1)
    assert (await get(fakes)).state == "open"
    fakes.now = CLOSES
    assert (await get(fakes)).state == "closed"


async def test_window_never_opened_is_not_offered():
    result = await get(Fakes(window=False))
    assert result.state == "not_offered" and result.window is None and result.items == []
    assert result.summary.total.model_dump() == {"admitted": 0, "submitted": 0, "not_submitted": 0, "excluded": 0}


async def test_window_without_snapshot_conflicts():
    with pytest.raises(BusinessLogicError) as error:
        await get(Fakes([]))
    assert error.value.detail["code"] == "audience_snapshot_unavailable"


async def test_not_a_teacher_is_forbidden_and_repository_is_not_called():
    fakes = Fakes(MIXED)
    fakes.is_teacher = False
    with pytest.raises(PermissionError):
        await get(fakes)
    assert fakes.calls == 0


async def test_hidden_exam_is_not_found_before_the_role_check():
    fakes = Fakes(MIXED)
    fakes.is_teacher = False
    fakes.visibility_error = NotFoundError("Exam not found")
    with pytest.raises(NotFoundError):
        await get(fakes)
    assert fakes.calls == 0


async def test_unknown_attempt_is_not_found():
    with pytest.raises(NotFoundError):
        await Fakes(MIXED).service().get(WS, EXAM, 999, USER)


async def test_draft_state_is_not_exposed_in_the_row():
    # A draft is never loaded by the repository; an admitted assessor without submission is "not submitted".
    item = (await get(Fakes([row(3, "Cid", None, "member")]))).items[0]
    assert item.status == "not_submitted" and item.submission is None


def make_client(service=None, role="teacher"):
    app = FastAPI()
    app.include_router(routers)

    async def authenticate(token):
        if token != "valid":
            raise AuthError("Invalid token")
        return SimpleNamespace(id=7, email="t@example.test", role=SimpleNamespace(name=role))

    app.dependency_overrides[get_auth_service] = lambda: SimpleNamespace(
        get_current_user=AsyncMock(side_effect=authenticate)
    )

    async def no_database():
        yield SimpleNamespace(session=SimpleNamespace())

    app.dependency_overrides[get_uow] = no_database
    if service is not None:
        app.dependency_overrides[get_exam_participation_service] = lambda: service
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer valid"}
    )


async def test_api_requires_authentication():
    async with make_client() as client:
        response = await client.get(BASE, headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


async def test_api_returns_service_payload():
    payload = await get(Fakes(MIXED))
    service = SimpleNamespace(get=AsyncMock(return_value=payload))
    async with make_client(service) as client:
        response = await client.get(BASE)
    assert response.status_code == 200
    body = response.json()
    assert ParticipationRead.model_validate(body) == payload
    assert body["state"] == "open" and [i["user_id"] for i in body["items"]] == [1, 2, 3, 4, 5]
    service.get.assert_awaited_once()


@pytest.mark.parametrize(
    "error,status",
    [
        (PermissionError("no"), 403),
        (NotFoundError("no"), 404),
        (BusinessLogicError({"code": "audience_snapshot_unavailable", "message": "m"}), 409),
    ],
)
async def test_api_maps_errors(error, status):
    service = SimpleNamespace(get=AsyncMock(side_effect=error))
    async with make_client(service) as client:
        response = await client.get(BASE)
    assert response.status_code == status


@pytest.mark.parametrize(
    "path", ["/v1/workspaces/0/exams/1/attempts/1/participation", "/v1/workspaces/1/exams/1/attempts/0/participation"]
)
async def test_api_out_of_range_path_is_422(path):
    async with make_client(SimpleNamespace()) as client:
        response = await client.get(path)
    assert response.status_code == 422


async def test_api_is_read_only():
    async with make_client(SimpleNamespace()) as client:
        response = await client.post(BASE, json={})
    assert response.status_code == 405
