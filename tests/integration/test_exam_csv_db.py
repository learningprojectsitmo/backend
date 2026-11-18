from __future__ import annotations

from decimal import Decimal

import pytest
import test_exam_results_db as results_cases
from sqlalchemy import text
from test_exam_assessment_submit_db import assessment_service, draft, question_ids, result_service, submit
from test_exam_attempts_db import organized, set_settings, start
from test_exam_results_db import accept, finished_attempt, insert_row, set_participation

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam_assessment import AssessmentDraftWrite
from src.schema.exam_result import ResultAccept
from src.schema.project_type_question import QuestionListReplace
from src.services.exam_csv_service import ExamCsvService
from src.services.project_type_question_service import ProjectTypeQuestionService
from src.services.question_template_service import QuestionTemplateService

pytestmark = pytest.mark.integration
seeded_base = results_cases.seeded_base
seeded = results_cases.seeded


async def snapshot(s, *, actor="teacher", workspace=None, exam=0, **kwargs):
    return await ExamCsvService(s["uow"], **kwargs).snapshot(
        workspace or s["workspace"], s["exams"][exam], s["users"][actor]
    )


async def test_register_keeps_registration_without_attempt_and_missing_values(seeded):
    registration = await organized(seeded)
    data = await snapshot(seeded)
    assert len(data.register) == 1
    row = data.register[0]
    assert row["registration_id"] == registration.id
    assert row["attempt_id"] is None and row["calculated_score"] is None and row["final_score"] is None
    assert row["eligible_count"] is None and row["presence"] == "unknown"
    assert row["registration_status"] == "active"


