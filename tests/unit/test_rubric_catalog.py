from __future__ import annotations

import hashlib
import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

from src.core.exceptions import NotFoundError
from src.services import rubric_catalog_service as catalog


@pytest.fixture
def source():
    return json.loads(files("src.data.assessment").joinpath("rubrics.v1.json").read_text(encoding="utf-8"))


def test_catalog_matches_source_transcription(source):
    canonical = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == "39bb7db9c64617ade5a7524c5d9c3014844e56d529fe465bdb5388da575ad063"
    for actual, expected in zip(catalog.load_catalog(), source, strict=True):
        assert actual.assessment_kind == expected["key"]
        assert actual.name == expected["name"]
        assert actual.version == 1
        for criterion, original in zip(actual.criteria, expected["criteria"], strict=True):
            assert (criterion.code, criterion.name, criterion.description) == (
                original["id"],
                original["name"],
                original["description"],
            )
            assert {str(level.score): level.description for level in criterion.levels} == original["levels"]


def test_catalog_has_three_sets_fifteen_criteria_seventy_five_levels():
    rubrics = catalog.RubricCatalogService().list_rubrics()
    assert [r.assessment_kind for r in rubrics] == ["product", "technical_integration", "research"]
    assert len(rubrics) == 3
    assert sum(len(r.criteria) for r in rubrics) == 15
    assert sum(len(c.levels) for r in rubrics for c in r.criteria) == 75
    for rubric, prefix in zip(rubrics, ["P", "T", "R"], strict=True):
        assert [c.code for c in rubric.criteria] == [f"{prefix}{i}" for i in range(1, 6)]


def test_levels_are_sorted_one_to_five():
    for rubric in catalog.load_catalog():
        for criterion in rubric.criteria:
            assert [level.score for level in criterion.levels] == [1, 2, 3, 4, 5]
            assert all(level.description.strip() for level in criterion.levels)


def test_five_maximum_scores_equal_twenty_five():
    for rubric in catalog.load_catalog():
        maximums = [max(level.score for level in criterion.levels) for criterion in rubric.criteria]
        assert maximums == [5, 5, 5, 5, 5]
        assert sum(maximums) == rubric.max_raw_score == 25


@pytest.mark.parametrize(
    "defect",
    [
        "missing_set",
        "duplicate_set",
        "missing_criterion",
        "duplicate_code",
        "wrong_prefix",
        "missing_level",
        "wrong_score",
        "empty_description",
        "empty_name",
        "unknown_kind",
    ],
)
def test_malformed_catalog_is_rejected(source, tmp_path, monkeypatch, defect):
    if defect == "missing_set":
        source.pop()
    elif defect == "duplicate_set":
        source[1] = source[0]
    elif defect == "missing_criterion":
        source[0]["criteria"].pop()
    elif defect == "duplicate_code":
        source[0]["criteria"][1]["id"] = "P1"
    elif defect == "wrong_prefix":
        source[0]["criteria"][0]["id"] = "R1"
    elif defect == "missing_level":
        source[0]["criteria"][0]["levels"].pop("1")
    elif defect == "wrong_score":
        levels = source[0]["criteria"][0]["levels"]
        levels["0"] = levels.pop("1")
    elif defect == "empty_description":
        source[0]["criteria"][0]["levels"]["1"] = "   "
    elif defect == "empty_name":
        source[0]["criteria"][0]["name"] = ""
    else:
        source[0]["key"] = "other"
    (tmp_path / "rubrics.v1.json").write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(catalog, "files", lambda _package: tmp_path)
    catalog.load_catalog.cache_clear()
    try:
        with pytest.raises(ValueError):
            catalog.load_catalog()
    finally:
        catalog.load_catalog.cache_clear()


def test_cached_catalog_cannot_be_mutated():
    rubric = catalog.load_catalog()[0]
    with pytest.raises(ValidationError):
        rubric.name = "changed"
    with pytest.raises(ValidationError):
        rubric.criteria[0].name = "changed"
    with pytest.raises(ValidationError):
        rubric.criteria[0].levels[0].description = "changed"
    with pytest.raises(TypeError):
        rubric.criteria[0].levels[0] = rubric.criteria[0].levels[-1]
    dumped = rubric.model_dump(mode="json")
    dumped["criteria"][0]["levels"][0]["description"] = "changed"
    assert catalog.RubricCatalogService().get_rubric("product", 1).criteria[0].levels[0].description != "changed"


@pytest.mark.parametrize(("kind", "version"), [("unknown", 1), ("../research", 1), ("product", 2), ("research", 0)])
def test_unknown_kind_or_version_is_not_found(kind, version):
    with pytest.raises(NotFoundError):
        catalog.RubricCatalogService().get_rubric(kind, version)
