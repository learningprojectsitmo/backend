from __future__ import annotations

from decimal import Decimal

import pytest

from src.services.exam_score import (
    ExamScoreError,
    ExamScoreResult,
    ScoreRole,
    ScoreWeights,
    SheetScore,
    calculate_exam_score,
)

W = ScoreWeights(teacher=60, manager=30, member=10)
D = Decimal


def sheet(role: ScoreRole, total: Decimal | int) -> SheetScore:
    return SheetScore(role=role, total=total)


def calc(
    sheets: list[SheetScore],
    weights: ScoreWeights = W,
    sheet_max: Decimal | int = 25,
    max_score: Decimal | int = 25,
) -> ExamScoreResult:
    return calculate_exam_score(sheets=sheets, weights=weights, sheet_max=sheet_max, max_score=max_score)


ACCEPTANCE = [sheet("teacher", 25), sheet("teacher", 15), sheet("manager", 15), sheet("member", 25)]


def role_of(result: ExamScoreResult, role: str):
    return next(r for r in result.roles if r.role == role)


def test_acceptance_example_gives_19_of_25() -> None:
    result = calc(ACCEPTANCE)
    assert result.score == D("19.00")
    assert result.normalized == D("19.00")
    assert result.used_weight == 100
    assert result.no_calculation is False
    assert [r.average for r in result.roles] == [D("20.00"), D("15.00"), D("25.00")]
    assert [r.sheets_count for r in result.roles] == [2, 1, 1]
    assert all(r.counted for r in result.roles)


def test_only_teacher_votes_are_not_underweighted() -> None:
    result = calc([sheet("teacher", 20)])
    assert result.score == D("20.00")
    assert result.used_weight == 60
    assert role_of(result, "manager").average is None
    assert role_of(result, "manager").counted is False


def test_scaling_to_max_100_gives_76() -> None:
    assert calc(ACCEPTANCE, max_score=D("100.00")).score == D("76.00")


def test_empty_group_is_not_zero() -> None:
    with_empty = calc([sheet("teacher", 20), sheet("member", 10)])
    # (60*20 + 10*10) / 70, not a zero manager group
    assert with_empty.normalized == D("18.57")
    assert role_of(with_empty, "manager").average is None


def test_no_sheets_means_no_calculation() -> None:
    result = calc([])
    assert result.score is None
    assert result.normalized is None
    assert result.no_calculation is True
    assert result.used_weight == 0
    assert all(r.average is None and not r.counted for r in result.roles)


def test_zero_weight_only_voting_role_means_no_calculation() -> None:
    result = calc([sheet("member", 20)], weights=ScoreWeights(teacher=70, manager=30, member=0))
    assert result.no_calculation is True
    assert result.score is None
    member = role_of(result, "member")
    assert member.average == D("20.00")
    assert member.counted is False


def test_zero_weight_role_is_ignored_when_others_vote() -> None:
    result = calc([sheet("teacher", 20), sheet("member", 5)], weights=ScoreWeights(teacher=70, manager=30, member=0))
    assert result.score == D("20.00")
    assert result.used_weight == 70


def test_number_of_assessors_does_not_raise_role_weight() -> None:
    one = calc([sheet("teacher", 20), sheet("manager", 10)])
    many = calc([sheet("teacher", 20)] * 5 + [sheet("manager", 10)])
    assert one.score == many.score == D("16.67")
    assert role_of(many, "teacher").sheets_count == 5


def test_changing_weights_recalculates() -> None:
    assert calc(ACCEPTANCE).score == D("19.00")
    assert calc(ACCEPTANCE, weights=ScoreWeights(teacher=50, manager=50, member=0)).score == D("17.50")


def test_changing_max_score_recalculates() -> None:
    assert calc(ACCEPTANCE, max_score=D("50.00")).score == D("38.00")
    assert calc(ACCEPTANCE, max_score=D("10")).score == D("7.60")


def test_sheet_max_is_five_times_question_count() -> None:
    # 3 questions -> sheet max 15; 12/15 = 80% -> 80 of 100
    result = calc([sheet("teacher", 12)], sheet_max=15, max_score=100)
    assert result.score == D("80.00")
    assert result.normalized == D("12.00")
    # 7 questions -> sheet max 35
    assert calc([sheet("teacher", 28)], sheet_max=35, max_score=25).score == D("20.00")


def test_rounding_is_half_up_not_bankers() -> None:
    # 0.125 -> 0.13 (banker's would give 0.12); 0.135 -> 0.14 (both agree)
    assert calc([sheet("teacher", D("0.125"))]).score == D("0.13")
    assert calc([sheet("teacher", D("0.135"))]).score == D("0.14")
    assert calc([sheet("teacher", D("2.5"))], sheet_max=25, max_score=D("0.1")).score == D("0.01")


def test_no_double_rounding() -> None:
    # exact 1.0049 rounds to 1.00; rounding the sheet scale first (1.00 -> 1.00) is the same,
    # but exact 0.0449 * 10 = 0.449 must give 0.45 only if no earlier rounding to 0.04
    result = calc([sheet("teacher", D("0.0449"))], sheet_max=25, max_score=250)
    assert result.score == D("0.45")
    # average shown as 0.04 (display) while the score uses the exact value
    assert role_of(result, "teacher").average == D("0.04")


def test_decimal_precision_without_float_artifacts() -> None:
    result = calc([sheet("teacher", D("0.1")), sheet("teacher", D("0.2"))], sheet_max=1, max_score=1)
    assert result.score == D("0.15")
    thirds = calc([sheet("teacher", 1), sheet("teacher", 1), sheet("teacher", 2)], sheet_max=5, max_score=5)
    assert thirds.score == D("1.33")
    assert isinstance(thirds.score, Decimal)


def test_result_has_two_decimal_places() -> None:
    assert str(calc(ACCEPTANCE).score) == "19.00"
    assert str(calc(ACCEPTANCE, max_score=D("100.00")).score) == "76.00"


@pytest.mark.parametrize(
    "bad_sheet",
    [
        SheetScore(role="teacher", total=-1),
        SheetScore(role="teacher", total=26),
        SheetScore(role="teacher", total=1.5),  # type: ignore[arg-type]
        SheetScore(role="teacher", total="20"),  # type: ignore[arg-type]
        SheetScore(role="teacher", total=True),
        SheetScore(role="teacher", total=D("NaN")),
        SheetScore(role="teacher", total=D("Infinity")),
        SheetScore(role="admin", total=10),  # type: ignore[arg-type]
    ],
)
def test_invalid_sheet_is_rejected(bad_sheet: SheetScore) -> None:
    with pytest.raises(ExamScoreError):
        calc([bad_sheet])


@pytest.mark.parametrize(
    ("sheet_max", "max_score"),
    [(0, 25), (-5, 25), (25, 0), (25, D("-1")), (25.0, 25), (25, D("NaN")), (True, 25)],
)
def test_invalid_maximums_are_rejected(sheet_max: object, max_score: object) -> None:
    with pytest.raises(ExamScoreError):
        calc([sheet("teacher", 10)], sheet_max=sheet_max, max_score=max_score)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "args",
    [(60, 30, 20), (60, 30, 5), (-10, 60, 50), (101, 0, -1), (60.0, 30, 10), (True, 99, 0)],
)
def test_invalid_weights_are_rejected(args: tuple) -> None:
    with pytest.raises(ExamScoreError):
        ScoreWeights(*args)


def test_error_is_value_error() -> None:
    assert issubclass(ExamScoreError, ValueError)
