from __future__ import annotations

import hashlib
import json
from importlib.resources import files

import pytest
from pydantic import ValidationError

from src.core.exceptions import NotFoundError
from src.services import question_template_service as templates


def source():
    return json.loads(files("src.data.assessment").joinpath("question_templates.json").read_text(encoding="utf-8"))


def test_templates_match_source_and_are_three_fifteen_seventy_five():
    original = source()
    canonical = json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == "39bb7db9c64617ade5a7524c5d9c3014844e56d529fe465bdb5388da575ad063"
    result = templates.QuestionTemplateService().list_templates()
    assert [x.code for x in result] == ["product", "technical_integration", "research"]
    assert sum(len(t.questions) for t in result) == 15
    assert sum(len(q.levels) for t in result for q in t.questions) == 75
    for actual, expected, prefix in zip(result, original, ["P", "T", "R"], strict=True):
        assert actual.name == expected["name"]
        assert [q.code for q in actual.questions] == [f"{prefix}{n}" for n in range(1, 6)]
        assert sum(max(level.score for level in q.levels) for q in actual.questions) == 25
        for q, c in zip(actual.questions, expected["criteria"], strict=True):
            assert (q.text, q.description) == (c["name"], c["description"])
            assert [level.score for level in q.levels] == [1, 2, 3, 4, 5]
            assert {str(level.score): level.description for level in q.levels} == c["levels"]


@pytest.mark.parametrize(
    "defect", ["missing_set", "missing_criterion", "duplicate_code", "missing_level", "blank_level"]
)
def test_malformed_resource_is_rejected(defect, tmp_path, monkeypatch):
    data = source()
    if defect == "missing_set":
        data.pop()
    elif defect == "missing_criterion":
        data[0]["criteria"].pop()
    elif defect == "duplicate_code":
        data[0]["criteria"][1]["id"] = "P1"
    elif defect == "missing_level":
        data[0]["criteria"][0]["levels"].pop("1")
    else:
        data[0]["criteria"][0]["levels"]["1"] = " "
    (tmp_path / "question_templates.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(templates, "files", lambda _package: tmp_path)
    templates.load_question_templates.cache_clear()
    try:
        with pytest.raises(ValueError):
            templates.load_question_templates()
    finally:
        templates.load_question_templates.cache_clear()


def test_cached_template_is_deeply_immutable():
    item = templates.load_question_templates()[0]
    for obj, key in [(item, "name"), (item.questions[0], "text"), (item.questions[0].levels[0], "description")]:
        with pytest.raises(ValidationError):
            setattr(obj, key, "changed")
    with pytest.raises(TypeError):
        item.questions[0] = item.questions[-1]
    dump = item.model_dump(mode="json")
    dump["questions"][0]["levels"][0]["description"] = "changed"
    assert templates.load_question_templates()[0].questions[0].levels[0].description != "changed"


def test_unknown_template_is_not_found():
    with pytest.raises(NotFoundError):
        templates.QuestionTemplateService().get_template("../unknown")
