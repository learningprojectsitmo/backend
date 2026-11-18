"""End-to-end acceptance checks AC-01..AC-03 and AC-06..AC-08 on the real chain (#105, #117).

exam -> attempt finished -> window + audience snapshot -> form/draft -> submit -> accept / manual.
The test names carry `ac0N` for traceability; the matrix lives in docs/exam-acceptance.md.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
import test_exam_assessment_submit_db as submit_cases
import test_exam_results_db as results_cases
from fastapi import FastAPI
from sqlalchemy import text
from test_exam_attempts_db import NOW, finish, organized, set_settings, set_window_minutes, start
from test_exam_participation_db import by_name, participation
from test_exam_results_db import AFTER_WINDOW, code_of
from test_exam_results_db import count as count_rows

from src.api.v1.routes import routers
from src.core.container import get_uow
from src.core.dependencies import get_current_user
from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import ProjectParticipation
from src.repository.exam_assessment_repository import ExamAssessmentRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam import ExamWeights
from src.schema.exam_assessment import AnswerDraftWrite, AssessmentDraftWrite
from src.schema.exam_result import ResultAccept, ResultManual
from src.services.exam_sheet_source import SubmittedSheetSource
from src.services.project_type_question_service import ProjectTypeQuestionService
from src.services.question_template_service import QuestionTemplateService

pytestmark = pytest.mark.integration

seeded_base = results_cases.seeded_base
seeded = results_cases.seeded
OPEN = submit_cases.OPEN
LAST_SECOND = AFTER_WINDOW - timedelta(seconds=1)
TEMPLATES = ["product", "technical_integration", "research"]


async def apply_template(s, code="product"):
    async with s["uow"]() as u:
        read = await ProjectTypeQuestionService(
            ProjectTypeQuestionRepository(u), QuestionTemplateService()
        ).apply_template(s["workspace"], s["types"][0], code, s["users"]["teacher"])
    assert len(read.questions) == 5 and all(len(q.levels) == 5 for q in read.questions)


@pytest_asyncio.fixture(loop_scope="function")
async def five(seeded):
    """Seeded exam whose project type carries a catalog set (5 criteria, sheet maximum 25)."""
    await apply_template(seeded)
    return seeded


async def finished(s, *, project="manager", team_member=None):
    registration = await organized(s, project=project)
    attempt, _ = await start(s, registration)
    if team_member:
        async with s["uow"]() as u:
            u.session.add(
                ProjectParticipation(project_id=s["projects"][project], participant_id=s["users"][team_member].id)
            )
    await finish(s, attempt, now=NOW + timedelta(minutes=10))
    return attempt


async def fill(s, attempt, actor, score, *, now=OPEN, submit=True, comment=None):
    """Score every question of the attempt's type with `score` and (optionally) submit the sheet."""
    qids = await submit_cases.question_ids(s, attempt)
    await submit_cases.form(s, attempt, actor, now)
    async with s["uow"]() as u:
        await submit_cases.assessment_service(u, now).save_draft(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            s["users"][actor],
            AssessmentDraftWrite(answers=[AnswerDraftWrite(question_id=q, score=score, comment=comment) for q in qids]),
        )
    return await submit_cases.submit(s, attempt, actor, now=now) if submit else None


async def accept_real(s, attempt, *, version=0, reason=None, actor="teacher", now=AFTER_WINDOW):
    """Accept through the real SubmittedSheetSource (the shared `accept` helper uses a fake source)."""
    async with s["uow"]() as u:
        return await submit_cases.result_service(u, now).accept(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            ResultAccept(expected_version=version, reason=reason),
            s["users"][actor],
        )


async def raw(s, sql):
    async with s["engine"].connect() as connection:
        return [tuple(row) for row in (await connection.execute(text(sql))).all()]


SHEETS_SQL = (
    "SELECT sh.id, sh.user_id, sh.attempt_id, sh.status, su.id, su.version, su.total, su.submitted_at, "
    "sa.question_id, sa.score, sa.comment FROM exam_assessment_sheet sh "
    "LEFT JOIN exam_assessment_submission su ON su.sheet_id = sh.id "
    "LEFT JOIN exam_assessment_submission_answer sa ON sa.submission_id = su.id "
    "ORDER BY sh.id, su.version, sa.question_id"
)


# ── AC-01: three catalog sets ────────────────────────────────────────────────


