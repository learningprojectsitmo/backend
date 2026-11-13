from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schema.exam_attempt import AttemptRead, PositiveId

QueueState = Literal["waiting", "running", "postponed", "no_show", "finished"]


class QueueDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class QueuePlace(QueueDTO):
    expected_version: PositiveId
    position: PositiveId | None = None


class QueueCommand(QueueDTO):
    expected_version: PositiveId


class QueueReason(QueueCommand):
    reason: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("NUL is not allowed in a reason")
            return value.strip()
        return value


class QueueItemRead(QueueDTO):
    registration_id: int
    project_id: int
    project_type_id: int
    slot_id: int | None
    planned_start_at: datetime | None
    planned_end_at: datetime | None
    position: PositiveId | None = None
    state: QueueState
    registration_version: int
    started_at: datetime | None
    attempt: AttemptRead | None = None


class QueueRead(QueueDTO):
    queue_revision: int
    server_now: datetime
    items: list[QueueItemRead]


class QueueMutationRead(QueueDTO):
    item: QueueItemRead
    queue_revision: int
    server_now: datetime
