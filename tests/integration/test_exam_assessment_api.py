from __future__ import annotations

import httpx
import pytest
import test_exam_assessment_db as assessment_db_cases
from fastapi import FastAPI

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user

pytestmark = pytest.mark.integration

seeded = assessment_db_cases.seeded

_finished_attempt = assessment_db_cases._finished_attempt


async def _client(s, actor_name):
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    actor = {"user": s["users"][actor_name]}
    app.dependency_overrides[get_current_user] = lambda: actor["user"]
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return client, actor


async def test_get_form_returns_200_for_admitted_teacher(seeded):
    s = seeded
    attempt = await _finished_attempt(s)
    client, _actor = await _client(s, "local_teacher")
    async with client:
        resp = await client.get(
            f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["attempt_id"] == attempt.id
    assert body["assessor"]["role"] == "teacher"
    assert body["assessor"]["weight"] == 60
    assert body["assessor"]["excluded"] is False
    assert len(body["questions"]) >= 1
    assert body["window"]["closes_at"] > body["window"]["opened_at"]


async def test_get_form_excluded_manager_returns_403(seeded):
    s = seeded
    attempt = await _finished_attempt(s, project="manager")
    client, _actor = await _client(s, "manager")
    async with client:
        resp = await client.get(
            f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"
        )
    assert resp.status_code == 403


async def test_get_form_wrong_workspace_returns_404(seeded):
    s = seeded
    attempt = await _finished_attempt(s)
    client, _actor = await _client(s, "local_teacher")
    async with client:
        resp = await client.get(f"/v1/workspaces/999999/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment")
    assert resp.status_code == 404


async def test_get_form_restores_draft_after_save(seeded):
    s = seeded
    attempt = await _finished_attempt(s)
    client, _actor = await _client(s, "local_teacher")
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"
    async with client:
        form = await client.get(base)
        assert form.status_code == 200
        qid = form.json()["questions"][0]["id"]
        saved = await client.put(f"{base}/draft", json={"answers": [{"question_id": qid, "score": 4, "comment": "ok"}]})
        assert saved.status_code == 200
        reloaded = await client.get(base)
        assert reloaded.status_code == 200
        answers = reloaded.json()["draft"]["answers"]
        assert any(a["question_id"] == qid and a["score"] == 4 for a in answers)


async def test_put_draft_null_score_clears_answer(seeded):
    s = seeded
    attempt = await _finished_attempt(s)
    client, _actor = await _client(s, "local_teacher")
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"
    async with client:
        form = await client.get(base)
        qid = form.json()["questions"][0]["id"]
        await client.put(f"{base}/draft", json={"answers": [{"question_id": qid, "score": 4, "comment": None}]})
        await client.put(f"{base}/draft", json={"answers": [{"question_id": qid, "score": None, "comment": None}]})
        reloaded = await client.get(base)
        answers = reloaded.json()["draft"]["answers"]
        assert any(a["question_id"] == qid and a["score"] is None for a in answers)


async def test_put_draft_validation_score_0_returns_422(seeded):
    s = seeded
    attempt = await _finished_attempt(s)
    client, _actor = await _client(s, "local_teacher")
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"
    async with client:
        resp = await client.put(f"{base}/draft", json={"answers": [{"question_id": 1, "score": 0}]})
    assert resp.status_code == 422


async def test_put_draft_validation_score_6_returns_422(seeded):
    s = seeded
    attempt = await _finished_attempt(s)
    client, _actor = await _client(s, "local_teacher")
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"
    async with client:
        resp = await client.put(f"{base}/draft", json={"answers": [{"question_id": 1, "score": 6}]})
    assert resp.status_code == 422


async def test_put_draft_unknown_question_id_ignored(seeded):
    s = seeded
    attempt = await _finished_attempt(s)
    client, _actor = await _client(s, "local_teacher")
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"
    async with client:
        await client.get(base)
        resp = await client.put(f"{base}/draft", json={"answers": [{"question_id": 999999, "score": 3}]})
        assert resp.status_code == 200
        assert resp.json()["answers"] == []


async def test_put_draft_excluded_returns_403(seeded):
    s = seeded
    attempt = await _finished_attempt(s, project="manager")
    client, _actor = await _client(s, "manager")
    base = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"
    async with client:
        resp = await client.put(f"{base}/draft", json={"answers": []})
    assert resp.status_code == 403
