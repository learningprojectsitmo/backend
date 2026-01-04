from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ResumeCreate(BaseModel):
    """Схема для создания резюме"""

    header: str
    author_id: int | None = None


class ResumeUpdate(BaseModel):
    """Схема для обновления резюме"""

    header: str | None = None
    resume_text: str | None = None


class ResumeFull(ResumeCreate):
    """Полная схема резюме"""

    id: int
    resume_text: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ResumeResponse(BaseModel):
    """Схема ответа с резюме"""

    id: int
    header: str
    author_id: int

    model_config = ConfigDict(from_attributes=True)


class ResumeListResponse(BaseModel):
    """Схема ответа со списком резюме"""

    items: list[ResumeFull]
    total: int
    page: int
    limit: int
    total_pages: int
