from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from datetime import datetime

T = TypeVar("T")


# Базовые схемы из base_schema.py
class ModelBaseInfo(BaseModel):
    """Базовая схема с информацией о модели"""

    id: int
    created_at: datetime
    updated_at: datetime


class FindBase(BaseModel):
    """Базовая схема для поиска"""

    ordering: str | None
    page: int | None
    page_size: int | str | None


class SearchOptions(FindBase):
    """Опции поиска"""

    total_count: int | None


class FindResult(BaseModel):
    """Результат поиска"""

    founds: list | None
    search_options: SearchOptions | None


class FindDateRange(BaseModel):
    """Поиск по диапазону дат"""

    created_at__lt: str
    created_at__lte: str
    created_at__gt: str
    created_at__gte: str


class Blank(BaseModel):
    """Пустая схема"""


# Общие схемы из schemas.py
class PaginatedResponse[T](BaseModel):
    """Общая схема пагинированного ответа"""

    items: list[T]
    total: int
    page: int
    limit: int
    total_pages: int


class DeleteResponse(BaseModel):
    """Схема ответа при удалении"""

    message: str
