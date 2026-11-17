from __future__ import annotations

import asyncio

import pytest
import test_exam_assessment_api as api_cases
import test_exam_assessment_db as sheet_cases
import test_exam_attempts_db as attempt_cases
from sqlalchemy import text

from src.repository.exam_assessment_repository import ExamAssessmentRepository
from src.schema.exam import ExamWeights

pytestmark = pytest.mark.integration
seeded = sheet_cases.seeded


def _url(s, attempt):
    return f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment"


async def test_form_and_draft_keep_captured_role_after_role_change(seeded):
    s = seeded
    attempt = await sheet_cases._finished_attempt(s)
    async with s["engine"].begin() as conn:
        await conn.execute(
            text(
                "UPDATE workspace_participation SET role_id=(SELECT id FROM role WHERE name='member') "
                "WHERE workspace_id=:wid AND participant_id=:uid"
            ),
            {"wid": s["workspace"], "uid": s["users"]["local_teacher"].id},
        )
    client, _ = await api_cases._client(s, "local_teacher")
    async with client:
        form = await client.get(_url(s, attempt))
        assert form.status_code == 200
        assert (form.json()["assessor"]["role"], form.json()["assessor"]["weight"]) == ("teacher", 60)
        qid = form.json()["questions"][0]["id"]
        draft = await client.put(_url(s, attempt) + "/draft", json={"answers": [{"question_id": qid, "score": 4}]})
        assert draft.status_code == 200
        assert draft.json()["updated_at"] > form.json()["draft"]["updated_at"]


async def test_excluded_manager_cannot_gain_access_after_author_change(seeded):
    s = seeded
    attempt = await sheet_cases._finished_attempt(s)
    async with s["engine"].begin() as conn:
        await conn.execute(
            text("UPDATE project SET author_id=:author WHERE id=:pid"),
            {"author": s["users"]["manager2"].id, "pid": s["projects"]["manager"]},
        )
    client, _ = await api_cases._client(s, "manager")
    async with client:
        assert (await client.get(_url(s, attempt))).status_code == 403
        assert (await client.put(_url(s, attempt) + "/draft", json={"answers": []})).status_code == 403


async def test_teacher_added_after_finish_is_not_in_audience(seeded):
    s = seeded
    attempt = await sheet_cases._finished_attempt(s)
    async with s["engine"].begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO workspace_participation(workspace_id,participant_id,role_id) "
                "VALUES (:wid,:uid,(SELECT id FROM role WHERE name='teacher'))"
            ),
            {"wid": s["workspace"], "uid": s["users"]["outsider"].id},
        )
    client, _ = await api_cases._client(s, "outsider")
    async with client:
        assert (await client.get(_url(s, attempt))).status_code == 403


async def test_legacy_window_does_not_fabricate_audience(seeded):
    s = seeded
    attempt = await sheet_cases._finished_attempt(s)
    async with s["engine"].begin() as conn:
        await conn.execute(text("DELETE FROM assessment_window_audience"))
    client, _ = await api_cases._client(s, "local_teacher")
    async with client:
        response = await client.get(_url(s, attempt))
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "audience_snapshot_unavailable"
        assert (await client.put(_url(s, attempt) + "/draft", json={"answers": []})).status_code == 409
    async with s["engine"].connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM exam_assessment_sheet"))).scalar_one() == 0


async def test_form_uses_window_settings_instead_of_start_revision(seeded):
    s = seeded
    registration = await attempt_cases.organized(s)
    attempt, _ = await attempt_cases.start(s, registration)
    await attempt_cases.set_settings(s, weights=ExamWeights(teacher=50, manager=35, member=15))
    finished = await attempt_cases.finish(s, attempt)
    assert finished.settings_version == 1
    assert finished.assessment_window.settings_version == 2
    client, _ = await api_cases._client(s, "local_teacher")
    async with client:
        response = await client.get(_url(s, attempt))
    assert response.status_code == 200
    assert response.json()["window"]["settings_version"] == 2
    assert response.json()["assessor"]["weight"] == 50


