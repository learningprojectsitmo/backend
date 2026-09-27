from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.model.wiki import WIKI_VISIBILITY_PRIVATE

# Ограничения продублированы в схеме, чтобы pydantic отсекал мусор до
# сервиса; фактическая очистка HTML — в src.util.html_sanitize.
MAX_TITLE_LENGTH = 200

WikiVisibility = Literal["public", "private"]


class WikiPageCreate(BaseModel):
    """Схема создания страницы вики"""

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    content: str = ""
    parent_id: int | None = None
    visibility: WikiVisibility = WIKI_VISIBILITY_PRIVATE
    position: int | None = None


class WikiPageUpdate(BaseModel):
    """Схема обновления страницы вики. Не переданные поля не меняются."""

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    content: str | None = None
    parent_id: int | None = None
    visibility: WikiVisibility | None = None
    position: int | None = None


class WikiPageAuthor(BaseModel):
    """Краткая информация об авторе страницы"""

    id: int
    username: str


class WikiPageFull(BaseModel):
    """Полная схема страницы вики"""

    id: int
    project_id: int
    parent_id: int | None = None
    title: str
    content: str
    visibility: str
    position: int
    author: WikiPageAuthor | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class WikiPageSummary(BaseModel):
    """Страница вики без содержимого — для сайдбара и списка"""

    id: int
    project_id: int
    parent_id: int | None = None
    title: str
    visibility: str
    position: int
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class WikiPageListResponse(BaseModel):
    """Список страниц вики с пагинацией"""

    items: list[WikiPageSummary]
    total: int
    page: int
    limit: int
    total_pages: int
