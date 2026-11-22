from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
import test_exam_demo_api as demo
from sqlalchemy import text
from test_exam_csv_http import download, parse
from test_exam_demo_api import begin, body, finish, register

from src.model.workspace import WorkSpaceParticipation

pytestmark = pytest.mark.integration
api = demo.api
seeded_base = demo.seeded


@pytest_asyncio.fixture(loop_scope="function")
async def seeded(seeded_base):
    s = seeded_base
    teacher = s["users"]["teacher"]
    async with s["uow"]() as u:
        u.session.add(
            WorkSpaceParticipation(workspace_id=s["workspace"], participant_id=teacher.id, role_id=teacher.role_id)
        )
    return s


def criteria(count, scale):
    return [
        {
            "text": f"Criterion {i}",
            "levels": [{"score": score, "description": f"Level {score}"} for score in range(1, scale + 1)],
        }
        for i in range(count)
    ]


async def hand_in(client, attempt_path, score):
    form = body(await client.get(attempt_path + "/assessment"))
    payload = {"answers": [{"question_id": q["id"], "score": score} for q in form["questions"]]}
    saved = body(await client.put(attempt_path + "/assessment/draft", json=payload))
    assert saved["answers"] == [{**answer, "comment": None} for answer in payload["answers"]]
    return body(await client.post(attempt_path + "/assessment/submit", json={})), form


async def test_three_point_type_through_form_revisions_result_and_csv(api, seeded):
    client, base, now = api
    type_id = seeded["types"][0]
    path = f"{base}/{seeded['draft']}"
    questions_path = f"/v1/workspaces/{seeded['workspace']}/project-types/{type_id}/questions"
    old = body(await client.get(questions_path))
    assert old["max_score"] == 5
    three = criteria(7, 3)
    three[0]["id"] = old["questions"][0]["id"]
    invalid = await client.put(questions_path, json={"max_score": 3, "questions": three[:1] + criteria(1, 5)})
    assert invalid.status_code == 422
    saved = body(await client.put(questions_path, json={"max_score": 3, "questions": three}))
    assert saved == body(await client.get(questions_path)) and saved["max_score"] == 3
    assert saved["questions"][0]["id"] == old["questions"][0]["id"]
    assert len(saved["questions"]) == 7
    assert all([r["score"] for r in q["levels"]] == [1, 2, 3] for q in saved["questions"])
    assert body(await client.put(questions_path, json={"questions": three}))["max_score"] == 3
    body(await client.post(path + "/publish", json={"expected_version": 1}))

    attempt = await finish(client, path, await begin(client, path, await register(client, path, seeded)))
    attempt_path = f"{path}/attempts/{attempt['id']}"
    first, form = await hand_in(client, attempt_path, 3)
    assert first["version"] == 1 and first["total"] == 21
    assert all([level["score"] for level in q["levels"]] == [1, 2, 3] for q in form["questions"])
    invalid = await client.put(
        attempt_path + "/assessment/draft", json={"answers": [{"question_id": form["questions"][0]["id"], "score": 4}]}
    )
    assert body(invalid, 422)["detail"]["code"] == "score_out_of_scale"
    unchanged = body(await client.post(attempt_path + "/assessment/submit", json={}))
    assert unchanged["version"] == 1 and unchanged["unchanged"]
    second, _ = await hand_in(client, attempt_path, 2)
    assert second["version"] == 2 and second["total"] == 14
    locked = await client.put(questions_path, json={"max_score": 5, "questions": criteria(1, 5)})
    assert body(locked, 409)["detail"]["code"] == "questions_locked"

    now[0] += timedelta(minutes=5)
    (_, preliminary), (_, participation) = parse(await download(seeded, path=path + "/exports/csv"))
    assert preliminary[0]["sheet_max"] == "21" and preliminary[0]["calculated_score"] == "16.67"
    teacher_row = next(row for row in participation if row["response_status"] == "submitted")
    assert (teacher_row["total"], teacher_row["criterion_7_score"], teacher_row["submission_version"]) == (
        "14",
        "2",
        "2",
    )

    accepted = body(await client.post(attempt_path + "/result/accept", json={"expected_version": 0}))["edition"]
    assert accepted["snapshot"]["sheet_max"] == 21 and accepted["snapshot"]["max_score"] == "25.00"
    assert accepted["final_score"] == "16.67"
    published = body(await client.post(attempt_path + "/result/publish", json={"expected_version": 1}))["edition"]
    assert published["published_at"] is not None
    (_, results), _ = parse(await download(seeded, path=path + "/exports/csv"))
    assert (results[0]["sheet_max"], results[0]["final_score"], results[0]["decision_state"]) == (
        "21",
        "16.67",
        "published",
    )
    async with seeded["engine"].connect() as db:
        totals = (
            (await db.execute(text("SELECT total FROM exam_assessment_submission ORDER BY version"))).scalars().all()
        )
        assert totals == [21, 14]


async def test_migration_and_archiving_preserve_legacy_five_point_history(api, seeded, run_migrations):
    client, base, now = api
    path = f"{base}/{seeded['exams'][0]}"
    attempt = await finish(client, path, await begin(client, path, await register(client, path, seeded)))
    attempt_path = f"{path}/attempts/{attempt['id']}"
    submission, _ = await hand_in(client, attempt_path, 5)
    assert submission["total"] == 5
    now[0] += timedelta(minutes=5)
    accepted = body(await client.post(attempt_path + "/result/accept", json={"expected_version": 0}))["edition"]
    assert accepted["snapshot"]["sheet_max"] == 5 and accepted["final_score"] == "25.00"

    await seeded["engine"].dispose()
    run_migrations(seeded["url"], "downgrade", "d117a11b20a1")
    run_migrations(seeded["url"], "upgrade", "head")
    run_migrations(seeded["url"], "check")
    assert (await client.delete(path, params={"x_test_actor": "admin"})).status_code == 204
    assert body(await client.get(attempt_path + "/result"))["edition"] == accepted
    form = body(await client.get(attempt_path + "/assessment"))
    assert [r["score"] for r in form["questions"][0]["levels"]] == [1, 2, 3, 4, 5]
    assert form["submission"]["version"] == 1 and form["draft"]["answers"][0]["score"] == 5
    (_, results), (_, participation) = parse(await download(seeded, path=path + "/exports/csv"))
    assert results[0]["sheet_max"] == "5" and results[0]["final_score"] == "25.00"
    assert next(row for row in participation if row["response_status"] == "submitted")["criterion_1_score"] == "5"
