from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schema.exam_attempt import AttemptRead, PositiveId

QueueState = Literal["waiting", "running", "postponed", "no_show", "finished"]
EtaCertainty = Literal["certain", "lower_bound"]
EtaReason = Literal["paused", "overdue", "before_start"]
EtaItemState = Literal["waiting", "postponed"]


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


class EtaCurrentRead(QueueDTO):
    registration_id: int
    attempt_id: int
    status: Literal["speaking", "questions"]
    paused: bool
    phase_remaining_seconds: int
    slot_remaining_seconds: int
    overdue_seconds: int
    settings_version: int


class EtaItemRead(QueueDTO):
    registration_id: int
    position: PositiveId
    state: EtaItemState
    eta_seconds: int
    eta_at: datetime
    certainty: EtaCertainty
    reason: EtaReason | None = None


class QueueEtaRead(QueueDTO):
    current: EtaCurrentRead | None
    items: list[EtaItemRead]


class QueueRead(QueueDTO):
    queue_revision: int
    server_now: datetime
    settings_version: int
    eta_stale: bool
    contract_version: int = 1
    items: list[QueueItemRead]
    eta: QueueEtaRead


class QueueMutationRead(QueueDTO):
    item: QueueItemRead
    queue_revision: int
    server_now: datetime
