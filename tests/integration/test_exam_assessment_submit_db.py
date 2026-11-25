from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
import test_exam_results_db as results_cases
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from test_exam_results_db import AFTER_WINDOW, NOW, finished_attempt, set_participation

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError, ValidationError
from src.model.exam_assessment import (
    ExamAssessmentAnswer,
    ExamAssessmentSubmission,
    ExamAssessmentSubmissionAnswer,
)
from src.model.project_type_question import ProjectTypeQuestion, ProjectTypeQuestionLevel
from src.repository.exam_assessment_repository import ExamAssessmentRepository
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_repository import ExamRepository
from src.repository.exam_result_repository import ExamResultRepository
from src.repository.project_repository import ProjectRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.repository.workspace_repository import WorkSpaceRepository
from src.schema.exam_assessment import AnswerDraftWrite, AssessmentDraftWrite, AssessmentSubmitWrite
from src.schema.exam_result import ResultAccept
from src.services.exam_assessment_service import ExamAssessmentService
from src.services.exam_result_service import ExamResultService
from src.services.exam_service import ExamService
from src.services.exam_sheet_source import SubmittedSheetSource
from src.services.project_relations import ProjectRelationsService

pytestmark = pytest.mark.integration

# Fixtures are shared with the result tests (the real source is exercised with #114).
seeded_base = results_cases.seeded_base
seeded = results_cases.seeded

OPEN = NOW + timedelta(minutes=11)  # window is open from NOW+10m to NOW+13m
LAST_SECOND = AFTER_WINDOW - timedelta(seconds=1)


def assessment_service(uow, now=OPEN, *, clock=None):
    return ExamAssessmentService(
        ExamAssessmentRepository(uow),
        ExamAttemptRepository(uow),
        ProjectTypeQuestionRepository(uow),
        ExamRepository(uow),
        clock=clock or (lambda: now),
    )


def result_service(uow, now=AFTER_WINDOW):
    return ExamResultService(
        ExamResultRepository(uow),
        ExamAttemptRepository(uow),
        ExamRepository(uow),
        ExamService(ExamRepository(uow), ProjectTypeQuestionRepository(uow)),
        SubmittedSheetSource(ExamAssessmentRepository(uow)),
        ProjectRelationsService(ProjectRepository(uow), WorkSpaceRepository(uow)),
        clock=lambda: now,
    )


async def question_ids(s, attempt):
    async with s["uow"]() as u:
        rows = await u.session.scalars(
            select(ProjectTypeQuestion.id)
            .where(ProjectTypeQuestion.project_type_id == attempt.project_type_id)
            .order_by(ProjectTypeQuestion.position)
        )
        return list(rows)


async def form(s, attempt, actor, now=OPEN):
    async with s["uow"]() as u:
        return await assessment_service(u, now).get_form(s["workspace"], s["exams"][0], attempt.id, s["users"][actor])


async def draft(s, attempt, actor, score, *, comment=None, now=OPEN, question=None):
    qids = await question_ids(s, attempt)
    await form(s, attempt, actor, now)  # lazily creates the personal sheet
    async with s["uow"]() as u:
        return await assessment_service(u, now).save_draft(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            s["users"][actor],
            AssessmentDraftWrite(
                answers=[AnswerDraftWrite(question_id=question or qids[0], score=score, comment=comment)]
            ),
        )


async def submit(s, attempt, actor, *, now=OPEN, workspace=None, exam=0):
    async with s["uow"]() as u:
        return await assessment_service(u, now).submit(
            workspace or s["workspace"], s["exams"][exam], attempt.id, s["users"][actor]
        )


async def sources(s, attempt):
    async with s["uow"]() as u:
        return await SubmittedSheetSource(ExamAssessmentRepository(u)).load_submitted_sheets(attempt_id=attempt.id)


async def edition_count(s):
    async with s["uow"]() as u:
        return await u.session.scalar(select(func.count()).select_from(ExamAssessmentSubmission))


