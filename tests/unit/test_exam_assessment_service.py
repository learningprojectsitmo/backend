from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import NotFoundError, PermissionError
from src.schema.exam import ExamConfiguration, ExamWeights
from src.schema.exam_assessment import AssessmentDraftWrite, AnswerDraftWrite
from src.services.exam_assessment_service import ExamAssessmentService


def _service(**overrides):
    repo = AsyncMock()
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


class TestDetermineAccess:
    async def test_teacher_from_local_role(self):
        svc, repo, *_ = _service()
        repo.is_excluded = AsyncMock(return_value=(False, None))
        repo.get_workspace_participation = AsyncMock(return_value=(True, "teacher"))
        repo.get_global_role = AsyncMock(return_value="member")
        result = await svc._determine_access(MagicMock(), 1, 1)
        assert result.role == "teacher"

    async def test_manager_role(self):
        svc, repo, *_ = _service()
        repo.is_excluded = AsyncMock(return_value=(False, None))
        repo.get_workspace_participation = AsyncMock(return_value=(True, "manager"))
        repo.get_global_role = AsyncMock(return_value="member")
        result = await svc._determine_access(MagicMock(), 1, 1)
        assert result.role == "manager"

    async def test_member_role(self):
        svc, repo, *_ = _service()
        repo.is_excluded = AsyncMock(return_value=(False, None))
        repo.get_workspace_participation = AsyncMock(return_value=(True, "member"))
        repo.get_global_role = AsyncMock(return_value="member")
        result = await svc._determine_access(MagicMock(), 1, 1)
        assert result.role == "member"

    async def test_global_admin_without_workspace(self):
        svc, repo, *_ = _service()
        repo.is_excluded = AsyncMock(return_value=(False, None))
        repo.get_workspace_participation = AsyncMock(return_value=(False, None))
        repo.get_global_role = AsyncMock(return_value="admin")
        result = await svc._determine_access(MagicMock(), 1, 1)
        assert result.role == "teacher"

    async def test_excluded_manager_propagates(self):
        svc, repo, *_ = _service()
        repo.is_excluded = AsyncMock(return_value=(True, "own_project_manager"))
        repo.get_workspace_participation = AsyncMock(return_value=(True, "manager"))
        repo.get_global_role = AsyncMock(return_value="member")
        result = await svc._determine_access(MagicMock(), 1, 1)
        assert result.excluded is True
        assert result.exclusion_reason == "own_project_manager"


class TestGetForm:
    async def test_get_form_full_structure(self):
        svc, repo, attempts, questions, exams = _service()
        attempt = MagicMock(status="finished", project_id=10, project_type_id=5, settings_version=1)
        window = MagicMock(opened_at=datetime(2026, 11, 16, 10, 30, tzinfo=UTC),
                           closes_at=datetime(2026, 11, 16, 10, 45, tzinfo=UTC), settings_version=1)
        project = MagicMock(id=10)
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, window, project))
        repo.is_excluded = AsyncMock(return_value=(False, None))
        repo.get_workspace_participation = AsyncMock(return_value=(True, "teacher"))
        repo.get_global_role = AsyncMock(return_value="member")
        repo.get_or_create_sheet = AsyncMock(return_value=MagicMock(id=1, updated_at=datetime(2026, 11, 16, 10, 35, tzinfo=UTC)))
        repo.get_answers = AsyncMock(return_value={})
        revision = MagicMock(teacher_weight=60, manager_weight=30, member_weight=10)
        exams.get_revision = AsyncMock(return_value=revision)
        q = MagicMock(id=1, text="Q1", description="desc", position=0,
                      levels=[MagicMock(score=s, description=f"L{s}") for s in range(1, 6)])
        questions.list_questions = AsyncMock(return_value=[q])

        from src.model.user import User
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
        repo.is_excluded = AsyncMock(return_value=(True, "own_project_manager"))
        repo.get_workspace_participation = AsyncMock(return_value=(True, "manager"))
        repo.get_global_role = AsyncMock(return_value="member")
        from src.model.user import User
        with pytest.raises(PermissionError):
            await svc.get_form(1, 1, 1, MagicMock(spec=User, id=1))


class TestSaveDraft:
    async def test_save_draft_upserts_and_returns(self):
        svc, repo, attempts, questions, exams = _service()
        attempt = MagicMock(status="finished", project_type_id=5, settings_version=1)
        window = MagicMock()
        project = MagicMock()
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, window, project))
        sheet = MagicMock(id=1, updated_at=datetime(2026, 11, 16, 10, 35, tzinfo=UTC))
        repo.get_sheet = AsyncMock(return_value=sheet)
        repo.is_excluded = AsyncMock(return_value=(False, None))
        repo.get_workspace_participation = AsyncMock(return_value=(True, "teacher"))
        repo.get_global_role = AsyncMock(return_value="member")
        q = MagicMock(id=1)
        questions.list_questions = AsyncMock(return_value=[q])
        repo.upsert_answers = AsyncMock(return_value={1: 4})
        repo.get_answers = AsyncMock(return_value={1: 4})

        data = AssessmentDraftWrite(answers=[AnswerDraftWrite(question_id=1, score=4, comment="ok")])
        result = await svc.save_draft(1, 1, 1, MagicMock(id=1), data)
        assert result.answers[0].score == 4

    async def test_save_draft_sheet_not_found_returns_404(self):
        svc, repo, *_ = _service()
        attempt = MagicMock(status="finished", project_type_id=5)
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, MagicMock(), MagicMock()))
        repo.is_excluded = AsyncMock(return_value=(False, None))
        repo.get_workspace_participation = AsyncMock(return_value=(True, "teacher"))
        repo.get_global_role = AsyncMock(return_value="member")
        repo.get_sheet = AsyncMock(return_value=None)
        with pytest.raises(NotFoundError):
            await svc.save_draft(1, 1, 1, MagicMock(id=1), AssessmentDraftWrite(answers=[]))

    async def test_save_draft_ignores_unknown_question_ids(self):
        svc, repo, attempts, questions, exams = _service()
        attempt = MagicMock(status="finished", project_type_id=5)
        repo.get_attempt_with_window_and_project = AsyncMock(return_value=(attempt, MagicMock(), MagicMock()))
        sheet = MagicMock(id=1, updated_at=datetime(2026, 11, 16, 10, 35, tzinfo=UTC))
        repo.get_sheet = AsyncMock(return_value=sheet)
        repo.is_excluded = AsyncMock(return_value=(False, None))
        repo.get_workspace_participation = AsyncMock(return_value=(True, "teacher"))
        repo.get_global_role = AsyncMock(return_value="member")
        questions.list_questions = AsyncMock(return_value=[])  # no questions
        repo.upsert_answers = AsyncMock(return_value={})
        repo.get_answers = AsyncMock(return_value={})

        data = AssessmentDraftWrite(answers=[AnswerDraftWrite(question_id=999, score=3, comment=None)])
        result = await svc.save_draft(1, 1, 1, MagicMock(id=1), data)
        # unknown question_id was filtered out, no answers persisted
        assert result.answers == []