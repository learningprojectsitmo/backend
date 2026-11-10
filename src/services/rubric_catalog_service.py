from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, field_validator

from src.core.exceptions import NotFoundError
from src.schema.rubric import AssessmentKind, RubricCriterionRead, RubricLevelRead, RubricRead

NonBlank = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]
SCORES = tuple(range(1, 6))


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
    def validate_scores(cls, value: dict[str, str]) -> dict[str, str]:
        if set(value) != {str(score) for score in SCORES}:
            raise ValueError("Each criterion must have exactly levels 1 through 5")
        return value


class _SourceRubric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: NonBlank
    key: AssessmentKind
    name: NonBlank
    criteria: Annotated[list[_SourceCriterion], Field(min_length=5, max_length=5)]


@lru_cache(maxsize=1)
def load_catalog() -> tuple[RubricRead, ...]:
    """Load the fixed v1 resource once; all cached objects are deeply immutable."""
    raw = files("src.data.assessment").joinpath("rubrics.v1.json").read_text(encoding="utf-8")
    source = TypeAdapter(list[_SourceRubric]).validate_json(raw)
    kinds: dict[AssessmentKind, str] = {"product": "P", "technical_integration": "T", "research": "R"}
    if len(source) != len(kinds) or {r.key for r in source} != set(kinds):
        raise ValueError("Catalog must contain each of the three assessment categories exactly once")
    by_kind = {r.key: r for r in source}
    result = []
    for kind, prefix in kinds.items():
        rubric = by_kind[kind]
        if [c.id for c in rubric.criteria] != [f"{prefix}{score}" for score in SCORES]:
            raise ValueError("Criterion codes must match the category and order 1 through 5")
        criteria = tuple(
            RubricCriterionRead(
                code=c.id,
                name=c.name,
                description=c.description,
                levels=tuple(RubricLevelRead(score=score, description=c.levels[str(score)]) for score in SCORES),
            )
            for c in rubric.criteria
        )
        result.append(
            RubricRead(
                assessment_kind=kind,
                name=rubric.name,
                version=1,
                max_raw_score=sum(max(level.score for level in c.levels) for c in criteria),
                criteria=criteria,
            )
        )
    return tuple(result)


class RubricCatalogService:
    def list_rubrics(self) -> tuple[RubricRead, ...]:
        return load_catalog()

    def get_rubric(self, assessment_kind: str, version: int) -> RubricRead:
        for rubric in load_catalog():
            if rubric.assessment_kind == assessment_kind and rubric.version == version:
                return rubric
        raise NotFoundError("Rubric version not found")