def test_ac01_catalog_has_three_sets_of_fifteen_criteria_and_seventy_five_levels():
    templates = QuestionTemplateService().list_templates()
    assert [t.code for t in templates] == TEMPLATES
    assert sum(len(t.questions) for t in templates) == 15
    assert sum(len(q.levels) for t in templates for q in t.questions) == 75


@pytest.mark.parametrize("code", TEMPLATES)
async def test_ac01_five_fives_on_each_catalog_set_give_sheet_25_and_result_25_of_25(seeded, code):
    s = seeded
    await apply_template(s, code)
    attempt = await finished(s)
    submission = await fill(s, attempt, "local_teacher", 5)
    assert submission.total == 25 and len(submission.answers) == 5
    result = await accept_real(s, attempt)
    assert (result.edition.calculated_score, result.edition.final_score) == (Decimal("25.00"), Decimal("25.00"))
    assert (result.edition.snapshot.sheet_max, result.edition.snapshot.max_score) == (25, Decimal("25.00"))


# ── AC-02: own team excluded, others admitted, one person is one vote ───────


async def test_ac02_own_manager_and_member_get_403_on_form_draft_and_submit(seeded):
    s = seeded
    attempt = await finished(s, team_member="demoted")
    for actor in ("manager", "demoted"):
        with pytest.raises(PermissionError):
            await submit_cases.form(s, attempt, actor)
        with pytest.raises(PermissionError):
            await submit_cases.draft(s, attempt, actor, 5)
        with pytest.raises(PermissionError):
            await submit_cases.submit(s, attempt, actor)
    assert await raw(s, "SELECT * FROM exam_assessment_sheet") == []
    assert await raw(s, "SELECT * FROM exam_assessment_submission") == []
    items = by_name(await participation(s, attempt))
    assert (items["manager"].exclusion_reason, items["demoted"].exclusion_reason) == (
        "manager_of_defending_team",
        "member_of_defending_team",
    )


@pytest.mark.parametrize("actor", ["teacher", "local_teacher", "local_admin", "manager2", "null_manager", "member"])
async def test_ac02_other_teachers_managers_and_members_are_admitted(seeded, actor):
    s = seeded
    attempt = await finished(s, team_member="demoted")
    form = await submit_cases.form(s, attempt, actor)
    assert form.assessor.excluded is False and form.assessor.exclusion_reason is None
    assert form.assessor.role == {"manager2": "manager", "null_manager": "manager", "member": "member"}.get(
        actor, "teacher"
    )


async def test_ac02_several_project_links_give_one_audience_row_and_one_vote(five):
    s = five
    async with s["uow"]() as u:  # the member is also in two other projects besides his own authored one
        for project in ("manager", "local_manager"):
            u.session.add(
                ProjectParticipation(project_id=s["projects"][project], participant_id=s["users"]["member"].id)
            )
    attempt = await finished(s, project="manager2")
    member_id = s["users"]["member"].id
    assert await raw(
        s, f"SELECT count(*), bool_and(admitted) FROM assessment_window_audience WHERE user_id = {member_id}"
    ) == [(1, True)]
    await fill(s, attempt, "member", 4)
    await fill(s, attempt, "member", 5)  # a second edition of the same person
    async with s["uow"]() as u:
        counted = await SubmittedSheetSource(ExamAssessmentRepository(u)).load_submitted_sheets(attempt_id=attempt.id)
    assert [(x.role, x.total) for x in counted] == [("member", 25)]
    assert (await participation(s, attempt)).summary.member.submitted == 1


async def test_ac02_a_teacher_in_the_defending_team_is_still_admitted_as_teacher(five):
    s = five
    attempt = await finished(s, team_member="local_teacher")
    teacher = by_name(await participation(s, attempt))["local_teacher"]
    assert (teacher.role, teacher.status, teacher.exclusion_reason) == ("teacher", "not_submitted", None)
    assert (await fill(s, attempt, "local_teacher", 4)).total == 20


# ── AC-03: weights, scale, empty groups ────────────────────────────────────


async def three_roles(s, attempt):
    await fill(s, attempt, "local_teacher", 4)  # 20 of 25
    await fill(s, attempt, "manager2", 3)  # 15 of 25
    await fill(s, attempt, "member", 5)  # 25 of 25


