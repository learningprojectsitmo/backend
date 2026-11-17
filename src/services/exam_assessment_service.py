from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from src.core.exceptions import BusinessLogicError, NotFoundError, PermissionError, ValidationError
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
    AssessmentSubmissionRead,
    AssessmentWindowRead,
    AssessorRead,
    QuestionLevelRead,
    QuestionWithLevelsRead,
    SubmissionAnswerRead,
    SubmissionStateRead,
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

    @staticmethod
    def _conflict(code: str):
        raise BusinessLogicError({"code": code, "message": code.replace("_", " ")})

    def _require_open(self, window) -> None:
        # Server clock is the only authority: the window closes exactly at closes_at.
        if self._clock() >= window.closes_at:
            self._conflict("assessment_window_closed")

    @staticmethod
    def _normalized(rows: dict[int, tuple[int | None, str | None]], valid_ids: set[int]):
        return {
            question_id: (score, comment)
            for question_id, (score, comment) in rows.items()
            if question_id in valid_ids and (score is not None or comment is not None)
        }

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
        submission_state = await self._submission_state(sheet.id, answers, {q.id for q in questions})

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
            submission=submission_state,
        )

    async def _submission_state(self, sheet_id: int, answers, valid_ids: set[int]) -> SubmissionStateRead | None:
        latest = await self._repo.latest_submission(sheet_id)
        if latest is None:
            return None
        submitted = await self._repo.submission_answers(latest.id)
        draft = self._normalized({qid: (a.score, a.comment) for qid, a in answers.items()}, valid_ids)
        return SubmissionStateRead(
            version=latest.version,
            submitted_at=latest.submitted_at,
            has_unsubmitted_changes=draft != self._normalized(dict(submitted), valid_ids),
        )

    async def save_draft(
        self, workspace_id: int, exam_id: int, attempt_id: int, user: User, data: AssessmentDraftWrite
    ) -> AssessmentDraftRead:
        attempt, window, _project = await self._load(workspace_id, exam_id, attempt_id)
        access = await self._determine_access(window.id, user.id, workspace_id)
        if access.excluded:
            raise PermissionError(f"Excluded from assessment: {access.exclusion_reason}")

        self._require_open(window)

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

    async def submit(self, workspace_id: int, exam_id: int, attempt_id: int, user: User) -> AssessmentSubmissionRead:
        """Snapshot the saved draft as a new immutable edition (idempotent for an unchanged draft)."""
        attempt, window, _project = await self._load(workspace_id, exam_id, attempt_id)
        access = await self._determine_access(window.id, user.id, workspace_id)
        if access.excluded:
            raise PermissionError(f"Excluded from assessment: {access.exclusion_reason}")
        self._require_open(window)

        questions = await self._questions.list_questions(attempt.project_type_id)
        question_ids = [q.id for q in questions]
        sheet = await self._repo.get_sheet(workspace_id, exam_id, attempt_id, user.id)
        if sheet is None:
            self._incomplete(question_ids)
        # Serialize concurrent submits of this sheet, then re-check the deadline after the wait.
        await self._repo.lock_sheet(sheet.id)
        self._require_open(window)

        drafts = await self._repo.get_answers(sheet.id)
        missing = [qid for qid in question_ids if drafts.get(qid) is None or drafts[qid].score is None]
        if missing:
            self._incomplete(missing)
        snapshot = {qid: (int(drafts[qid].score), drafts[qid].comment) for qid in question_ids}

        latest = await self._repo.latest_submission(sheet.id)
        unchanged = False
        if latest is not None and await self._repo.submission_answers(latest.id) == snapshot:
            submission, unchanged = latest, True
        else:
            submission = await self._repo.add_submission(
                sheet,
                version=1 if latest is None else latest.version + 1,
                submitted_at=self._clock(),
                answers=snapshot,
            )
        return AssessmentSubmissionRead(
            version=submission.version,
            submitted_at=submission.submitted_at,
            total=submission.total,
            answers=[
                SubmissionAnswerRead(question_id=qid, score=score, comment=comment)
                for qid, (score, comment) in sorted(snapshot.items())
            ],
            unchanged=unchanged,
        )

    @staticmethod
    def _incomplete(missing_question_ids: list[int]):
        raise ValidationError(
            {
                "code": "incomplete_sheet",
                "message": "every question of the project type must have a score",
                "missing_question_ids": sorted(missing_question_ids),
            }
        )
