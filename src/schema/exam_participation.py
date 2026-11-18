from __future__ import annotations

from datetime import datetime
from typing import Literal

from src.schema.exam import ExamDTO

PG_INTEGER_MAX = 2**31 - 1
ParticipationState = Literal["not_offered", "open", "closed"]
ParticipantRole = Literal["teacher", "manager", "member"]
ParticipantStatus = Literal["excluded", "submitted", "not_submitted"]
ParticipantExclusionReason = Literal["manager_of_defending_team", "member_of_defending_team"]


class ParticipationWindowRead(ExamDTO):
    opened_at: datetime
    closes_at: datetime
    settings_version: int


class ParticipationAnswerRead(ExamDTO):
    question_id: int
    score: int
    comment: str | None


class ParticipationSubmissionRead(ExamDTO):
    """Latest submitted edition of an assessor's sheet (drafts are never exposed)."""

    version: int
    submitted_at: datetime
    total: int
    answers: list[ParticipationAnswerRead]


class ParticipantRead(ExamDTO):
    user_id: int
    name: str
    role: ParticipantRole
    status: ParticipantStatus
    exclusion_reason: ParticipantExclusionReason | None = None
    submission: ParticipationSubmissionRead | None = None


class ParticipationCounts(ExamDTO):
    admitted: int = 0
    submitted: int = 0
    not_submitted: int = 0
    excluded: int = 0


class ParticipationSummary(ExamDTO):
    total: ParticipationCounts
    teacher: ParticipationCounts
    manager: ParticipationCounts
    member: ParticipationCounts


class ParticipationRead(ExamDTO):
    workspace_id: int
    exam_id: int
    attempt_id: int
    state: ParticipationState
    window: ParticipationWindowRead | None
    summary: ParticipationSummary
    items: list[ParticipantRead]