async def test_ac03_weights_60_30_10_give_19_of_25_and_more_assessors_do_not_raise_a_role(five):
    s = five
    attempt = await finished(s)
    await three_roles(s, attempt)
    await fill(s, attempt, "null_manager", 3)  # a second manager with the same average
    await fill(s, attempt, "local_admin", 4)  # a second teacher with the same average
    result = await accept_real(s, attempt)
    assert result.edition.final_score == Decimal("19.00")
    assert result.edition.calculated_score == Decimal("19.00")
    counts = result.edition.snapshot.sheets
    assert (counts.teacher, counts.manager, counts.member) == (2, 2, 1)


async def test_ac03_new_settings_revision_recalculates_preliminary_and_marks_accepted_outdated(five):
    s = five
    attempt = await finished(s)
    await three_roles(s, attempt)
    first = await accept_real(s, attempt)
    await set_settings(s, weights=ExamWeights(teacher=20, manager=40, member=40), max_score=Decimal("50.00"))
    async with s["uow"]() as u:
        read = await submit_cases.result_service(u).get(
            s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"]
        )
    assert read.outdated is True
    assert read.preliminary.score == Decimal("40.00")  # (20*20 + 40*15 + 40*25) / 100 = 20 of 25 -> 40 of 50
    assert read.edition.version == 1 and read.edition.final_score == Decimal("19.00")
    assert read.edition.snapshot == first.edition.snapshot  # the accepted edition is not recalculated
    second = await accept_real(s, attempt, version=1, reason="Новые веса")
    assert (second.edition.version, second.edition.final_score) == (2, Decimal("40.00"))
    assert await raw(s, "SELECT version, final_score FROM exam_result_edition ORDER BY version") == [
        (1, Decimal("19.00")),
        (2, Decimal("40.00")),
    ]


async def test_ac03_empty_roles_are_not_zero_only_teacher_20_gives_20(five):
    s = five
    attempt = await finished(s)
    await fill(s, attempt, "local_teacher", 4)
    result = await accept_real(s, attempt)
    assert result.edition.final_score == Decimal("20.00")  # not 12 = 60% of 20
    snapshot = result.edition.snapshot
    assert (snapshot.sheets.manager, snapshot.sheets.member, snapshot.used_weight) == (0, 0, 60)


async def test_ac03_no_counted_sheets_means_no_calculation_and_never_zero(five):
    s = five
    attempt = await finished(s)
    await fill(s, attempt, "member", 3, submit=False)  # a draft is not a vote
    async with s["uow"]() as u:
        read = await submit_cases.result_service(u).get(
            s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"]
        )
    assert read.preliminary.no_calculation is True and read.preliminary.score is None
    assert await code_of(accept_real(s, attempt)) == "no_calculation"
    assert await count_rows(s, "exam_result_edition") == 0


# ── AC-06: window, server deadline, next team ──────────────────────────────


async def test_ac06_window_opens_by_finish_for_the_configured_minutes_and_deadline_is_server_side(seeded):
    s = seeded
    await set_window_minutes(s, 5)
    attempt = await finished(s)
    ((opened, closes, version),) = await raw(s, "SELECT opened_at, closes_at, settings_version FROM assessment_window")
    assert closes - opened == timedelta(minutes=5) and opened == NOW + timedelta(minutes=10) and version == 2
    before_close = closes - timedelta(seconds=1)
    first = await fill(s, attempt, "member", 3, now=before_close)
    assert first.version == 1
    for action in (
        submit_cases.submit(s, attempt, "member", now=closes),
        submit_cases.draft(s, attempt, "member", 1, now=closes),
    ):
        assert await code_of(action) == "assessment_window_closed"
    assert await raw(s, "SELECT version, total FROM exam_assessment_submission") == [(1, 3)]
    assert (await participation(s, attempt, now=closes)).state == "closed"


async def test_ac06_next_attempt_does_not_change_the_sheet_of_the_previous_one(seeded):
    s = seeded
    first = await finished(s, project="manager")
    await fill(s, first, "member", 4, comment="first team")
    snapshot_before = await raw(s, SHEETS_SQL)
    second_registration = await organized(s, project="local_manager")
    second, _ = await start(s, second_registration, now=AFTER_WINDOW)
    await finish(s, second, now=AFTER_WINDOW + timedelta(minutes=10))
    await fill(s, second, "member", 2, now=AFTER_WINDOW + timedelta(minutes=11), comment="second team")
    after = await raw(s, SHEETS_SQL)
    assert [row for row in after if row[2] == first.id] == snapshot_before  # first sheet is untouched
    assert {row[2] for row in after} == {first.id, second.id}
    assert len({row[0] for row in after}) == 2  # a separate sheet per attempt for the same assessor