async def test_register_uses_complete_saved_edition_despite_new_settings(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await accept(s, attempt)
    await set_settings(s, max_score=Decimal("100.00"))
    row = (await snapshot(s)).register[0]
    assert (row["calculated_score"], row["final_score"], row["max_score"]) == (
        Decimal("19.00"),
        Decimal("19.00"),
        Decimal("25.00"),
    )
    assert row["settings_version"] == row["result_version"] == 1
    assert row["teacher_weight"] == 60 and row["decided_by_id"] == s["users"]["teacher"].id


async def test_register_manual_zero_without_calculation_is_not_empty(seeded):
    attempt = await finished_attempt(seeded)
    await insert_row(
        seeded, attempt, kind="manual", calculated_score=None, final_score=Decimal(0), reason="Нет голосов"
    )
    row = (await snapshot(seeded)).register[0]
    assert row["final_score"] == 0 and row["calculated_score"] is None
    assert row["decision_state"] == "accepted" and row["result_kind"] == "manual"


@pytest.mark.parametrize("actor", ["local_teacher", "local_admin", "teacher"])
async def test_workspace_teachers_can_export_empty_exam(seeded, actor):
    assert (await snapshot(seeded, actor=actor)).register == []


@pytest.mark.parametrize("actor", ["manager", "member", "local_manager", "demoted", "admin"])
async def test_non_workspace_teachers_cannot_export(seeded, actor):
    with pytest.raises(PermissionError):
        await snapshot(seeded, actor=actor)


async def test_foreign_scope_and_outsider_cannot_export(seeded):
    with pytest.raises(NotFoundError):
        await snapshot(seeded, workspace=seeded["foreign_workspace"])
    with pytest.raises(NotFoundError):
        await snapshot(seeded, actor="outsider")
    await set_participation(seeded, "teacher", local="member")
    with pytest.raises(PermissionError):
        await snapshot(seeded)


async def test_participation_uses_history_last_submission_and_never_drafts(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4)
    await submit(s, attempt, "local_teacher")
    await draft(s, attempt, "local_teacher", 5)
    await submit(s, attempt, "local_teacher")
    await draft(s, attempt, "local_teacher", 2, comment="PRIVATE DRAFT")
    await draft(s, attempt, "member", 3)
    await set_participation(s, "local_teacher", local="member")
    async with s["uow"]() as u:
        await u.session.execute(
            text("UPDATE project SET author_id=:u WHERE id=:p"),
            {"u": s["users"]["member"].id, "p": s["projects"]["manager"]},
        )
    data = await snapshot(s)
    rows = {r["assessor_id"]: r for r in data.participation}
    teacher = rows[s["users"]["local_teacher"].id]
    assert (teacher["response_status"], teacher["role"], teacher["submission_version"], teacher["total"]) == (
        "submitted",
        "teacher",
        2,
        5,
    )
    assert teacher["criterion_1_score"] == 5 and "PRIVATE DRAFT" not in repr(data)
    assert rows[s["users"]["member"].id]["response_status"] == "not_submitted"
    excluded = rows[s["users"]["manager"].id]
    assert excluded["response_status"] == "excluded" and excluded["admitted"] is False
    assert excluded["exclusion_reason"] == "manager_of_defending_team" and excluded["total"] is None
    assert len(data.participation) == len(rows)
    register = data.register[0]
    assert register["submitted_count"] == 1 and register["calculated_score"] == Decimal("25.00")
    assert register["eligible_count"] == sum(
        r["response_status"] in ("submitted", "not_submitted") for r in rows.values()
    )
    assert register["excluded_count"] == sum(r["response_status"] == "excluded" for r in rows.values())


async def test_not_requested_is_current_preview_and_not_historical_admission(seeded):
    s = seeded
    reg = await organized(s)
    attempt, _ = await start(s, reg)
    data = await snapshot(s)
    assert data.participation
    assert all(r["attempt_id"] == attempt.id and r["response_status"] == "not_requested" for r in data.participation)
    assert all(r["admitted"] is None and r["audience_source"] == "preview" for r in data.participation)
    assert data.register[0]["eligible_count"] is None


async def test_missing_historical_snapshot_aborts_both_profiles(seeded):
    await finished_attempt(seeded)
    async with seeded["uow"]() as u:
        await u.session.execute(text("DELETE FROM assessment_window_audience"))
    with pytest.raises(BusinessLogicError) as error:
        await snapshot(seeded)
    assert error.value.detail["code"] == "audience_snapshot_unavailable"


@pytest.mark.parametrize("n", [1, 5, 7])
async def test_all_custom_questions_from_one_edition_in_question_order(seeded, n):
    s = seeded
    async with s["uow"]() as u:
        await ProjectTypeQuestionService(ProjectTypeQuestionRepository(u), QuestionTemplateService()).replace_questions(
            s["workspace"],
            s["types"][0],
            QuestionListReplace(
                questions=[
                    {"text": f"Вопрос {i}", "levels": [{"score": v, "description": str(v)} for v in range(1, 6)]}
                    for i in range(n)
                ]
            ),
            s["users"]["teacher"],
        )
    attempt = await finished_attempt(s)
    qids = await question_ids(s, attempt)
    async with s["uow"]() as u:
        service = assessment_service(u)
        await service.get_form(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
        await service.save_draft(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            s["users"]["teacher"],
            AssessmentDraftWrite(answers=[{"question_id": qid, "score": 5} for qid in reversed(qids)]),
        )
        await service.submit(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
    async with s["uow"]() as u:
        await result_service(u).accept(
            s["workspace"], s["exams"][0], attempt.id, ResultAccept(expected_version=0), s["users"]["teacher"]
        )
    data = await snapshot(s)
    row = next(r for r in data.participation if r["assessor_id"] == s["users"]["teacher"].id)
    assert row["total"] == n * 5
    assert [row[f"criterion_{i + 1}_question_id"] for i in range(n)] == qids
    assert [row[f"criterion_{i + 1}_score"] for i in range(n)] == [5] * n
    assert data.register[0]["sheet_max"] == n * 5 and data.register[0]["final_score"] == Decimal("25.00")
