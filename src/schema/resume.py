from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ResumeExperienceFull(BaseModel):
    id: int
    company: str
    position: str
    period_from: date | None = None
    period_to: date | None = None
    duration: str | None = None
    description: str | None = None
    responsibilities: list[str] | None = None
    skills: list[str] | None = None
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeSkillFull(BaseModel):
    id: int
    name: str
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeInterestFull(BaseModel):
    id: int
    name: str
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeLinkFull(BaseModel):
    id: int
    platform: str
    url: str
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeEducationFull(BaseModel):
    id: int
    institution: str
    faculty: str | None = None
    degree: str | None = None
    year: int | None = None
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeLanguageFull(BaseModel):
    id: int
    name: str
    level: str | None = None
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeCreate(BaseModel):
    header: str
    author_id: int | None = None
    resume_text: str | None = None
    role: str | None = None
    about: str | None = None
    cover_letter: str | None = None


class ResumeUpdate(BaseModel):
    header: str | None = None
    resume_text: str | None = None
    role: str | None = None
    about: str | None = None
    cover_letter: str | None = None


class ResumeFull(ResumeCreate):
    id: int
    author_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ResumeResponse(BaseModel):
    id: int
    header: str
    author_id: int

    model_config = ConfigDict(from_attributes=True)


class ResumeListResponse(BaseModel):
    items: list[ResumeFull]
    total: int
    page: int
    limit: int
    total_pages: int


class ResumeUserInfo(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    middle_name: str
    email: str | None = None
    phone: str | None = None
    tg_nickname: str | None = None
    vk_nickname: str | None = None
    role: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ResumeDetail(BaseModel):
    resume: ResumeFull
    user: ResumeUserInfo
    experiences: list[ResumeExperienceFull] = []
    skills: list[ResumeSkillFull] = []
    interests: list[ResumeInterestFull] = []
    links: list[ResumeLinkFull] = []
    educations: list[ResumeEducationFull] = []
    languages: list[ResumeLanguageFull] = []
