from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictInt, field_validator, model_validator

PositiveId = Annotated[StrictInt, Field(ge=1)]
Minute = Annotated[StrictInt, Field(ge=0, le=1440)]
PositiveMinute = Annotated[StrictInt, Field(ge=1, le=1440)]


class ExamDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExamWeights(ExamDTO):
    teacher: Annotated[StrictInt, Field(ge=0, le=100)]
    manager: Annotated[StrictInt, Field(ge=0, le=100)]
    member: Annotated[StrictInt, Field(ge=0, le=100)]

    @model_validator(mode="after")
    def total(self) -> Self:
        if self.teacher + self.manager + self.member != 100:
            raise ValueError("Weights must sum to 100")
        return self


class ExamConfiguration(ExamDTO):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(min_length=1, max_length=5000)] | None
    starts_at: datetime
    connection_url: Annotated[HttpUrl, Field(max_length=2048)] | None
    project_type_ids: tuple[PositiveId, ...]
    registration_opens_at: datetime | None
    registration_closes_at: datetime | None
    weights: ExamWeights
    max_score: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
    presentation_minutes: PositiveMinute
    questions_minutes: Minute
    transition_minutes: Minute
    assessment_window_minutes: PositiveMinute

    @field_validator("title", "description", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("max_score", mode="before")
    @classmethod
    def decimal_input(cls, value):
        if isinstance(value, bool):
            raise ValueError("Boolean is not a score")
        return value

    @field_validator("max_score")
    @classmethod
    def decimal_scale(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))

    @field_validator("starts_at", "registration_opens_at", "registration_closes_at")
    @classmethod
    def utc_time(cls, value: datetime | None) -> datetime | None:
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Timezone is required")
            return value.astimezone(UTC)
        return value

    @field_validator("project_type_ids")
    @classmethod
    def unique_types(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Duplicate project type")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def registration_order(self) -> Self:
        a, b = self.registration_opens_at, self.registration_closes_at
        if (a and a > self.starts_at) or (b and b > self.starts_at) or (a and b and a >= b):
            raise ValueError("Invalid registration period")
        return self


class ExamCreate(ExamConfiguration):
    description: Annotated[str, Field(min_length=1, max_length=5000)] | None = None
    connection_url: Annotated[HttpUrl, Field(max_length=2048)] | None = None
    project_type_ids: tuple[PositiveId, ...] = ()
    registration_opens_at: datetime | None = None
    registration_closes_at: datetime | None = None
    weights: ExamWeights = Field(default_factory=lambda: ExamWeights(teacher=60, manager=30, member=10))
    max_score: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2, allow_inf_nan=False)] = Decimal("25.00")
    presentation_minutes: PositiveMinute = 7
    questions_minutes: Minute = 7
    transition_minutes: Minute = 1
    assessment_window_minutes: PositiveMinute = 3

    def to_configuration(self) -> ExamConfiguration:
        return ExamConfiguration.model_validate(self.model_dump())


class ExamSettingsReplace(ExamDTO):
    expected_version: PositiveId
    reason: Annotated[str, Field(min_length=1, max_length=1000)]
    configuration: ExamConfiguration

    @field_validator("reason", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class ExamPublish(ExamDTO):
    expected_version: PositiveId


class ExamRead(ExamDTO):
    id: int
    workspace_id: int
    status: Literal["draft", "published"]
    current_settings_version: int
    configuration: ExamConfiguration
    created_by: int
    created_at: datetime
    published_by: int | None
    published_at: datetime | None


class ExamSettingsRevisionRead(ExamDTO):
    exam_id: int
    version: int
    configuration: ExamConfiguration
    changed_by: int
    changed_at: datetime
    reason: str | None


class ExamListRead(ExamDTO):
    items: list[ExamRead]
    limit: int
    offset: int
    has_more: bool


class ExamSettingsHistoryRead(ExamDTO):
    items: list[ExamSettingsRevisionRead]
    limit: int
    offset: int
    has_more: bool


class AssessmentWindowSettings(ExamDTO):
    model_config = ConfigDict(extra="forbid", frozen=True)
    exam_id: int
    workspace_id: int
    project_type_id: int
    settings_version: int
    opened_at: datetime
    closes_at: datetime
