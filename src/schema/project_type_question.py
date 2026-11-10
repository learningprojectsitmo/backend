from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

TemplateCode = Literal["product", "technical_integration", "research"]
QuestionText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1000)]
QuestionDescription = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000)
]
LevelDescription = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=4000)]
QuestionId = Annotated[int, Field(strict=True, ge=1)]


class QuestionLevel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", from_attributes=True)

    score: Annotated[int, Field(strict=True, ge=1, le=5)]
    description: LevelDescription


class _QuestionContent(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    text: QuestionText
    description: QuestionDescription | None = None
    levels: Annotated[tuple[QuestionLevel, ...], Field(min_length=5, max_length=5)]

    @field_validator("levels")
    @classmethod
    def complete_scale(cls, levels: tuple[QuestionLevel, ...]) -> tuple[QuestionLevel, ...]:
        if {level.score for level in levels} != {1, 2, 3, 4, 5}:
            raise ValueError("Each question must have distinct levels 1 through 5")
        return tuple(sorted(levels, key=lambda level: level.score))


class QuestionWrite(_QuestionContent):
    id: QuestionId | None = None


class QuestionListReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[QuestionWrite]

    @field_validator("questions")
    @classmethod
    def unique_ids(cls, questions: list[QuestionWrite]) -> list[QuestionWrite]:
        ids = [q.id for q in questions if q.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Question IDs must be unique")
        return questions


class QuestionRead(_QuestionContent):
    id: int
    position: int


class ProjectTypeQuestionsRead(BaseModel):
    project_type_id: int
    questions: list[QuestionRead]
    min_score: Literal[1] = 1
    max_score: Literal[5] = 5


class TemplateQuestionRead(_QuestionContent):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str


class QuestionTemplateRead(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: TemplateCode
    name: str
    questions: tuple[TemplateQuestionRead, ...]


class TemplateApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_code: TemplateCode
