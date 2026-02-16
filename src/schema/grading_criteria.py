from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GradingCriteriaBase(BaseModel):
    """Базовая схема критерия оценивания"""
    name: str = Field(..., min_length=1, max_length=100, description="Название критерия")
    description: str | None = Field(None, max_length=300, description="Описание критерия")
    max_score: int = Field(..., gt=0, le=100, description="Максимальный балл")
    weight: int = Field(default=1, gt=0, le=5, description="Вес критерия")
    order_index: int = Field(default=0, ge=0, description="Порядок отображения")


class GradingCriteriaCreate(GradingCriteriaBase):
    """Создание критерия оценивания"""
    project_type_id: int = Field(..., gt=0, description="ID типа проекта")


class GradingCriteriaUpdate(BaseModel):
    """Обновление критерия"""
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=300)
    max_score: int | None = Field(None, gt=0, le=100)
    weight: int | None = Field(None, gt=0, le=5)
    order_index: int | None = Field(None, ge=0)


class GradingCriteriaResponse(GradingCriteriaBase):
    """Ответ с критерием"""
    id: int
    project_type_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GradingCriteriaListResponse(BaseModel):
    """Список критериев с метаданными"""
    items: list[GradingCriteriaResponse]
    total: int
    project_type_id: int
    total_max_score: float = Field(description="Суммарный максимальный балл")
