from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

PG_INTEGER_MAX = 2**31 - 1
PositiveId = Annotated[StrictInt, Field(ge=1, le=PG_INTEGER_MAX)]

AttemptStatus = Literal["speaking", "questions", "finished"]
AttemptAction = Literal["started", "questions", "paused", "resumed", "finished"]


class AttemptDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AttemptStart(AttemptDTO):
    registration_id: PositiveId
    expected_version: PositiveId


class AttemptCommand(AttemptDTO):
    expected_version: PositiveId


class AttemptPause(AttemptCommand):
    reason: Annotated[str, Field(min_length=1, max_length=1000)] | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("NUL is not allowed in a reason")
            return value.strip()
        return value


class AttemptWindowRead(AttemptDTO):
    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)
    opened_at: datetime
    closes_at: datetime
    settings_version: int
    project_type_id: int


class AttemptRead(AttemptDTO):
    id: int
    workspace_id: int
    exam_id: int
    registration_id: int
    project_id: int
    project_type_id: int
    status: AttemptStatus
    version: int
    settings_version: int
    started_at: datetime
    phase_started_at: datetime
    phase_deadline: datetime
    paused_at: datetime | None
    paused_seconds: int
    finished_at: datetime | None
    created_by: int
    created_at: datetime
    updated_at: datetime
    remaining_seconds: int
    server_now: datetime
    assessment_window: AttemptWindowRead | None = None


class CurrentAttemptRead(AttemptDTO):
    attempt: AttemptRead | None


class AttemptEventRead(AttemptDTO):
    id: int
    attempt_id: int
    version: int
    action: AttemptAction
    actor_id: int
    occurred_at: datetime
    reason: str | None = None


class AttemptEventListRead(AttemptDTO):
    items: list[AttemptEventRead]
    limit: int
    offset: int
    has_more: bool


class AttemptTiming(AttemptDTO):
    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)
    presentation_minutes: int
    questions_minutes: int
