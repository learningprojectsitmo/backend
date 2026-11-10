from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

AssessmentKind = Literal["product", "technical_integration", "research"]


class RubricLevelRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: int
    description: str


class RubricCriterionRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    description: str
    levels: tuple[RubricLevelRead, ...]


class RubricRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    assessment_kind: AssessmentKind
    name: str
    version: int
    max_raw_score: int
    criteria: tuple[RubricCriterionRead, ...]
