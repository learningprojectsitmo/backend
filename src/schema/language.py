from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LanguageCreate(BaseModel):
    name: str
    level: str
    flag: str
    user_id: int | None = None


class LanguageUpdate(BaseModel):
    name: str | None = None
    level: str | None = None
    flag: str | None = None


class LanguageFull(LanguageCreate):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)