# ── AC-07: who assessed ─────────────────────────────────────────────────────


async def test_ac07_participation_agrees_with_the_counted_sheets_and_a_draft_is_not_a_vote(five):
    s = five
    attempt = await finished(s, team_member="demoted")
    await fill(s, attempt, "local_teacher", 4)
    await fill(s, attempt, "manager2", 3)
    await fill(s, attempt, "member", 5, submit=False)  # draft only
    # A sheet that somehow exists for an excluded assessor must not count either.
    async with s["uow"]() as u:
        await u.session.execute(
            text(
                "INSERT INTO exam_assessment_sheet (workspace_id, exam_id, attempt_id, user_id, status) "
                "VALUES (:w, :e, :a, :u, 'draft')"
            ),
            {"w": s["workspace"], "e": s["exams"][0], "a": attempt.id, "u": s["users"]["manager"].id},
        )
    result = await participation(s, attempt)
    summary = result.summary
    assert (summary.total.submitted, summary.total.excluded) == (2, 2)
    assert by_name(result)["member"].status == "not_submitted"
    assert by_name(result)["manager"].status == "excluded"
    accepted = await accept_real(s, attempt)
    counts = accepted.edition.snapshot.sheets
    assert (counts.teacher, counts.manager, counts.member) == (
        summary.teacher.submitted,
        summary.manager.submitted,
        summary.member.submitted,
    )
    assert all(item.submission.version == 1 for item in result.items if item.status == "submitted")


# ── AC-08: decision ─────────────────────────────────────────────────────────


async def test_ac08_accept_and_manual_keep_both_values_reason_author_and_version_and_sheets_stay(five):
    s = five
    attempt = await finished(s)
    await three_roles(s, attempt)
    sheets_before = await raw(s, SHEETS_SQL)
    await accept_real(s, attempt)
    edition_one = await raw(s, "SELECT * FROM exam_result_edition WHERE version = 1")
    async with s["uow"]() as u:
        manual = await submit_cases.result_service(u).manual(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            ResultManual(expected_version=1, final_score=Decimal("21.50"), reason="Учтена устная часть"),
            s["users"]["local_teacher"],
        )
    edition = manual.edition
    assert (edition.version, edition.kind) == (2, "manual")
    assert (edition.calculated_score, edition.final_score) == (Decimal("19.00"), Decimal("21.50"))
    assert edition.reason == "Учтена устная часть" and edition.decided_by == s["users"]["local_teacher"].id
    assert (
        await raw(s, "SELECT * FROM exam_result_edition WHERE version = 1") == edition_one
    )  # old version is immutable
    assert await raw(s, SHEETS_SQL) == sheets_before  # source sheets are not touched by a decision


@pytest.mark.parametrize("actor", ["manager", "manager2", "member", "demoted", "admin"])
async def test_ac08_members_and_managers_cannot_decide(five, actor):
    s = five
    attempt = await finished(s)
    await three_roles(s, attempt)
    with pytest.raises(PermissionError):
        await accept_real(s, attempt, actor=actor)
    async with s["uow"]() as u:
        with pytest.raises(PermissionError):
            await submit_cases.result_service(u).manual(
                s["workspace"],
                s["exams"][0],
                attempt.id,
                ResultManual(expected_version=0, final_score=Decimal("10"), reason="r"),
                s["users"][actor],
            )
    assert await count_rows(s, "exam_result_edition") == 0


# ── Role and score are not taken from the client ───────────────────────────


def api_client(s, actor):
    app = FastAPI()
    app.include_router(routers)

    async def test_uow():
        async with s["uow"]() as u:
            yield u

    app.dependency_overrides[get_uow] = test_uow
    app.dependency_overrides[get_current_user] = lambda: s["users"][actor]
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


FORBIDDEN_EXTRAS = [
    {"role": "teacher"},
    {"weight": 100},
    {"score": 5},
    {"total": 25},
    {"kind": "manual"},
    {"calculated_score": "25.00"},
    {"final_score": "25.00"},
]


