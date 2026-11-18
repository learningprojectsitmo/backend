from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StrictInt, field_validator, model_validator

from src.schema.exam import ExamDTO, ExamWeights

PG_INTEGER_MAX = 2**31 - 1
ResultKind = Literal["calculated", "manual"]
ResultRole = Literal["teacher", "manager", "member"]
Reason = Annotated[str, Field(min_length=1, max_length=1000)]


def _clean_reason(value: object) -> object:
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("NUL is not allowed in a reason")
        return value.strip()
    return value


class ResultAccept(ExamDTO):
    """Accept a new result edition. expected_version is the latest edition the client saw (0 = none yet)."""

    expected_version: Annotated[StrictInt, Field(ge=0, le=PG_INTEGER_MAX)]
    reason: Reason | None = None

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value: object) -> object:
        return _clean_reason(value)

    @model_validator(mode="after")
    def reason_for_repeat(self) -> Self:
        if self.expected_version >= 1 and self.reason is None:
            raise ValueError("reason is required for a repeated decision")
        return self


class ResultManual(ExamDTO):
    """Manual (official) result decided by the teacher. The reason is always required."""

    expected_version: Annotated[StrictInt, Field(ge=0, le=PG_INTEGER_MAX)]
    final_score: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
    reason: Reason

    @field_validator("final_score", mode="before")
    @classmethod
    def score_input(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Boolean is not a score")  # noqa: TRY004 -- Pydantic requires ValueError for 422
        return value

    @field_validator("final_score")
    @classmethod
    def score_scale(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value: object) -> object:
        return _clean_reason(value)


class ResultPublish(ExamDTO):
    expected_version: Annotated[StrictInt, Field(ge=1, le=PG_INTEGER_MAX)]


class ResultSheetCounts(ExamDTO):
    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)
    teacher: int
    manager: int
    member: int


class ResultSnapshot(ExamDTO):
    """Parameters the score was calculated with."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)
    settings_version: int
    weights: ExamWeights
    max_score: Decimal
    sheet_max: int
    sheets: ResultSheetCounts
    used_weight: int


class ResultRoleRead(ExamDTO):
    role: ResultRole
    weight: int
    sheets_count: int
    average: Decimal | None
    counted: bool


class ResultEditionRead(ExamDTO):
    id: int
    workspace_id: int
    exam_id: int
    attempt_id: int
    version: int
    kind: ResultKind
    calculated_score: Decimal | None
    final_score: Decimal
    snapshot: ResultSnapshot
    reason: str | None
    decided_by: int
    decided_at: datetime
    published_at: datetime | None
    published_by: int | None


class ResultPreliminaryRead(ExamDTO):
    """Fresh calculation over the current sheets and the current settings; never stored."""

    score: Decimal | None
    no_calculation: bool
    snapshot: ResultSnapshot
    roles: list[ResultRoleRead]


class ResultRead(ExamDTO):
    workspace_id: int
    exam_id: int
    attempt_id: int
    edition: ResultEditionRead | None
    preliminary: ResultPreliminaryRead | None
    outdated: bool


class ResultEditionListRead(ExamDTO):
    items: list[ResultEditionRead]


ResultRegistryState = Literal["undecided", "accepted", "published"]


class ResultRegistryCurrentRead(ExamDTO):
    """The latest accepted edition of an attempt, flattened for the registry."""

    version: int
    kind: ResultKind
    calculated_score: Decimal | None
    final_score: Decimal
    max_score: Decimal
    reason: str | None
    decided_by_id: int
    decided_by_name: str
    decided_at: datetime
    published_at: datetime | None
    published_by_id: int | None


class ResultRegistryItemRead(ExamDTO):
    attempt_id: int
    registration_id: int
    project_id: int
    project_name: str
    project_type_id: int
    finished_at: datetime
    state: ResultRegistryState
    editions_count: int
    current: ResultRegistryCurrentRead | None
    previous_final_score: Decimal | None
    settings_outdated: bool


class ResultRegistryRead(ExamDTO):
    items: list[ResultRegistryItemRead]
    limit: int
    offset: int
    has_more: bool
