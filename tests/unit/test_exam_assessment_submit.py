# ruff: noqa: ARG002
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError, ValidationError
from src.schema.exam_assessment import AssessmentDraftWrite, AssessmentSubmitWrite
from src.services.exam_assessment_service import ExamAssessmentService
from src.services.exam_score import SheetScore
from src.services.exam_sheet_source import SubmittedSheetSource

NOW = datetime(2026, 11, 16, 10, 40, tzinfo=UTC)
CLOSES = NOW + timedelta(minutes=5)
QUESTIONS = [1, 2, 3]


class FakeRepo:
    """In-memory stand-in for ExamAssessmentRepository (draft answers, editions, audience)."""

    def __init__(self, *, closes_at=CLOSES, role="teacher", admitted=True):
        self.attempt = SimpleNamespace(status="finished", id=7, project_id=10, project_type_id=5)
        self.window = SimpleNamespace(id=3, opened_at=NOW, closes_at=closes_at, settings_version=1)
        self.audience = SimpleNamespace(
            role=role, admitted=admitted, exclusion_reason=None if admitted else "member_of_defending_team"
        )
        self.sheet = SimpleNamespace(id=11, status="draft", updated_at=NOW, workspace_id=1, exam_id=2, attempt_id=7)
        self.drafts: dict[int, SimpleNamespace] = {}
        self.editions: list[SimpleNamespace] = []
        self.locked = 0

    async def get_attempt_with_window_and_project(self, workspace_id, exam_id, attempt_id):
        if (workspace_id, exam_id, attempt_id) != (1, 2, 7):
            return None
        return self.attempt, self.window, MagicMock()

    async def get_audience(self, window_id, workspace_id, user_id):
        return self.audience

    async def has_audience(self, window_id, workspace_id):
        return True

    async def get_sheet(self, *args):
        return self.sheet

    async def get_or_create_sheet(self, *args):
        return self.sheet

    async def get_answers(self, sheet_id):
        return dict(self.drafts)

    async def lock_sheet(self, sheet_id):
        self.locked += 1

    async def latest_submission(self, sheet_id):
        return self.editions[-1] if self.editions else None

    async def submission_answers(self, submission_id):
        return dict(next(e for e in self.editions if e.id == submission_id).answers)

    async def add_submission(self, sheet, *, version, submitted_at, answers):
        edition = SimpleNamespace(
            id=len(self.editions) + 100,
            version=version,
            submitted_at=submitted_at,
            answers=dict(answers),
            total=sum(score for score, _ in answers.values()),
        )
        self.editions.append(edition)
        sheet.status = "submitted"
        return edition

    def draft(self, **scores):
        for key, score in scores.items():
            self.drafts[int(key[1:])] = SimpleNamespace(score=score, comment=None)


def make(repo=None, now=NOW):
    repo = repo or FakeRepo()
    questions = AsyncMock()
    questions.list_questions.return_value = [
        SimpleNamespace(id=q, text="t", description=None, position=q, levels=[]) for q in QUESTIONS
    ]
    exams = AsyncMock()
    exams.get_revision.return_value = SimpleNamespace(teacher_weight=60, manager_weight=30, member_weight=10)
    clock = {"now": now}
    service = ExamAssessmentService(repo, AsyncMock(), questions, exams, clock=lambda: clock["now"])
    return service, repo, clock


USER = SimpleNamespace(id=5)


async def submit(service):
    return await service.submit(1, 2, 7, USER)


async def test_first_submit_creates_version_one_with_total():
    service, repo, _ = make()
    repo.draft(q1=5, q2=4, q3=3)
    result = await submit(service)
    assert (result.version, result.total, result.unchanged) == (1, 12, False)
    assert [a.score for a in result.answers] == [5, 4, 3]
    assert repo.sheet.status == "submitted"
    assert repo.locked >= 1


async def test_unchanged_resubmit_returns_same_edition():
    service, repo, _ = make()
    repo.draft(q1=5, q2=4, q3=3)
    first = await submit(service)
    second = await submit(service)
    assert second.unchanged is True
    assert second.version == first.version == 1
    assert len(repo.editions) == 1


async def test_changed_draft_makes_next_version():
    service, repo, _ = make()
    repo.draft(q1=5, q2=4, q3=3)
    await submit(service)
    repo.draft(q3=5)
    result = await submit(service)
    assert (result.version, result.total, result.unchanged) == (2, 14, False)
    assert len(repo.editions) == 2


async def test_comment_change_makes_new_version_but_not_total_change():
    service, repo, _ = make()
    repo.draft(q1=5, q2=4, q3=3)
    await submit(service)
    repo.drafts[1].comment = "good"
    result = await submit(service)
    assert (result.version, result.total) == (2, 12)


async def test_draft_edit_after_submit_does_not_change_counted_edition():
    service, repo, _ = make()
    repo.draft(q1=5, q2=4, q3=3)
    await submit(service)
    repo.draft(q1=1)
    assert repo.editions[-1].total == 12
    assert repo.editions[-1].answers[1] == (5, None)


async def test_incomplete_sheet_lists_missing_questions():
    service, repo, _ = make()
    repo.draft(q1=5, q3=None)
    with pytest.raises(ValidationError) as error:
        await submit(service)
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "incomplete_sheet"
    assert error.value.detail["missing_question_ids"] == [2, 3]
    assert repo.editions == []


