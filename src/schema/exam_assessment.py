from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

PG_INTEGER_MAX = 2**31 - 1
PositiveId = Annotated[StrictInt, Field(ge=1, le=PG_INTEGER_MAX)]
AssessorRole = Literal["teacher", "manager", "member"]
ExclusionReason = Literal["own_project_manager", "own_project_member", "not_workspace_member"]


class AssessmentDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AnswerDraftWrite(AssessmentDTO):
    question_id: PositiveId
    score: Annotated[int | None, Field(ge=1, le=5, default=None)]
    comment: Annotated[str | None, Field(max_length=5000, default=None)]


class AssessmentDraftWrite(AssessmentDTO):
    answers: list[AnswerDraftWrite]


class AnswerDraftRead(AssessmentDTO):
    question_id: int
    score: int | None
    comment: str | None


class AssessmentDraftRead(AssessmentDTO):
    answers: list[AnswerDraftRead]
    updated_at: datetime


class AssessorRead(AssessmentDTO):
    role: AssessorRole
    weight: Annotated[int, Field(ge=0, le=100)]
    excluded: bool
    exclusion_reason: ExclusionReason | None = None


class AssessmentWindowRead(AssessmentDTO):
    opened_at: datetime
    closes_at: datetime
    settings_version: PositiveId


class QuestionLevelRead(AssessmentDTO):
    score: int
    description: str


class QuestionWithLevelsRead(AssessmentDTO):
    id: int
    text: str
    description: str | None
    position: int
    levels: list[QuestionLevelRead]


class AssessmentSubmitWrite(AssessmentDTO):
    """Submit takes no data: the server snapshots the saved draft. Role, weight and scores are never accepted."""


class SubmissionAnswerRead(AssessmentDTO):
    question_id: int
    score: int
    comment: str | None


class AssessmentSubmissionRead(AssessmentDTO):
    version: PositiveId
    submitted_at: datetime
    total: int
    answers: list[SubmissionAnswerRead]
    # True when the draft matched the latest edition, so no new version was created.
    unchanged: bool


class SubmissionStateRead(AssessmentDTO):
    version: PositiveId
    submitted_at: datetime
    has_unsubmitted_changes: bool


class AssessmentFormRead(AssessmentDTO):
    attempt_id: int
    project_id: int
    project_type_id: int
    window: AssessmentWindowRead
    assessor: AssessorRead
    questions: list[QuestionWithLevelsRead]
    draft: AssessmentDraftRead
    submission: SubmissionStateRead | None = None
