from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EducationCreate(BaseModel):
    institution: str
    faculty: str
    degree: str
    years: str
    user_id: int | None = None


class EducationUpdate(BaseModel):
    institution: str | None = None
    faculty: str | None = None
    degree: str | None = None
    years: str | None = None


class EducationFull(EducationCreate):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)
