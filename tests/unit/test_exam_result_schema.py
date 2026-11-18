from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.schema.exam_result import ResultAccept, ResultManual, ResultPublish


def test_first_accept_needs_no_reason():
    data = ResultAccept(expected_version=0)
    assert data.reason is None


def test_repeated_accept_requires_reason():
    with pytest.raises(ValidationError):
        ResultAccept(expected_version=1)
    with pytest.raises(ValidationError):
        ResultAccept(expected_version=2, reason="   ")


def test_reason_is_trimmed_and_limited():
    assert ResultAccept(expected_version=1, reason="  new weights ").reason == "new weights"
    with pytest.raises(ValidationError):
        ResultAccept(expected_version=1, reason="x" * 1001)
    with pytest.raises(ValidationError):
        ResultAccept(expected_version=1, reason="bad\x00")


@pytest.mark.parametrize("value", [-1, True, "1", 1.0, 2**31])
def test_accept_expected_version_is_strict(value):
    with pytest.raises(ValidationError):
        ResultAccept(expected_version=value)


@pytest.mark.parametrize("value", [0, -1, True, "1", 2**31])
def test_publish_expected_version_is_strict(value):
    with pytest.raises(ValidationError):
        ResultPublish(expected_version=value)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        ResultAccept(expected_version=0, score=5)
    with pytest.raises(ValidationError):
        ResultPublish(expected_version=1, visible=True)


def manual(**overrides):
    body = {"expected_version": 0, "final_score": "20", "reason": "oral defense"} | overrides
    return ResultManual(**body)


def test_manual_accepts_numbers_and_strings_and_quantizes():
    assert manual(final_score=12.5).final_score == Decimal("12.50")
    assert manual(final_score="0").final_score == Decimal("0.00")
    assert manual(final_score=10).final_score == Decimal("10.00")


@pytest.mark.parametrize("value", [-0.01, "-1", True, "NaN", "Infinity", "12.345", "abc", None, 10**12])
def test_manual_rejects_bad_scores(value):
    with pytest.raises(ValidationError):
        manual(final_score=value)


@pytest.mark.parametrize("reason", [None, "", "   ", "x" * 1001, "bad\x00"])
def test_manual_reason_is_always_required(reason):
    with pytest.raises(ValidationError):
        manual(reason=reason)
    with pytest.raises(ValidationError):
        manual(expected_version=0, reason=reason)


def test_manual_reason_is_trimmed():
    assert manual(reason="  ok  ").reason == "ok"


@pytest.mark.parametrize("value", [-1, True, "1", 1.0, 2**31])
def test_manual_expected_version_is_strict(value):
    with pytest.raises(ValidationError):
        manual(expected_version=value)


@pytest.mark.parametrize("extra", ["kind", "calculated_score", "weights", "max_score"])
def test_manual_rejects_unknown_fields(extra):
    with pytest.raises(ValidationError):
        manual(**{extra: 1})
