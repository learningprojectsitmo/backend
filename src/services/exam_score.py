from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Final, Literal

ScoreRole = Literal["teacher", "manager", "member"]

SCORE_ROLES: Final[tuple[ScoreRole, ...]] = ("teacher", "manager", "member")
PERCENT_TOTAL: Final = 100
_CENTS: Final = 100


class ExamScoreError(ValueError):
    """Base class for invalid score calculation input."""


@dataclass(frozen=True)
class ScoreWeights:
    teacher: int
    manager: int
    member: int

    def __post_init__(self) -> None:
        values = (self.teacher, self.manager, self.member)
        if any(isinstance(v, bool) or not isinstance(v, int) for v in values):
            raise ExamScoreError("Weights must be integers")
        if any(v < 0 or v > PERCENT_TOTAL for v in values):
            raise ExamScoreError("Each weight must be between 0 and 100")
        if sum(values) != PERCENT_TOTAL:
            raise ExamScoreError("Weights must sum to 100")

    def of(self, role: ScoreRole) -> int:
        return {"teacher": self.teacher, "manager": self.manager, "member": self.member}[role]


@dataclass(frozen=True)
class SheetScore:
    """Submitted assessment sheet: the assessor's role and the sum of its criteria."""

    role: ScoreRole
    total: Decimal | int


@dataclass(frozen=True)
class RoleScore:
    role: ScoreRole
    weight: int
    sheets_count: int
    average: Decimal | None
    counted: bool


@dataclass(frozen=True)
class ExamScoreResult:
    score: Decimal | None
    normalized: Decimal | None
    roles: tuple[RoleScore, ...]
    used_weight: int
    no_calculation: bool


def _to_exact(value: object, *, name: str) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, int | Decimal):
        raise ExamScoreError(f"{name} must be an int or Decimal")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ExamScoreError(f"{name} must be finite")
    return Fraction(value)


def _round_half_up(value: Fraction) -> Decimal:
    """Round a non-negative exact fraction to 2 places, half up, exactly once."""
    scaled = (2 * value.numerator * _CENTS + value.denominator) // (2 * value.denominator)
    return Decimal(scaled).scaleb(-2)


def _validated_totals(sheets: Iterable[SheetScore], sheet_max: Fraction) -> dict[ScoreRole, list[Fraction]]:
    grouped: dict[ScoreRole, list[Fraction]] = {role: [] for role in SCORE_ROLES}
    for sheet in sheets:
        if sheet.role not in grouped:
            raise ExamScoreError(f"Unknown role: {sheet.role!r}")
        total = _to_exact(sheet.total, name="Sheet total")
        if total < 0:
            raise ExamScoreError("Sheet total must not be negative")
        if total > sheet_max:
            raise ExamScoreError("Sheet total must not exceed the sheet maximum")
        grouped[sheet.role].append(total)
    return grouped


def calculate_exam_score(
    *,
    sheets: Iterable[SheetScore],
    weights: ScoreWeights,
    sheet_max: Decimal | int,
    max_score: Decimal | int,
) -> ExamScoreResult:
    """Sheet sum -> role average -> weights over non-empty roles -> scale to the exam maximum.

    Stateless: a recalculation after a weights or maximum change is just another call.
    All arithmetic is exact (Fraction); rounding happens once, at the very end.
    """
    sheet_max_exact = _to_exact(sheet_max, name="Sheet maximum")
    max_score_exact = _to_exact(max_score, name="Exam maximum")
    if sheet_max_exact <= 0:
        raise ExamScoreError("Sheet maximum must be positive")
    if max_score_exact <= 0:
        raise ExamScoreError("Exam maximum must be positive")

    grouped = _validated_totals(sheets, sheet_max_exact)

    roles: list[RoleScore] = []
    weighted_sum = Fraction(0)
    used_weight = 0
    for role in SCORE_ROLES:
        totals = grouped[role]
        weight = weights.of(role)
        average = sum(totals, Fraction(0)) / len(totals) if totals else None
        counted = average is not None and weight > 0
        if counted and average is not None:
            weighted_sum += weight * average
            used_weight += weight
        roles.append(
            RoleScore(
                role=role,
                weight=weight,
                sheets_count=len(totals),
                average=_round_half_up(average) if average is not None else None,
                counted=counted,
            )
        )

    if used_weight == 0:
        return ExamScoreResult(score=None, normalized=None, roles=tuple(roles), used_weight=0, no_calculation=True)

    normalized = weighted_sum / used_weight
    return ExamScoreResult(
        score=_round_half_up(normalized * max_score_exact / sheet_max_exact),
        normalized=_round_half_up(normalized),
        roles=tuple(roles),
        used_weight=used_weight,
        no_calculation=False,
    )
