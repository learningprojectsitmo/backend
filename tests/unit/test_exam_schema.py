from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.schema.exam import ExamConfiguration, ExamCreate, ExamSettingsReplace


def create_payload():
    return {"title": "Защита", "starts_at": "2026-11-30T10:00:00+03:00", "project_type_ids": [42]}


def complete_configuration():
    return dict(
        title="Защита",
        description=None,
        starts_at="2026-11-30T07:00:00Z",
        connection_url=None,
        project_type_ids=[42],
        registration_opens_at=None,
        registration_closes_at=None,
        weights=dict(teacher=60, manager=30, member=10),
        max_score="25.00",
        presentation_minutes=7,
        questions_minutes=7,
        transition_minutes=1,
        assessment_window_minutes=3,
    )


def test_create_expands_confirmed_defaults():
    c = ExamCreate.model_validate(create_payload()).to_configuration()
    assert c.weights.model_dump() == dict(teacher=60, manager=30, member=10)
    assert c.max_score == Decimal("25.00")
    assert (c.presentation_minutes, c.questions_minutes, c.transition_minutes, c.assessment_window_minutes) == (
        7,
        7,
        1,
        3,
    )
    assert c.starts_at.isoformat() == "2026-11-30T07:00:00+00:00"
    assert c.model_dump(mode="json")["max_score"] == "25.00"


@pytest.mark.parametrize(
    "field,value",
    [("max_score", x) for x in [0, -1, True, "NaN", "Infinity", "25.001"]]
    + [("presentation_minutes", x) for x in [0, 1441, True, "7", 7.5]]
    + [
        ("assessment_window_minutes", 0),
        ("questions_minutes", -1),
        ("transition_minutes", 1441),
        ("title", " "),
        ("connection_url", "javascript:alert(1)"),
        ("starts_at", "2026-11-30T07:00:00"),
        ("project_type_ids", [42, 42]),
        ("project_type_ids", [True]),
        ("unknown", 1),
    ],
)
def test_invalid_configuration(field, value):
    data = complete_configuration()
    data[field] = value
    with pytest.raises(ValidationError):
        ExamConfiguration.model_validate(data)


@pytest.mark.parametrize("field", list(complete_configuration()))
def test_full_replace_requires_every_field(field):
    data = complete_configuration()
    del data[field]
    with pytest.raises(ValidationError):
        ExamConfiguration.model_validate(data)


def test_weights_and_registration_order():
    data = complete_configuration()
    data["weights"]["teacher"] = 59
    with pytest.raises(ValidationError):
        ExamConfiguration.model_validate(data)
    data["weights"] = dict(teacher=0, manager=100, member=0)
    assert ExamConfiguration.model_validate(data).weights.manager == 100
    data["registration_opens_at"] = "2026-12-01T00:00:00Z"
    with pytest.raises(ValidationError):
        ExamConfiguration.model_validate(data)


@pytest.mark.parametrize("score", ["12.50", 12.5])
def test_decimal_input(score):
    data = complete_configuration()
    data["max_score"] = score
    assert ExamConfiguration.model_validate(data).max_score == Decimal("12.50")


def test_replace_requires_reason_and_strict_version():
    for version, reason in [(True, "change"), (1, " "), ("1", "change")]:
        with pytest.raises(ValidationError):
            ExamSettingsReplace(expected_version=version, reason=reason, configuration=complete_configuration())
