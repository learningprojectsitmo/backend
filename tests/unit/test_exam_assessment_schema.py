from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.schema.exam_assessment import (
    AnswerDraftRead,
    AnswerDraftWrite,
    AssessmentDraftRead,
    AssessmentDraftWrite,
    AssessmentFormRead,
    AssessmentWindowRead,
    AssessorRead,
    QuestionLevelRead,
    QuestionWithLevelsRead,
)


class TestAnswerDraftWrite:
    def test_valid_score_4(self):
        a = AnswerDraftWrite(question_id=1, score=4, comment=None)
        assert a.score == 4

    def test_score_null_allowed(self):
        a = AnswerDraftWrite(question_id=1, score=None, comment=None)
        assert a.score is None

    def test_score_0_rejected(self):
        with pytest.raises(ValidationError):
            AnswerDraftWrite(question_id=1, score=0)

    def test_score_6_rejected(self):
        with pytest.raises(ValidationError):
            AnswerDraftWrite(question_id=1, score=6)

    def test_question_id_must_be_positive(self):
        with pytest.raises(ValidationError):
            AnswerDraftWrite(question_id=0, score=3)

    def test_comment_max_5000(self):
        a = AnswerDraftWrite(question_id=1, score=3, comment="x" * 5000)
        assert len(a.comment) == 5000
        with pytest.raises(ValidationError):
            AnswerDraftWrite(question_id=1, score=3, comment="x" * 5001)


class TestAssessmentDraftWrite:
    def test_empty_answers_allowed(self):
        d = AssessmentDraftWrite(answers=[])
        assert d.answers == []

    def test_valid_with_answers(self):
        d = AssessmentDraftWrite(
            answers=[
                AnswerDraftWrite(question_id=1, score=4, comment="ok"),
                AnswerDraftWrite(question_id=2, score=None, comment=None),
            ]
        )
        assert len(d.answers) == 2

    def test_answer_field_must_be_list(self):
        with pytest.raises(ValidationError):
            AssessmentDraftWrite(answers="not_a_list")


class TestAssessorRead:
    def test_valid_teacher(self):
        a = AssessorRead(role="teacher", weight=60, excluded=False, exclusion_reason=None)
        assert a.role == "teacher"

    def test_excluded_manager(self):
        a = AssessorRead(role="manager", weight=30, excluded=True, exclusion_reason="own_project_manager")
        assert a.excluded is True

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            AssessorRead(role="supervisor", weight=60, excluded=False, exclusion_reason=None)

    def test_exclusion_reason_null_when_not_excluded(self):
        a = AssessorRead(role="member", weight=10, excluded=False, exclusion_reason=None)
        assert a.exclusion_reason is None


class TestAssessmentWindowRead:
    def test_valid_window(self):
        w = AssessmentWindowRead(
            opened_at="2026-11-16T10:30:00Z",
            closes_at="2026-11-16T10:45:00Z",
            settings_version=3,
        )
        assert w.settings_version == 3


class TestQuestionWithLevelsRead:
    def test_valid_question_with_5_levels(self):
        q = QuestionWithLevelsRead(
            id=1,
            text="Question text",
            description="desc",
            position=0,
            levels=[QuestionLevelRead(score=s, description=f"Level {s}") for s in range(1, 6)],
        )
        assert len(q.levels) == 5

    def test_levels_must_be_unique_scores(self):
        q = QuestionWithLevelsRead(
            id=1,
            text="Q",
            description=None,
            position=0,
            levels=[
                QuestionLevelRead(score=1, description="A"),
                QuestionLevelRead(score=2, description="B"),
            ],
        )
        assert len(q.levels) == 2


class TestAssessmentFormRead:
    def test_full_form_structure(self):
        now = datetime(2026, 11, 16, 10, 35, tzinfo=UTC)
        form = AssessmentFormRead(
            attempt_id=1,
            project_id=10,
            project_type_id=5,
            window=AssessmentWindowRead(
                opened_at="2026-11-16T10:30:00Z",
                closes_at="2026-11-16T10:45:00Z",
                settings_version=3,
            ),
            assessor=AssessorRead(role="teacher", weight=60, excluded=False, exclusion_reason=None),
            questions=[
                QuestionWithLevelsRead(
                    id=1,
                    text="Q1",
                    description="desc",
                    position=0,
                    levels=[QuestionLevelRead(score=s, description=f"L{s}") for s in range(1, 6)],
                )
            ],
            draft=AssessmentDraftRead(answers=[], updated_at=now),
        )
        assert form.attempt_id == 1
        assert form.draft.answers == []

    def test_form_with_draft_answers(self):
        now = datetime(2026, 11, 16, 10, 35, tzinfo=UTC)
        form = AssessmentFormRead(
            attempt_id=1,
            project_id=10,
            project_type_id=5,
            window=AssessmentWindowRead(
                opened_at="2026-11-16T10:30:00Z",
                closes_at="2026-11-16T10:45:00Z",
                settings_version=3,
            ),
            assessor=AssessorRead(role="teacher", weight=60, excluded=False, exclusion_reason=None),
            questions=[],
            draft=AssessmentDraftRead(
                answers=[
                    AnswerDraftRead(question_id=1, score=4, comment="Good"),
                    AnswerDraftRead(question_id=2, score=None, comment=None),
                ],
                updated_at=now,
            ),
        )
        assert len(form.draft.answers) == 2
        assert form.draft.answers[0].score == 4
        assert form.draft.answers[1].score is None
