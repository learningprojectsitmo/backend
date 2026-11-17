from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError
from src.model.user import User
from src.repository.exam_assessment_repository import ExamAssessmentRepository
from src.repository.exam_attempt_repository import ExamAttemptRepository
from src.repository.exam_repository import ExamRepository
from src.repository.project_type_question_repository import ProjectTypeQuestionRepository
from src.schema.exam_assessment import (
    AnswerDraftRead,
    AssessmentDraftRead,
    AssessmentDraftWrite,
    AssessmentFormRead,
    AssessmentWindowRead,
    AssessorRead,
    QuestionLevelRead,
    QuestionWithLevelsRead,
)


class ExamAssessmentService:
    def __init__(
        self,
        repository: ExamAssessmentRepository,
        attempts: ExamAttemptRepository,
        questions: ProjectTypeQuestionRepository,
        exams: ExamRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self._repo = repository
        self._attempts = attempts
        self._questions = questions
        self._exams = exams
        self._clock = clock or (lambda: datetime.now(UTC))

    async def _determine_access(self, window_id: int, user_id: int, workspace_id: int) -> AssessorRead:
        audience = await self._repo.get_audience(window_id, workspace_id, user_id)
        if audience is None:
            if not await self._repo.has_audience(window_id, workspace_id):
                raise BusinessLogicError(
                    {
                        "code": "audience_snapshot_unavailable",
                        "message": "Historical audience is unavailable for this assessment window",
                    }
                )
            raise PermissionError("User is not in the captured assessment audience")
        reasons = {
            "member_of_defending_team": "own_project_member",
            "manager_of_defending_team": "own_project_manager",
        }
        return AssessorRead(
            role=audience.role,
            weight=0,
            excluded=not audience.admitted,
            exclusion_reason=reasons.get(audience.exclusion_reason),
        )

    async def _weights(self, exam_id: int, settings_version: int) -> tuple[int, int, int]:
        revision = await self._exams.get_revision(exam_id, settings_version)
        if revision is None:
            raise NotFoundError("Settings revision not found")
        return revision.teacher_weight, revision.manager_weight, revision.member_weight

    async def _weight_for(self, role: str, exam_id: int, settings_version: int) -> int:
        teacher, manager, member = await self._weights(exam_id, settings_version)
        if role == "teacher":
            return teacher
        if role == "manager":
            return manager
        return member

    async def _load(self, workspace_id: int, exam_id: int, attempt_id: int):
        """Fetch attempt+window+project scoped; raise 404 when missing or not finished."""
        result = await self._repo.get_attempt_with_window_and_project(workspace_id, exam_id, attempt_id)
        if result is None:
            raise NotFoundError("Attempt not found")
        attempt, window, project = result
        if attempt.status != "finished":
            raise NotFoundError("Assessment not open")
        if window is None:
            raise NotFoundError("Assessment window not found")
        return attempt, window, project

    async def get_form(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> AssessmentFormRead:
        attempt, window, _project = await self._load(workspace_id, exam_id, attempt_id)
        access = await self._determine_access(window.id, user.id, workspace_id)
        if access.excluded:
            raise PermissionError(f"Excluded from assessment: {access.exclusion_reason}")
        weight = await self._weight_for(access.role, exam_id, window.settings_version)
        access = access.model_copy(update={"weight": weight})

        sheet = await self._repo.get_or_create_sheet(workspace_id, exam_id, attempt_id, user.id)
        questions = await self._questions.list_questions(attempt.project_type_id)
        answers = await self._repo.get_answers(sheet.id)

        question_reads = [
            QuestionWithLevelsRead(
                id=q.id,
                text=q.text,
                description=q.description,
                position=q.position,
                levels=[QuestionLevelRead(score=level.score, description=level.description) for level in q.levels],
            )
            for q in questions
        ]
        answer_reads = [
            AnswerDraftRead(question_id=qid, score=answer.score, comment=answer.comment)
            for qid, answer in answers.items()
        ]
        draft = AssessmentDraftRead(answers=answer_reads, updated_at=sheet.updated_at)

        return AssessmentFormRead(
            attempt_id=attempt.id,
            project_id=attempt.project_id,
            project_type_id=attempt.project_type_id,
            window=AssessmentWindowRead(
                opened_at=window.opened_at,
                closes_at=window.closes_at,
                settings_version=window.settings_version,
            ),
            assessor=access,
            questions=question_reads,
            draft=draft,
        )

    async def save_draft(
        self, workspace_id: int, exam_id: int, attempt_id: int, user: User, data: AssessmentDraftWrite
    ) -> AssessmentDraftRead:
        attempt, window, _project = await self._load(workspace_id, exam_id, attempt_id)
        access = await self._determine_access(window.id, user.id, workspace_id)
        if access.excluded:
            raise PermissionError(f"Excluded from assessment: {access.exclusion_reason}")

        sheet = await self._repo.get_sheet(workspace_id, exam_id, attempt_id, user.id)
        if sheet is None:
            raise NotFoundError("Draft not found — open the form first")

        # Filter to question_ids that belong to the attempt's project type.
        questions = await self._questions.list_questions(attempt.project_type_id)
        valid_ids = {q.id for q in questions}
        filtered = [(a.question_id, a.score, a.comment) for a in data.answers if a.question_id in valid_ids]
        await self._repo.upsert_answers(sheet.id, filtered)

        answers = await self._repo.get_answers(sheet.id)
        # Reload the sheet for fresh updated_at.
        sheet = await self._repo.get_sheet(workspace_id, exam_id, attempt_id, user.id)
        answer_reads = [
            AnswerDraftRead(question_id=qid, score=answer.score, comment=answer.comment)
            for qid, answer in answers.items()
        ]
        return AssessmentDraftRead(answers=answer_reads, updated_at=sheet.updated_at if sheet else self._clock())
