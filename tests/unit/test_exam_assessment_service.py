from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.user import User
from src.schema.exam_assessment import AnswerDraftWrite, AssessmentDraftWrite
from src.services.exam_assessment_service import ExamAssessmentService


def _service(**overrides):
    repo = AsyncMock()
    repo.get_audience.return_value = MagicMock(role="teacher", admitted=True, exclusion_reason=None)
    attempts = AsyncMock()
    questions = AsyncMock()
    exams = AsyncMock()
    defaults = {
        "repository": repo,
        "attempts": attempts,
        "questions": questions,
        "exams": exams,
    }
    defaults.update(overrides)
    return ExamAssessmentService(**defaults), repo, attempts, questions, exams


def _open_window():
    return MagicMock(closes_at=datetime(2099, 1, 1, tzinfo=UTC))


class TestDetermineAccess:
    @pytest.mark.parametrize("role", ["teacher", "manager", "member"])
    async def test_captured_role_is_used(self, role):
        svc, repo, *_ = _service()
        repo.get_audience.return_value = MagicMock(role=role, admitted=True, exclusion_reason=None)
        result = await svc._determine_access(10, 20, 30)
        assert result.role == role
        assert result.excluded is False
        repo.get_audience.assert_awaited_once_with(10, 30, 20)

    async def test_missing_historical_audience_is_reported(self):
        svc, repo, *_ = _service()
        repo.get_audience.return_value = None
        repo.has_audience.return_value = False
        with pytest.raises(BusinessLogicError) as error:
            await svc._determine_access(1, 2, 3)
        assert error.value.detail["code"] == "audience_snapshot_unavailable"

    async def test_user_absent_from_existing_audience_is_denied(self):
        svc, repo, *_ = _service()
        repo.get_audience.return_value = None
        repo.has_audience.return_value = True
        with pytest.raises(PermissionError):
            await svc._determine_access(1, 2, 3)


class TestGetForm:
    async def test_get_form_full_structure(self):
        svc, repo, _attempts, questions, exams = _service()
        attempt = MagicMock(status="finished", project_id=10, project_type_id=5, settings_version=1)
        window = MagicMock(
            opened_at=datetime(2026, 11, 16, 10, 30, tzinfo=UTC),
            closes_at=datetime(2026, 11, 16, 10, 45, tzinfo=UTC),
            settings_version=1,
        )
        project = MagicMock(id=10)
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, window, project))
        repo.get_or_create_sheet = AsyncMock(
            return_value=MagicMock(id=1, updated_at=datetime(2026, 11, 16, 10, 35, tzinfo=UTC))
        )
        repo.get_answers = AsyncMock(return_value={})
        repo.latest_submission = AsyncMock(return_value=None)
        revision = MagicMock(teacher_weight=60, manager_weight=30, member_weight=10)
        exams.get_revision = AsyncMock(return_value=revision)
        q = MagicMock(
            id=1,
            text="Q1",
            description="desc",
            position=0,
            levels=[MagicMock(score=s, description=f"L{s}") for s in range(1, 6)],
        )
        questions.list_questions = AsyncMock(return_value=[q])

        user = MagicMock(spec=User, id=1)
        form = await svc.get_form(1, 1, 1, user)
        assert form.attempt_id == 1
        assert form.project_id == 10
        assert form.project_type_id == 5
        assert form.assessor.role == "teacher"
        assert form.assessor.weight == 60
        assert len(form.questions) == 1
        assert len(form.questions[0].levels) == 5

    async def test_get_form_no_window_returns_404(self):
        svc, repo, *_ = _service()
        attempt = MagicMock(status="finished")
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, None, MagicMock()))
        with pytest.raises(NotFoundError):
            await svc.get_form(1, 1, 1, MagicMock(id=1))

    async def test_get_form_attempt_not_finished_returns_404(self):
        svc, repo, *_ = _service()
        attempt = MagicMock(status="speaking")
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, MagicMock(), MagicMock()))
        with pytest.raises(NotFoundError):
            await svc.get_form(1, 1, 1, MagicMock(id=1))

    async def test_get_form_excluded_returns_403(self):
        svc, repo, *_ = _service()
        attempt = MagicMock(status="finished")
        window = MagicMock()
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, window, MagicMock()))
        repo.get_audience.return_value = MagicMock(
            role="manager", admitted=False, exclusion_reason="manager_of_defending_team"
        )
        with pytest.raises(PermissionError):
            await svc.get_form(1, 1, 1, MagicMock(spec=User, id=1))


class TestSaveDraft:
    async def test_save_draft_upserts_and_returns(self):
        svc, repo, _attempts, questions, _exams = _service()
        attempt = MagicMock(status="finished", project_type_id=5, settings_version=1)
        project = MagicMock()
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, _open_window(), project))
        sheet = MagicMock(id=1, updated_at=datetime(2026, 11, 16, 10, 35, tzinfo=UTC))
        repo.get_sheet = AsyncMock(return_value=sheet)
        q = MagicMock(id=1, levels=[MagicMock(score=s) for s in range(1, 6)])
        questions.list_questions = AsyncMock(return_value=[q])
        answer = MagicMock(score=4, comment="ok")
        repo.upsert_answers = AsyncMock(return_value={1: answer})
        repo.get_answers = AsyncMock(return_value={1: answer})

        data = AssessmentDraftWrite(answers=[AnswerDraftWrite(question_id=1, score=4, comment="ok")])
        result = await svc.save_draft(1, 1, 1, MagicMock(id=1), data)
        assert result.answers[0].score == 4
        assert result.answers[0].comment == "ok"

    async def test_save_draft_sheet_not_found_returns_404(self):
        svc, repo, *_ = _service()
        attempt = MagicMock(status="finished", project_type_id=5)
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, _open_window(), MagicMock()))
        repo.get_sheet = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await svc.save_draft(1, 1, 1, MagicMock(id=1), AssessmentDraftWrite(answers=[]))

    async def test_save_draft_ignores_unknown_question_ids(self):
        svc, repo, _attempts, questions, _exams = _service()
        attempt = MagicMock(status="finished", project_type_id=5)
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, _open_window(), MagicMock()))
        sheet = MagicMock(id=1, updated_at=datetime(2026, 11, 16, 10, 35, tzinfo=UTC))
        repo.get_sheet = AsyncMock(return_value=sheet)
        questions.list_questions = AsyncMock(return_value=[])  # no questions
        repo.upsert_answers = AsyncMock(return_value={})
        repo.get_answers = AsyncMock(return_value={})

        data = AssessmentDraftWrite(answers=[AnswerDraftWrite(question_id=999, score=3, comment=None)])
        result = await svc.save_draft(1, 1, 1, MagicMock(id=1), data)
        # unknown question_id was filtered out, no answers persisted
        assert result.answers == []