async def test_submissions_are_versioned_and_history_is_kept(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4, comment="first")
    first = await submit(s, attempt, "local_teacher")
    assert (first.version, first.total, first.unchanged) == (1, 4, False)

    again = await submit(s, attempt, "local_teacher")
    assert (again.version, again.unchanged) == (1, True)
    assert await edition_count(s) == 1

    await draft(s, attempt, "local_teacher", 5, comment="second")
    second = await submit(s, attempt, "local_teacher")
    assert (second.version, second.total, second.unchanged) == (2, 5, False)

    async with s["uow"]() as u:
        rows = (
            (await u.session.execute(select(ExamAssessmentSubmission).order_by(ExamAssessmentSubmission.version)))
            .scalars()
            .all()
        )
        assert [(r.version, r.total) for r in rows] == [(1, 4), (2, 5)]
        answers = (
            (
                await u.session.execute(
                    select(ExamAssessmentSubmissionAnswer).order_by(ExamAssessmentSubmissionAnswer.submission_id)
                )
            )
            .scalars()
            .all()
        )
        assert [(a.score, a.comment) for a in answers] == [(4, "first"), (5, "second")]
    assert (await form(s, attempt, "local_teacher")).submission.version == 2


async def test_form_reports_unsubmitted_changes(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    assert (await form(s, attempt, "member")).submission is None
    await draft(s, attempt, "member", 3)
    await submit(s, attempt, "member")
    state = (await form(s, attempt, "member")).submission
    assert (state.version, state.has_unsubmitted_changes) == (1, False)
    await draft(s, attempt, "member", 2)
    assert (await form(s, attempt, "member")).submission.has_unsubmitted_changes is True


async def test_deadline_uses_server_clock_for_submit_and_draft(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4)
    first = await submit(s, attempt, "local_teacher", now=LAST_SECOND)
    assert first.version == 1

    await draft(s, attempt, "local_teacher", 1, now=LAST_SECOND)
    with pytest.raises(BusinessLogicError) as error:
        await submit(s, attempt, "local_teacher", now=AFTER_WINDOW)
    assert error.value.detail["code"] == "assessment_window_closed"
    with pytest.raises(BusinessLogicError) as error:
        await draft(s, attempt, "local_teacher", 2, now=AFTER_WINDOW)
    assert error.value.detail["code"] == "assessment_window_closed"
    # The last valid edition still counts; the late attempts left nothing behind.
    assert await edition_count(s) == 1
    assert [(x.role, x.total) for x in await sources(s, attempt)] == [("teacher", 4)]


@pytest.mark.parametrize("explicit_answers", [False, True])
async def test_submit_that_reaches_cutoff_before_writing_does_not_report_success(seeded, explicit_answers):
    s = seeded
    attempt = await finished_attempt(s)
    actor = s["users"]["local_teacher"]
    await draft(s, attempt, "local_teacher", 4)
    qid = (await question_ids(s, attempt))[0]
    data = AssessmentSubmitWrite(answers=[AnswerDraftWrite(question_id=qid, score=5)]) if explicit_answers else None
    before_close = AFTER_WINDOW - timedelta(microseconds=200)
    clock = iter((before_close, before_close, AFTER_WINDOW))

    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await assessment_service(u, clock=lambda: next(clock)).submit(
                s["workspace"], s["exams"][0], attempt.id, actor, data
            )

    assert error.value.detail["code"] == "assessment_window_closed"
    assert await edition_count(s) == 0
    reopened = await form(s, attempt, "local_teacher", now=AFTER_WINDOW)
    assert reopened.submission is None
    assert reopened.draft.answers[0].score == 4


async def test_draft_waiting_for_another_save_rechecks_the_deadline(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    actor = s["users"]["local_teacher"]
    await draft(s, attempt, "local_teacher", 4)
    qid = (await question_ids(s, attempt))[0]
    now = LAST_SECOND
    entered = asyncio.Event()

    def clock():
        entered.set()
        return now

    async def save():
        async with s["uow"]() as uow:
            return await assessment_service(uow, clock=clock).save_draft(
                s["workspace"],
                s["exams"][0],
                attempt.id,
                actor,
                AssessmentDraftWrite(answers=[AnswerDraftWrite(question_id=qid, score=5)]),
            )

    async with s["uow"]() as locking:
        repository = ExamAssessmentRepository(locking)
        sheet = await repository.get_sheet(s["workspace"], s["exams"][0], attempt.id, actor.id)
        assert sheet is not None
        await repository.lock_sheet(sheet.id)
        await locking.session.execute(
            select(ExamAssessmentAnswer).where(ExamAssessmentAnswer.question_id == qid).with_for_update()
        )
        request = asyncio.create_task(save())
        await asyncio.wait_for(entered.wait(), timeout=3)
        now = AFTER_WINDOW

    with pytest.raises(BusinessLogicError) as error:
        await asyncio.wait_for(request, timeout=3)
    assert error.value.detail["code"] == "assessment_window_closed"
    assert (await form(s, attempt, "local_teacher", now=AFTER_WINDOW)).draft.answers[0].score == 4


async def test_incomplete_sheet_is_rejected_with_missing_questions(seeded):
    s = seeded
    async with s["uow"]() as u:
        extra = ProjectTypeQuestion(
            project_type_id=s["types"][0],
            text="Extra",
            position=50,
            levels=[ProjectTypeQuestionLevel(score=score, description=f"Level {score}") for score in range(1, 6)],
        )
        u.session.add(extra)
        await u.session.flush()
        extra_id = extra.id
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4)
    with pytest.raises(ValidationError) as error:
        await submit(s, attempt, "local_teacher")
    assert error.value.detail["code"] == "incomplete_sheet"
    assert error.value.detail["missing_question_ids"] == [extra_id]
    assert await edition_count(s) == 0
    assert await sources(s, attempt) == []

    await draft(s, attempt, "local_teacher", 3, question=extra_id)
    assert (await submit(s, attempt, "local_teacher")).total == 7


async def test_submit_without_opening_the_form_is_incomplete(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(ValidationError) as error:
        await submit(s, attempt, "local_teacher")
    assert error.value.detail["code"] == "incomplete_sheet"


async def test_excluded_foreign_and_outside_users_cannot_submit(seeded):
    s = seeded
    attempt = await finished_attempt(s)  # project "manager": its manager is excluded
    with pytest.raises(PermissionError):
        await submit(s, attempt, "manager")
    with pytest.raises(PermissionError):
        await submit(s, attempt, "outsider")
    with pytest.raises(NotFoundError):
        await submit(s, attempt, "local_teacher", workspace=s["foreign_workspace"])
    with pytest.raises(NotFoundError):
        await submit(s, attempt, "local_teacher", exam=1)
    async with s["uow"]() as u:
        assert await u.session.scalar(text("SELECT count(*) FROM exam_assessment_submission")) == 0
        assert await u.session.scalar(text("SELECT count(*) FROM exam_assessment_sheet")) == 0


async def test_draft_is_not_a_vote_and_later_edits_do_not_change_the_counted_edition(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4)
    assert await sources(s, attempt) == []

    await submit(s, attempt, "local_teacher")
    await draft(s, attempt, "local_teacher", 1)
    assert [(x.role, x.total) for x in await sources(s, attempt)] == [("teacher", 4)]


async def test_role_comes_from_the_snapshot_and_one_assessor_is_one_vote(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "member", 5)
    await submit(s, attempt, "member")
    await draft(s, attempt, "member", 4)
    await submit(s, attempt, "member")
    # The user is promoted after the window opened: the historical role must not change.
    await set_participation(s, "member", local="teacher")
    sheets = await sources(s, attempt)
    assert [(x.role, x.total) for x in sheets] == [("member", 4)]


async def test_excluded_sheet_of_a_snapshot_row_is_not_counted(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4)
    await submit(s, attempt, "local_teacher")
    async with s["uow"]() as u:  # even a sheet that somehow exists for an excluded assessor is ignored
        await u.session.execute(
            text(
                "INSERT INTO exam_assessment_sheet (workspace_id, exam_id, attempt_id, user_id, status) "
                "VALUES (:w, :e, :a, :u, 'submitted')"
            ),
            {"w": s["workspace"], "e": s["exams"][0], "a": attempt.id, "u": s["users"]["manager"].id},
        )
        sheet_id = await u.session.scalar(
            text("SELECT id FROM exam_assessment_sheet WHERE user_id = :u"), {"u": s["users"]["manager"].id}
        )
        await u.session.execute(
            text(
                "INSERT INTO exam_assessment_submission (workspace_id, exam_id, attempt_id, sheet_id, version, "
                "submitted_at, total) VALUES (:w, :e, :a, :s, 1, now(), 5)"
            ),
            {"w": s["workspace"], "e": s["exams"][0], "a": attempt.id, "s": sheet_id},
        )
    assert [(x.role, x.total) for x in await sources(s, attempt)] == [("teacher", 4)]


async def test_source_fails_loudly_without_window_or_snapshot(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    with pytest.raises(BusinessLogicError) as error:
        async with s["uow"]() as u:
            await SubmittedSheetSource(ExamAssessmentRepository(u)).load_submitted_sheets(attempt_id=999999)
    assert error.value.detail["code"] == "assessment_window_missing"
    async with s["uow"]() as u:
        await u.session.execute(text("DELETE FROM assessment_window_audience"))
    with pytest.raises(BusinessLogicError) as error:
        await sources(s, attempt)
    assert error.value.detail["code"] == "audience_snapshot_unavailable"


async def test_concurrent_submits_of_one_sheet_do_not_duplicate_versions(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4)
    results = await asyncio.gather(*[submit(s, attempt, "local_teacher") for _ in range(5)])
    assert {r.version for r in results} == {1}
    assert await edition_count(s) == 1


async def test_concurrent_submits_with_different_drafts_keep_consistent_versions(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4)
    await submit(s, attempt, "local_teacher")
    await draft(s, attempt, "local_teacher", 5)
    results = await asyncio.gather(*[submit(s, attempt, "local_teacher") for _ in range(4)])
    assert {r.version for r in results} == {2}
    async with s["uow"]() as u:
        versions = (
            await u.session.scalars(select(ExamAssessmentSubmission.version).order_by(ExamAssessmentSubmission.version))
        ).all()
    assert list(versions) == [1, 2]


async def test_database_forbids_duplicate_versions_and_bad_values(seeded):
    s = seeded
    attempt = await finished_attempt(s)
    await draft(s, attempt, "local_teacher", 4)
    first = await submit(s, attempt, "local_teacher")
    async with s["uow"]() as u:
        sheet_id = await u.session.scalar(select(ExamAssessmentSubmission.sheet_id))
    for version, total, constraint in [
        (1, 4, "uq_submission_sheet_version"),
        (0, 4, "ck_submission_version"),
        (2, 0, "ck_submission_total"),
    ]:
        with pytest.raises(IntegrityError) as error:
            async with s["uow"]() as u:
                u.session.add(
                    ExamAssessmentSubmission(
                        workspace_id=s["workspace"],
                        exam_id=s["exams"][0],
                        attempt_id=attempt.id,
                        sheet_id=sheet_id,
                        version=version,
                        submitted_at=OPEN,
                        total=total,
                    )
                )
        assert constraint in str(error.value)
    # Scope isolation: a submission cannot point to another workspace's sheet.
    with pytest.raises(IntegrityError):
        async with s["uow"]() as u:
            u.session.add(
                ExamAssessmentSubmission(
                    workspace_id=s["foreign_workspace"],
                    exam_id=s["exams"][0],
                    attempt_id=attempt.id,
                    sheet_id=sheet_id,
                    version=9,
                    submitted_at=OPEN,
                    total=4,
                )
            )
    assert first.version == 1


async def test_end_to_end_with_result_acceptance(seeded):
    """Sheets of three roles -> real source -> accept (#114): 60/30/10 with 4/3/5 of 5 gives 19 of 25."""
    s = seeded
    attempt = await finished_attempt(s)
    for actor, score in [("local_teacher", 4), ("local_manager", 3), ("member", 5)]:
        await draft(s, attempt, actor, score)
        await submit(s, attempt, actor)

    async with s["uow"]() as u:
        accepted = await result_service(u).accept(
            s["workspace"], s["exams"][0], attempt.id, ResultAccept(expected_version=0), s["users"]["teacher"]
        )
    assert accepted.edition.version == 1
    assert accepted.edition.final_score == Decimal("19.00")
    assert (
        accepted.edition.snapshot.sheets.teacher,
        accepted.edition.snapshot.sheets.manager,
        accepted.edition.snapshot.sheets.member,
    ) == (1, 1, 1)

    # Editing a draft after the submission does not change the preliminary result.
    await draft(s, attempt, "local_teacher", 1)
    async with s["uow"]() as u:
        read = await result_service(u).get(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
    assert read.preliminary.score == Decimal("19.00")
    assert read.outdated is False

    # A resubmission inside the window (before closes_at) replaces the counted sheet.
    await draft(s, attempt, "local_teacher", 5, now=LAST_SECOND)
    await submit(s, attempt, "local_teacher", now=LAST_SECOND)
    async with s["uow"]() as u:
        read = await result_service(u).get(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
    assert read.preliminary.score == Decimal("22.00")  # (60*5 + 30*3 + 10*5) / 100 = 4.4 of 5
    assert read.outdated is True

    async with s["uow"]() as u:
        second = await result_service(u).accept(
            s["workspace"],
            s["exams"][0],
            attempt.id,
            ResultAccept(expected_version=1, reason="Преподаватель исправил лист"),
            s["users"]["teacher"],
        )
    assert (second.edition.version, second.edition.final_score) == (2, Decimal("22.00"))
    async with s["uow"]() as u:
        editions = await result_service(u).editions(s["workspace"], s["exams"][0], attempt.id, s["users"]["teacher"])
    assert [(e.version, e.final_score) for e in editions.items] == [(1, Decimal("19.00")), (2, Decimal("22.00"))]
