from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
import test_exam_results_db as results_cases
from fastapi import FastAPI
from sqlalchemy import event, text
from test_exam_assessment_submit_db import OPEN, draft, submit
from test_exam_attempts_db import NOW, finish, organized, start
from test_exam_results_db import AFTER_WINDOW, finished_attempt, set_participation

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user
from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.project import ProjectParticipation
from src.model.user import User
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_participation_repository import ExamParticipationRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_repository import ProjectRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.repository.workspace_repository import WorkSpaceRepository
from src.services.exam_participation_service import ExamParticipationService
from src.services.exam_service import ExamService
from src.services.project_relations import ProjectRelationsService

pytestmark = pytest.mark.integration

seeded_base = results_cases.seeded_base
seeded = results_cases.seeded
LAST_SECOND = AFTER_WINDOW - timedelta(seconds=1)


def participation_service(uow, now=OPEN):
    return ExamParticipationService(
        ExamParticipationRepository(uow),
        ExamAttemptRepository(uow),
        ExamService(ExamRepository(uow), ProjectTypeQuestionRepository(uow)),
        ProjectRelationsService(ProjectRepository(uow), WorkSpaceRepository(uow)),
        clock=lambda: now,
    )


async def participation(s, attempt, *, actor="teacher", now=OPEN, workspace=None, exam=0, attempt_id=None):
    async with s["uow"]() as u:
        return await participation_service(u, now).get(
            workspace or s["workspace"], s["exams"][exam], attempt_id or attempt.id, s["users"][actor]
        )


async def team_attempt(s, *, team_member="demoted"):
    """Finished attempt whose defending team also has a plain member (excluded as member_of_defending_team)."""
    registration = await organized(s, project="manager")
    attempt, _ = await start(s, registration)
    async with s["uow"]() as u:
        u.session.add(
            ProjectParticipation(project_id=s["projects"]["manager"], participant_id=s["users"][team_member].id)
        )
    await finish(s, attempt, now=NOW + timedelta(minutes=10))
    return attempt


def by_name(result):
    return {item.name: item for item in result.items}


async def test_mixed_audience_statuses_reasons_and_submissions(seeded):
    s = seeded
    attempt = await team_attempt(s)
    await draft(s, attempt, "local_teacher", 4, comment="first")
    await submit(s, attempt, "local_teacher")
    await draft(s, attempt, "local_teacher", 5, comment="second")
    await submit(s, attempt, "local_teacher")
    await draft(s, attempt, "manager2", 3, comment="secret draft")  # draft only: not a vote
    result = await participation(s, attempt)

    assert result.state == "open"
    assert (result.window.settings_version, result.window.opened_at < result.window.closes_at) == (1, True)
    items = by_name(result)
    teacher = items["local_teacher"]
    assert teacher.status == "submitted" and teacher.role == "teacher" and teacher.exclusion_reason is None
    assert (teacher.submission.version, teacher.submission.total) == (2, 5)
    assert [(a.score, a.comment) for a in teacher.submission.answers] == [(5, "second")]
    assert items["member"].status == "not_submitted" and items["member"].submission is None
    draft_only = items["manager2"]
    assert draft_only.status == "not_submitted" and draft_only.submission is None
    assert "secret draft" not in result.model_dump_json()
    assert items["manager"].status == "excluded" and items["manager"].exclusion_reason == "manager_of_defending_team"
    assert items["demoted"].status == "excluded" and items["demoted"].exclusion_reason == "member_of_defending_team"
    assert items["manager"].submission is None
    # Teachers are never excluded, even the author of the exam workspace.
    assert items["teacher"].status == "not_submitted"
    summary = result.summary
    assert summary.total.excluded == 2 and summary.total.submitted == 1
    assert summary.total.admitted == summary.total.submitted + summary.total.not_submitted
    assert summary.teacher.submitted == 1 and summary.manager.excluded == 1 and summary.member.excluded == 1


async def test_window_states_open_closed_and_not_offered(seeded):
    s = seeded
    registration = await organized(s)
    running, _ = await start(s, registration)
    not_offered = await participation(s, running)
    assert (not_offered.state, not_offered.window, not_offered.items) == ("not_offered", None, [])
    assert not_offered.summary.total.admitted == 0

    await finish(s, running, now=NOW + timedelta(minutes=10))
    assert (await participation(s, running, now=LAST_SECOND)).state == "open"
    assert (await participation(s, running, now=AFTER_WINDOW)).state == "closed"


async def test_submissions_stay_visible_after_the_window_closes(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "member", 2, comment="late")
    await submit(s, attempt, "member")
    closed = await participation(s, attempt, now=AFTER_WINDOW)
    assert closed.state == "closed"
    member = by_name(closed)["member"]
    assert (member.status, member.submission.total) == ("submitted", 2)


