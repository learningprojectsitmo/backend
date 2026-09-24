from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RequirementGroup(BaseModel):
    """Группа требований ТЗ (для ФТ — роль/модуль, для НФТ — категория)"""

    name: str
    requirements: list[str] = []


class SpecificationUpdate(BaseModel):
    """Схема обновления технического задания проекта"""

    goal: str | None = None
    tasks: list[str] | None = None
    functional_requirements: list[RequirementGroup] | None = None
    non_functional_requirements: list[RequirementGroup] | None = None
    acceptance_criteria: list[str] | None = None


class SpecificationFull(BaseModel):
    """Полная схема технического задания проекта"""

    id: int
    project_id: int
    goal: str | None = None
    tasks: list[str] = []
    functional_requirements: list[RequirementGroup] = []
    non_functional_requirements: list[RequirementGroup] = []
    acceptance_criteria: list[str] = []
    status: str = "draft"
    rejection_comment: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SpecificationCommentCreate(BaseModel):
    """Схема создания комментария к техническому заданию"""

    text: str


class SpecificationCommentUpdate(BaseModel):
    """Схема обновления комментария к техническому заданию"""

    text: str


class SpecificationCommentAuthor(BaseModel):
    """Краткая информация об авторе комментария"""

    id: int
    username: str


class SpecificationCommentResponse(BaseModel):
    """Полная схема комментария к техническому заданию"""

    id: int
    specification_id: int
    author: SpecificationCommentAuthor
    text: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