async def test_missing_sheet_is_incomplete_not_created():
    service, repo, _ = make()
    repo.sheet = None
    repo.get_sheet = AsyncMock(return_value=None)
    with pytest.raises(ValidationError) as error:
        await submit(service)
    assert error.value.detail["missing_question_ids"] == QUESTIONS


async def test_submit_at_or_after_closes_at_is_rejected():
    service, repo, clock = make()
    repo.draft(q1=5, q2=4, q3=3)
    clock["now"] = CLOSES
    with pytest.raises(BusinessLogicError) as error:
        await submit(service)
    assert error.value.detail["code"] == "assessment_window_closed"
    clock["now"] = CLOSES - timedelta(seconds=1)
    assert (await submit(service)).version == 1


async def test_resubmit_after_close_keeps_last_valid_edition():
    service, repo, clock = make()
    repo.draft(q1=5, q2=4, q3=3)
    await submit(service)
    repo.draft(q1=1)
    clock["now"] = CLOSES + timedelta(minutes=1)
    with pytest.raises(BusinessLogicError):
        await submit(service)
    assert len(repo.editions) == 1


async def test_excluded_assessor_is_forbidden():
    service, _repo, _ = make(FakeRepo(admitted=False, role="member"))
    with pytest.raises(PermissionError):
        await submit(service)


async def test_user_outside_audience_is_forbidden():
    repo = FakeRepo()
    repo.audience = None
    service, repo, _ = make(repo)
    with pytest.raises(PermissionError):
        await submit(service)


async def test_missing_snapshot_is_conflict():
    repo = FakeRepo()
    repo.audience = None
    repo.has_audience = AsyncMock(return_value=False)
    service, repo, _ = make(repo)
    with pytest.raises(BusinessLogicError) as error:
        await submit(service)
    assert error.value.detail["code"] == "audience_snapshot_unavailable"


async def test_foreign_scope_is_not_found():
    service, _repo, _ = make()
    with pytest.raises(NotFoundError):
        await service.submit(99, 2, 7, USER)


async def test_unfinished_attempt_is_not_found():
    service, repo, _ = make()
    repo.attempt.status = "speaking"
    with pytest.raises(NotFoundError):
        await submit(service)


async def test_draft_save_after_close_is_rejected():
    service, _repo, clock = make()
    clock["now"] = CLOSES
    with pytest.raises(BusinessLogicError) as error:
        await service.save_draft(1, 2, 7, USER, AssessmentDraftWrite(answers=[]))
    assert error.value.detail["code"] == "assessment_window_closed"


async def test_form_submission_state():
    service, repo, _ = make()
    form = await service.get_form(1, 2, 7, USER)
    assert form.submission is None
    repo.draft(q1=5, q2=4, q3=3)
    await submit(service)
    form = await service.get_form(1, 2, 7, USER)
    assert (form.submission.version, form.submission.has_unsubmitted_changes) == (1, False)
    repo.draft(q2=2)
    form = await service.get_form(1, 2, 7, USER)
    assert form.submission.has_unsubmitted_changes is True
    repo.draft(q2=4)
    form = await service.get_form(1, 2, 7, USER)
    assert form.submission.has_unsubmitted_changes is False


def test_submit_body_rejects_role_weight_and_scores():
    assert AssessmentSubmitWrite() is not None
    for extra in ({"role": "teacher"}, {"weight": 100}, {"answers": []}, {"total": 25}):
        with pytest.raises(PydanticValidationError):
            AssessmentSubmitWrite(**extra)


class TestSubmittedSheetSource:
    async def test_returns_scores_with_snapshot_roles(self):
        repo = AsyncMock()
        repo.window_for_attempt.return_value = SimpleNamespace(id=3, workspace_id=1)
        repo.has_audience.return_value = True
        repo.counted_sheets.return_value = [("teacher", 20), ("member", 15)]
        sheets = await SubmittedSheetSource(repo).load_submitted_sheets(attempt_id=7)
        assert sheets == [SheetScore(role="teacher", total=20), SheetScore(role="member", total=15)]

    async def test_empty_vote_is_empty_list_when_snapshot_exists(self):
        repo = AsyncMock()
        repo.window_for_attempt.return_value = SimpleNamespace(id=3, workspace_id=1)
        repo.has_audience.return_value = True
        repo.counted_sheets.return_value = []
        assert await SubmittedSheetSource(repo).load_submitted_sheets(attempt_id=7) == []

    async def test_missing_window_fails_loudly(self):
        repo = AsyncMock()
        repo.window_for_attempt.return_value = None
        with pytest.raises(BusinessLogicError) as error:
            await SubmittedSheetSource(repo).load_submitted_sheets(attempt_id=7)
        assert error.value.detail["code"] == "assessment_window_missing"

    async def test_missing_audience_fails_loudly(self):
        repo = AsyncMock()
        repo.window_for_attempt.return_value = SimpleNamespace(id=3, workspace_id=1)
        repo.has_audience.return_value = False
        with pytest.raises(BusinessLogicError) as error:
            await SubmittedSheetSource(repo).load_submitted_sheets(attempt_id=7)
        assert error.value.detail["code"] == "audience_snapshot_unavailable"
