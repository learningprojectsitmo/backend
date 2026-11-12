from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

PG_INTEGER_MAX = 2**31 - 1
PositiveId = Annotated[StrictInt, Field(ge=1, le=PG_INTEGER_MAX)]

RegistrationStatus = Literal["active", "cancelled", "moved"]
RegistrationSource = Literal["manager", "organizer"]
EventAction = Literal["created", "cancelled", "slot_changed", "moved_out", "moved_in", "defense_started"]


class RegistrationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SlotCreate(RegistrationDTO):
    starts_at: datetime
    ends_at: datetime

    @field_validator("starts_at", "ends_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone is required")
        try:
            return value.astimezone(UTC)
        except OverflowError as error:
            raise ValueError("Timestamp is outside the supported UTC range") from error

    @model_validator(mode="after")
    def positive_interval(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("Slot end must be after its start")
        return self


class SlotBatchCreate(RegistrationDTO):
    slots: Annotated[tuple[SlotCreate, ...], Field(min_length=1, max_length=100)]

    @field_validator("slots")
    @classmethod
    def unique_intervals(cls, slots):
        intervals = {(s.starts_at, s.ends_at) for s in slots}
        if len(intervals) != len(slots):
            raise ValueError("Duplicate slot interval")
        return slots


class RegistrationCreate(RegistrationDTO):
    project_id: PositiveId
    slot_id: PositiveId | None = None


class RegistrationCancel(RegistrationDTO):
    expected_version: PositiveId
    reason: Annotated[str, Field(min_length=1, max_length=1000)]

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("NUL is not allowed in a reason")
            return value.strip()
        return value


class RegistrationMove(RegistrationCancel):
    target_exam_id: PositiveId
    target_slot_id: PositiveId | None = None


class SlotRead(RegistrationDTO):
    id: int
    workspace_id: int
    exam_id: int
    starts_at: datetime
    ends_at: datetime
    is_available: bool


class RegistrationRead(RegistrationDTO):
    id: int
    workspace_id: int
    exam_id: int
    project_id: int
    project_type_id_at_registration: int
    slot_id: int | None
    status: RegistrationStatus
    version: int
    created_source: RegistrationSource
    created_by: int
    created_at: datetime
    updated_by: int
    updated_at: datetime
    started_at: datetime | None


class RegistrationMoveRead(RegistrationDTO):
    source: RegistrationRead
    target: RegistrationRead


class EventRead(RegistrationDTO):
    id: int
    workspace_id: int
    exam_id: int
    registration_id: int
    version: int
    action: EventAction
    source: RegistrationSource
    actor_id: int
    occurred_at: datetime
    reason: str | None
    from_slot_id: int | None
    to_slot_id: int | None
    related_registration_id: int | None
    transfer_id: UUID | None


class RegistrationListRead(RegistrationDTO):
    items: list[RegistrationRead]
    limit: int
    offset: int
    has_more: bool


class SlotListRead(RegistrationDTO):
    items: list[SlotRead]
    limit: int
    offset: int
    has_more: bool


class EventListRead(RegistrationDTO):
    items: list[EventRead]
    limit: int
    offset: int
    has_more: bool


class RegistrationAttemptBinding(RegistrationDTO):
    model_config = ConfigDict(frozen=True, extra="forbid")
    registration_id: int
    workspace_id: int
    exam_id: int
    project_id: int
    project_type_id: int
    started_at: datetime
