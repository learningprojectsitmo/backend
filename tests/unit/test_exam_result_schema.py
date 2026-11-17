from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schema.exam_result import ResultAccept, ResultPublish


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