ENDPOINTS = [
    ("local_teacher", "PUT", "/assessment/draft", {"answers": []}),
    ("local_teacher", "POST", "/assessment/submit", {}),
    ("teacher", "POST", "/result/accept", {"expected_version": 0}),
    ("teacher", "POST", "/result/manual", {"expected_version": 0, "final_score": "20", "reason": "r"}),
]
# `final_score` is the legitimate field of the manual decision, everything else is not part of any contract.
CASES = [
    (*endpoint, extra)
    for endpoint in ENDPOINTS
    for extra in FORBIDDEN_EXTRAS
    if not (endpoint[2].endswith("manual") and "final_score" in extra)
]


@pytest.mark.parametrize("actor,method,path,body,extra", CASES)
async def test_ac_client_cannot_send_role_weight_score_total_or_kind(five, actor, method, path, body, extra):
    s = five
    attempt = await finished(s)
    url = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}{path}"
    async with api_client(s, actor) as client:
        response = await client.request(method, url, json={**body, **extra})
    assert response.status_code == 422
    assert await raw(s, "SELECT * FROM exam_assessment_submission") == []
    assert await raw(s, "SELECT * FROM exam_result_edition") == []


async def test_ac_answer_item_cannot_carry_role_or_weight(five):
    s = five
    attempt = await finished(s)
    qid = (await submit_cases.question_ids(s, attempt))[0]
    url = f"/v1/workspaces/{s['workspace']}/exams/{s['exams'][0]}/attempts/{attempt.id}/assessment/draft"
    async with api_client(s, "local_teacher") as client:
        for extra in ({"role": "teacher"}, {"weight": 100}):
            response = await client.put(url, json={"answers": [{"question_id": qid, "score": 5, **extra}]})
            assert response.status_code == 422


async def test_ac_user_cannot_pick_own_role_the_snapshot_role_wins(five):
    s = five
    attempt = await finished(s)
    form = await submit_cases.form(s, attempt, "member")
    assert (form.assessor.role, form.assessor.weight) == ("member", 10)
    await fill(s, attempt, "member", 5)
    async with s["uow"]() as u:
        counted = await SubmittedSheetSource(ExamAssessmentRepository(u)).load_submitted_sheets(attempt_id=attempt.id)
    assert [x.role for x in counted] == ["member"]


# ── Foreign ids ─────────────────────────────────────────────────────────────


async def test_ac_foreign_ids_do_not_open_exam_form_or_sheet(five):
    s = five
    attempt = await finished(s)
    await fill(s, attempt, "local_teacher", 4)
    with pytest.raises(NotFoundError):
        await submit_cases.submit(s, attempt, "local_teacher", workspace=s["foreign_workspace"])
    with pytest.raises(NotFoundError):
        await submit_cases.submit(s, attempt, "local_teacher", exam=1)
    with pytest.raises(PermissionError):  # a global teacher outside the audience cannot touch any sheet
        await submit_cases.submit(s, attempt, "outsider")
    assert await raw(s, "SELECT user_id FROM exam_assessment_sheet") == [(s["users"]["local_teacher"].id,)]


# ── Empty answers ───────────────────────────────────────────────────────────


async def test_ac_empty_answers_are_not_answers_incomplete_sheet_is_rejected_with_question_ids(five):
    s = five
    attempt = await finished(s)
    qids = await submit_cases.question_ids(s, attempt)
    await submit_cases.form(s, attempt, "local_teacher")
    async with s["uow"]() as u:  # score=None is a valid draft state and counts as "no answer"
        await submit_cases.assessment_service(u).save_draft(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            s["users"]["local_teacher"],
            AssessmentDraftWrite(
                answers=[AnswerDraftWrite(question_id=q, score=None, comment="только комментарий") for q in qids]
            ),
        )
    with pytest.raises(ValidationError) as error:
        await submit_cases.submit(s, attempt, "local_teacher")
    assert error.value.detail["code"] == "incomplete_sheet"
    assert error.value.detail["missing_question_ids"] == sorted(qids)

    await submit_cases.draft(s, attempt, "local_teacher", 4, question=qids[0])
    with pytest.raises(ValidationError) as error:
        await submit_cases.submit(s, attempt, "local_teacher")
    assert error.value.detail["missing_question_ids"] == sorted(qids[1:])
    assert await raw(s, "SELECT * FROM exam_assessment_submission") == []
    assert (await participation(s, attempt)).summary.total.submitted == 0
    assert await code_of(accept_real(s, attempt)) == "no_calculation"