async def test_concurrent_sheet_creation_preserves_outer_transactions(seeded):
    s = seeded
    attempt = await sheet_cases._finished_attempt(s)
    barrier = asyncio.Barrier(2)

    async def create(project):
        async with s["uow"]() as u:
            repo = ExamAssessmentRepository(u)
            original = repo.get_sheet
            first = True

            async def synchronized(*args):
                nonlocal first
                result = await original(*args)
                if first:
                    first = False
                    await barrier.wait()
                return result

            repo.get_sheet = synchronized
            await u.session.execute(
                text("UPDATE project SET description='preserved' WHERE id=:id"), {"id": s["projects"][project]}
            )
            sheet = await repo.get_or_create_sheet(
                s["workspace"], s["exams"][0], attempt.id, s["users"]["local_teacher"].id
            )
            return sheet.id

    ids = await asyncio.wait_for(asyncio.gather(create("manager"), create("manager2")), 10)
    assert ids[0] == ids[1]
    async with s["engine"].connect() as conn:
        rows = (
            (
                await conn.execute(
                    text("SELECT description FROM project WHERE id IN (:a,:b)"),
                    {"a": s["projects"]["manager"], "b": s["projects"]["manager2"]},
                )
            )
            .scalars()
            .all()
        )
    assert rows == ["preserved", "preserved"]


@pytest.mark.parametrize("duplicate", [False, True])
async def test_repeated_identical_draft_preserves_all_timestamps(seeded, duplicate):
    s = seeded
    attempt = await sheet_cases._finished_attempt(s)
    client, _ = await api_cases._client(s, "local_teacher")
    async with client:
        form = await client.get(_url(s, attempt))
        qid = form.json()["questions"][0]["id"]
        payload = {"answers": [{"question_id": qid, "score": 3, "comment": "same"}]}
        if duplicate:
            payload["answers"].insert(0, {"question_id": qid, "score": 2})
        first = await client.put(_url(s, attempt) + "/draft", json=payload)
        async with s["engine"].connect() as conn:
            answer_time = (await conn.execute(text("SELECT updated_at FROM exam_assessment_answer"))).scalar_one()
        second = await client.put(_url(s, attempt) + "/draft", json=payload)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        async with s["engine"].connect() as conn:
            assert (
                await conn.execute(text("SELECT updated_at FROM exam_assessment_answer"))
            ).scalar_one() == answer_time


async def test_reverse_order_concurrent_saves_do_not_deadlock(seeded):
    s = seeded
    async with s["engine"].begin() as conn:
        second = (
            await conn.execute(
                text(
                    "INSERT INTO project_type_question(project_type_id,text,position) VALUES (:tid,'Second',1) RETURNING id"
                ),
                {"tid": s["types"][0]},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO project_type_question_level(question_id,score,description) "
                "SELECT :qid,n,'Level ' || n FROM generate_series(1,5) AS n"
            ),
            {"qid": second},
        )
    attempt = await sheet_cases._finished_attempt(s)
    async with s["uow"]() as u:
        repo = ExamAssessmentRepository(u)
        sheet = await repo.get_or_create_sheet(
            s["workspace"], s["exams"][0], attempt.id, s["users"]["local_teacher"].id
        )
        first = (await u.session.execute(text("SELECT id FROM project_type_question WHERE position=0"))).scalar_one()
        await repo.upsert_answers(sheet.id, [(first, 1, None), (second, 1, None)])
        sid = sheet.id

    async def save(order, score):
        async with s["uow"]() as u:
            execute = u.session.execute

            async def yield_after_answer_write(statement, *args, **kwargs):
                result = await execute(statement, *args, **kwargs)
                if getattr(getattr(statement, "table", None), "name", None) == "exam_assessment_answer":
                    await asyncio.sleep(0.02)
                return result

            u.session.execute = yield_after_answer_write
            await ExamAssessmentRepository(u).upsert_answers(sid, [(qid, score, None) for qid in order])

    await asyncio.wait_for(asyncio.gather(save([first, second], 3), save([second, first], 4)), 10)
    async with s["uow"]() as u:
        answers = await ExamAssessmentRepository(u).get_answers(sid)
        assert len(answers) == 2
        assert {answer.score for answer in answers.values()} in ({3}, {4})
