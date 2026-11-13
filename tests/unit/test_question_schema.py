from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from src.schema.project_type_question import QuestionListReplace, QuestionWrite


def payload():
    return {
        "text": " Обоснованность решения ",
        "description": " Предмет оценки ",
        "levels": [
            {"score": 5, "description": "Полностью обосновано"},
            {"score": 4, "description": "Почти всё обосновано"},
            {"score": 3, "description": "Основное объяснено"},
            {"score": 2, "description": "Есть фрагменты"},
            {"score": 1, "description": "Обоснования нет"},
        ],
    }


def test_custom_question_normalizes_text_and_levels():
    q = QuestionWrite.model_validate(payload())
    assert (q.id, q.text, q.description) == (None, "Обоснованность решения", "Предмет оценки")
    assert [level.score for level in q.levels] == [1, 2, 3, 4, 5]
    assert q.levels[0].description == "Обоснования нет"
    assert QuestionListReplace(questions=[]).questions == []


@pytest.mark.parametrize("score", [0, 6, True, "1", 1.0])
def test_invalid_level_score_is_rejected(score):
    data = payload()
    data["levels"][0]["score"] = score
    with pytest.raises(ValidationError):
        QuestionWrite.model_validate(data)


@pytest.mark.parametrize(
    "defect",
    [
        "four_levels",
        "six_levels",
        "duplicate_score",
        "blank_text",
        "long_text",
        "blank_description",
        "long_description",
        "blank_level",
        "long_level",
        "foreign_key",
        "version",
        "duplicate_id",
    ],
)
def test_malformed_question_list_is_rejected(defect):
    data = payload()
    if defect == "four_levels":
        data["levels"].pop()
    elif defect == "six_levels":
        data["levels"].append(deepcopy(data["levels"][0]))
    elif defect == "duplicate_score":
        data["levels"][0]["score"] = 4
    elif defect == "blank_text":
        data["text"] = " \t\n"
    elif defect == "long_text":
        data["text"] = "я" * 1001
    elif defect == "blank_description":
        data["description"] = "  "
    elif defect == "long_description":
        data["description"] = "я" * 2001
    elif defect == "blank_level":
        data["levels"][0]["description"] = "\t"
    elif defect == "long_level":
        data["levels"][0]["description"] = "я" * 4001
    elif defect == "foreign_key":
        data["project_type_id"] = 999
    elif defect == "version":
        data["version"] = 1
    else:
        data["id"] = 17
    questions = [data, deepcopy(data)] if defect == "duplicate_id" else [data]
    with pytest.raises(ValidationError):
        QuestionListReplace.model_validate({"questions": questions})


def test_bool_question_id_is_rejected():
    data = payload()
    data["id"] = True
    with pytest.raises(ValidationError):
        QuestionWrite.model_validate(data)