async def test_order_is_role_then_name_then_id_and_stable(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    result = await participation(s, attempt)
    roles = [item.role for item in result.items]
    assert roles == sorted(roles, key={"teacher": 0, "manager": 1, "member": 2}.get)
    for role in ("teacher", "manager", "member"):
        keys = [(i.name, i.user_id) for i in result.items if i.role == role]
        assert keys == sorted(keys)
    assert result == await participation(s, attempt)


async def test_role_is_taken_from_the_snapshot(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await set_participation(s, "member", local="teacher")
    await set_participation(s, "local_teacher", local="member")
    async with s["uow"]() as u:
        await u.session.execute(
            text('UPDATE "user" SET first_name = :n WHERE id = :u'), {"n": "Renamed", "u": s["users"]["member"].id}
        )
    items = by_name(await participation(s, attempt))
    assert items["Renamed"].role == "member"
    assert items["local_teacher"].role == "teacher"


async def test_late_workspace_member_is_not_added_retroactively(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    before = await participation(s, attempt)
    await set_participation(s, "outsider", local="teacher")
    after = await participation(s, attempt)
    assert [i.user_id for i in after.items] == [i.user_id for i in before.items]
    assert s["users"]["outsider"].id not in {i.user_id for i in after.items}


@pytest.mark.parametrize("actor", ["manager", "member", "local_manager", "demoted"])
async def test_non_teachers_of_the_workspace_are_forbidden(seeded, actor):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(PermissionError):
        await participation(s, attempt, actor=actor)


async def test_global_admin_outside_the_workspace_has_no_access(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(PermissionError):
        await participation(s, attempt, actor="admin")


async def test_local_teacher_and_admin_can_read(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    for actor in ("local_teacher", "local_admin"):
        assert (await participation(s, attempt, actor=actor)).state == "open"


async def test_outsider_and_foreign_ids_are_not_found(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(NotFoundError):
        await participation(s, attempt, actor="outsider")
    with pytest.raises(NotFoundError):
        await participation(s, attempt, workspace=s["foreign_workspace"])
    with pytest.raises(NotFoundError):
        await participation(s, attempt, exam=1)  # attempt of another exam
    with pytest.raises(NotFoundError):
        await participation(s, attempt, attempt_id=999999)


async def test_old_window_without_snapshot_conflicts(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    async with s["uow"]() as u:
        await u.session.execute(text("DELETE FROM assessment_window_audience"))
    with pytest.raises(BusinessLogicError) as error:
        await participation(s, attempt)
    assert error.value.detail["code"] == "audience_snapshot_unavailable"


async def test_other_attempts_sheets_do_not_leak(seeded):
    s = seeded
    first = await finished_attempt(s, project="manager")
    await draft(s, first, "member", 4)
    await submit(s, first, "member")

    second_registration = await organized(s, project="local_manager")
    second, _ = await start(s, second_registration, now=AFTER_WINDOW)
    await finish(s, second, now=AFTER_WINDOW + timedelta(minutes=10))
    items = by_name(await participation(s, second, now=AFTER_WINDOW + timedelta(minutes=11)))
    assert items["member"].status == "not_submitted" and items["member"].submission is None
    assert by_name(await participation(s, first))["member"].status == "submitted"


async def test_statement_count_does_not_grow_with_the_audience(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4)
    await submit(s, attempt, "local_teacher")
    statements: list[str] = []

    def record(_connection, _cursor, statement, *_args):
        statements.append(statement)

    async def measure():
        statements.clear()
        async with s["uow"]() as u:
            data = await ExamParticipationRepository(u).list_participation(
                workspace_id=s["workspace"], exam_id=s["exams"][0], attempt_id=attempt.id
            )
        return len(data.rows), len(statements)

    sync_engine = s["engine"].sync_engine
    event.listen(sync_engine, "before_cursor_execute", record)
    try:
        small_rows, small_count = await measure()
        async with s["uow"]() as u:
            window_id = await u.session.scalar(
                text("SELECT id FROM assessment_window WHERE attempt_id = :a"), {"a": attempt.id}
            )
            role_id = await u.session.scalar(text("SELECT id FROM role WHERE name = 'member'"))
            extra = [
                User(
                    first_name=f"Extra {i}",
                    middle_name="T",
                    email=f"extra{i}@example.com",
                    password_hashed="x",
                    role_id=role_id,
                )
                for i in range(30)
            ]
            u.session.add_all(extra)
            await u.session.flush()
            for user in extra:
                await u.session.execute(
                    text(
                        "INSERT INTO assessment_window_audience (window_id, workspace_id, user_id, role, own_project_ids, "
                        "admitted, created_at) VALUES (:w, :ws, :u, 'member', '[]', TRUE, now())"
                    ),
                    {"w": window_id, "ws": s["workspace"], "u": user.id},
                )
        large_rows, large_count = await measure()
    finally:
        event.remove(sync_engine, "before_cursor_execute", record)
    assert large_rows == small_rows + 30
    assert small_count == large_count <= 3


async def test_http_route_is_wired_with_real_services(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    actor = {"name": "teacher"}
    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"][actor["name"]]
    url = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/participation"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(url)
        body = response.json()
        assert response.status_code == 200 and body["attempt_id"] == attempt.id
        assert {i["status"] for i in body["items"]} == {"excluded", "not_submitted"}
        actor["name"] = "member"
        assert (await client.get(url)).status_code == 403
        actor["name"] = "teacher"
        assert (await client.get(url.replace(f"/attempts/{attempt.id}", "/attempts/999999"))).status_code == 404
