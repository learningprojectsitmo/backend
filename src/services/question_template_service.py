from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, field_validator

from src.core.exceptions import NotFoundError
from src.schema.project_type_question import QuestionLevel, QuestionTemplateRead, TemplateCode, TemplateQuestionRead

NonBlank = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]


class _SourceCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: NonBlank
    name: NonBlank
    description: NonBlank
    levels: dict[str, NonBlank]
    weight: None
    target_scope: Literal["team"]

    @field_validator("levels")
    @classmethod
    def complete_scale(cls, levels: dict[str, str]) -> dict[str, str]:
        if set(levels) != {"1", "2", "3", "4", "5"}:
            raise ValueError("Template scale must contain exactly levels 1 through 5")
        return levels


class _SourceTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: NonBlank
    key: TemplateCode
    name: NonBlank
    criteria: Annotated[list[_SourceCriterion], Field(min_length=5, max_length=5)]


@lru_cache(maxsize=1)
def load_question_templates() -> tuple[QuestionTemplateRead, ...]:
    raw = files("src.data.assessment").joinpath("question_templates.json").read_text(encoding="utf-8")
    source = TypeAdapter(list[_SourceTemplate]).validate_json(raw)
    kinds: dict[TemplateCode, str] = {"product": "P", "technical_integration": "T", "research": "R"}
    if len(source) != len(kinds) or {t.key for t in source} != set(kinds):
        raise ValueError("Each of the three templates must appear exactly once")
    by_code = {t.key: t for t in source}
    result = []
    for code, prefix in kinds.items():
        template = by_code[code]
        if [c.id for c in template.criteria] != [f"{prefix}{n}" for n in range(1, 6)]:
            raise ValueError("Template criterion codes must match their set and order")
        result.append(
            QuestionTemplateRead(
                code=code,
                name=template.name,
                questions=tuple(
                    TemplateQuestionRead(
                        code=c.id,
                        text=c.name,
                        description=c.description,
                        levels=tuple(QuestionLevel(score=n, description=c.levels[str(n)]) for n in range(1, 6)),
                    )
                    for c in template.criteria
                ),
            )
        )
    return tuple(result)


class QuestionTemplateService:
    def list_templates(self) -> tuple[QuestionTemplateRead, ...]:
        return load_question_templates()

    def get_template(self, code: str) -> QuestionTemplateRead:
        for template in load_question_templates():
            if template.code == code:
                return template
        raise NotFoundError("Question template not found")
