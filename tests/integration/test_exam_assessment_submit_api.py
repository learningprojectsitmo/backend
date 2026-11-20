from __future__ import annotations

import httpx
import pytest
import test_exam_assessment_db as assessment_db_cases
from fastapi import Depends, FastAPI
from test_exam_assessment_submit_db import AFTER_WINDOW, assessment_service

from src.api.v1.routes import routers
from src.core.container import get_exam_assessment_service, get_uow
from src.core.dependencies import get_current_user

pytestmark = pytest.mark.integration

seeded = assessment_db_cases.seeded
_finished_attempt = assessment_db_cases._finished_attempt


async def _client(s, actor_name, *, now=assessment_db_cases.NOW):
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"][actor_name]

    async def frozen_service(uow=Depends(test_uow)):
        return assessment_service(uow, now)

    app.dependency_overrides[get_exam_assessment_service] = frozen_service
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _base(s, attempt):
    return f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"


async def test_submit_flow_over_http(seeded):
    s = seeded
    attempt = await _finished_attempt(s)
    async with await _client(s, "local_teacher") as client:
        base = _base(s, attempt)
        form = (await client.get(base)).json()
        assert form["submission"] is None
        qid = form["questions"][0]["id"]
        await client.put(f"{base}/draft", json={"answers": [{"question_id": qid, "score": 4, "comment": "ok"}]})

        resp = await client.post(f"{base}/submit")
        assert resp.status_code == 200
        body = resp.json()
        assert (body["version"], body["total"], body["unchanged"]) == (1, 4, False)
        assert body["answers"] == [{"question_id": qid, "score": 4, "comment": "ok"}]

        assert (await client.post(f"{base}/submit", json={})).json()["unchanged"] is True

        await client.put(f"{base}/draft", json={"answers": [{"question_id": qid, "score": 5, "comment": "ok"}]})
        state = (await client.get(base)).json()["submission"]
        assert (state["version"], state["has_unsubmitted_changes"]) == (1, True)
        assert (await client.post(f"{base}/submit")).json()["version"] == 2


@pytest.mark.parametrize("extra", [{"role": "teacher"}, {"weight": 100}, {"answers": []}, {"total": 25}])
async def test_submit_body_does_not_accept_role_weight_or_scores(seeded, extra):
    s = seeded
    attempt = await _finished_attempt(s)
    async with await _client(s, "member") as client:
        assert (await client.post(f"{_base(s, attempt)}/submit", json=extra)).status_code == 422


async def test_submit_error_codes(seeded):
    s = seeded
    attempt = await _finished_attempt(s)
    base = _base(s, attempt)
    async with await _client(s, "manager") as client:
        assert (await client.post(f"{base}/submit")).status_code == 403  # excluded
    async with await _client(s, "local_teacher") as client:
        resp = await client.post(f"{base}/submit")  # nothing saved yet
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "incomplete_sheet"
        wrong = f"/v1/workspaces/{s['foreign_workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"
        assert (await client.post(f"{wrong}/submit")).status_code == 404
    async with await _client(s, "local_teacher", now=AFTER_WINDOW) as client:
        resp = await client.post(f"{base}/submit")
        assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "assessment_window_closed")
        resp = await client.put(f"{base}/draft", json={"answers": []})
        assert (resp.status_code, resp.json()["detail"]["code"]) == (409, "assessment_window_closed")
