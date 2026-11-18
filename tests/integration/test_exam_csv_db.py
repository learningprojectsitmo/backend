from __future__ import annotations

from decimal import Decimal

import pytest
import test_exam_results_db as results_cases
from fastapi import HTTPException
from sqlalchemy import text
from test_exam_assessment_submit_db import AFTER_WINDOW, assessment_service, draft, question_ids, result_service, submit
from test_exam_attempts_db import NOW, attempt_service, organized, set_settings, start
from test_exam_results_db import accept, finished_attempt, insert_row, set_participation

import src.services.exam_csv_participation as participation
from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam import ExamPublish, ExamSettingsReplace
from src.schema.exam_assessment import AssessmentDraftWrite
from src.schema.exam_attempt import AttemptPostpone
from src.schema.exam_result import ResultAccept
from src.schema.project_type_question import QuestionListReplace
from src.services.exam_csv_service import ExamCsvService
from src.services.exam_service import ExamService
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


async def test_saved_calculation_counts_and_edition_identity_remain_together(seeded):
    attempt = await finished_attempt(seeded)
    await accept(seeded, attempt)
    row = (await snapshot(seeded)).register[0]
    assert row["result_id"] > 0
    assert [row[f"result_{role}_sheets"] for role in ("teacher", "manager", "member")] == [1, 1, 1]
    assert row["used_weight"] == 100


async def test_multiple_links_and_teacher_own_team_are_one_historical_row(seeded):
    s = seeded
    async with s["uow"]() as u:
        for project in ["manager", "manager2"]:
            await u.session.execute(
                text("INSERT INTO project_participation (project_id,participant_id,role) VALUES (:p,:u,'member')"),
                {"p": s["projects"][project], "u": s["users"]["teacher"].id},
            )
    await finished_attempt(s)
    rows = [r for r in (await snapshot(s)).participation if r["assessor_id"] == s["users"]["teacher"].id]
    assert len(rows) == 1 and rows[0]["admitted"] is True and rows[0]["role"] == "teacher"
    assert (
        rows[0]["own_project_ids"]
        == "[" + ",".join(map(str, sorted([s["projects"]["manager"], s["projects"]["manager2"]]))) + "]"
    )


async def test_late_invalid_submission_does_not_hide_last_valid_edition(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "teacher", 4)
    await submit(s, attempt, "teacher")
    async with s["uow"]() as u:
        await u.session.execute(
            text("""INSERT INTO exam_assessment_submission
            (workspace_id,exam_id,attempt_id,sheet_id,version,submitted_at,total)
            SELECT workspace_id,exam_id,attempt_id,sheet_id,2,:late,1 FROM exam_assessment_submission"""),
            {"late": AFTER_WINDOW},
        )
    row = next(r for r in (await snapshot(s)).participation if r["assessor_id"] == s["users"]["teacher"].id)
    assert row["submission_version"] == 1 and row["total"] == row["criterion_1_score"] == 4


async def test_finished_without_votes_preliminary_is_empty_but_known_counts_are_zero(seeded):
    await finished_attempt(seeded)
    row = (await snapshot(seeded)).register[0]
    assert row["decision_state"] == "no_calculation" and row["calculated_score"] is None
    assert row["submitted_count"] == 0 and row["eligible_count"] > 0


async def test_postponed_attempt_has_preview_not_a_no_show(seeded):
    s = seeded
    reg = await organized(s)
    attempt, _ = await start(s, reg)
    async with s["uow"]() as u:
        await attempt_service(u, NOW).postpone(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            AttemptPostpone(expected_version=1, reason="Позже"),
            s["users"]["teacher"],
        )
    data = await snapshot(s)
    row = data.register[0]
    assert row["defense_status"] == "postponed" and row["presence"] == "present" and row["postponed_at"] is not None
    assert all(p["response_status"] == "not_requested" for p in data.participation)


async def test_mixed_types_keep_question_identity_and_pad_inapplicable_positions(seeded):
    s = seeded
    async with s["uow"]() as u:
        qservice = ProjectTypeQuestionService(ProjectTypeQuestionRepository(u), QuestionTemplateService())
        await qservice.replace_questions(
            s["workspace"],
            s["types"][1],
            QuestionListReplace(
                questions=[
                    {"text": f"Other {i}", "levels": [{"score": v, "description": str(v)} for v in range(1, 6)]}
                    for i in range(7)
                ]
            ),
            s["users"]["teacher"],
        )
        await u.session.execute(
            text("UPDATE project SET project_type_id=:t WHERE id=:p"),
            {"t": s["types"][1], "p": s["projects"]["manager2"]},
        )
    # Allowed types are part of the published schedule: configure the fixture's draft before publishing.
    async with s["uow"]() as u:
        exams = ExamService(ExamRepository(u), ProjectTypeQuestionRepository(u))
        current = await exams.get(s["workspace"], s["draft"], s["users"]["teacher"])
        await exams.replace_settings(
            s["workspace"],
            s["draft"],
            ExamSettingsReplace(
                expected_version=1,
                reason="Mixed types",
                configuration=current.configuration.model_copy(update={"project_type_ids": tuple(s["types"][:2])}),
            ),
            s["users"]["teacher"],
        )
        await exams.publish(s["workspace"], s["draft"], ExamPublish(expected_version=2), s["users"]["teacher"])
    s["exams"][0] = s["draft"]
    first = await finished_attempt(s, project="manager")
    second = await finished_attempt(s, project="manager2")
    data = await snapshot(s)
    assert data.criterion_count == 7
    first_rows = [p for p in data.participation if p["attempt_id"] == first.id]
    second_rows = [p for p in data.participation if p["attempt_id"] == second.id]
    assert first_rows and second_rows
    assert all(p["criterion_2_question_id"] is None and p["criterion_7_score"] is None for p in first_rows)
    assert all(p["criterion_7_question_id"] is not None and p["criterion_7_text"] == "Other 6" for p in second_rows)


async def test_scoped_exam_export_does_not_include_other_exam_registrations(seeded):
    first = await organized(seeded, project="manager", exam=0)
    second = await organized(seeded, project="manager2", exam=1)
    assert [r["registration_id"] for r in (await snapshot(seeded, exam=0)).register] == [first.id]
    assert [r["registration_id"] for r in (await snapshot(seeded, exam=1)).register] == [second.id]


async def test_output_cell_limit_rejects_large_preview_before_building_rows(seeded, monkeypatch):
    reg = await organized(seeded)
    await start(seeded, reg)
    monkeypatch.setattr(participation, "MAX_OUTPUT_CELLS", 1)
    with pytest.raises(HTTPException) as error:
        await snapshot(seeded)
    assert error.value.status_code == 413
