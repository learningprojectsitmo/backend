from __future__ import annotations

from datetime import date, datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_HEADER_LENGTH = 200
MAX_NAME_LENGTH = 100
MAX_ROLE_LENGTH = 100
MAX_LEVEL_LENGTH = 50
MAX_YEARS_LENGTH = 50
MAX_UNIVERSITY_LENGTH = 200
MAX_PLATFORM_LENGTH = 100
MAX_LINK_LENGTH = 500
MAX_COMPANY_POSITION_LENGTH = 200
MAX_DURATION_LENGTH = 100
MAX_TEXT_LENGTH = 10_000
MAX_EXPERIENCE_DESCRIPTION_LENGTH = 5_000


def _normalize_url(value: str) -> str:
    """Привести ссылку к https-виду и проверить, что она корректная."""
    value = value.strip()
    if not value or any(c.isspace() for c in value):
        raise ValueError("Укажите корректный URL (http/https)")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Укажите корректный URL (http/https)")
    return value


class ResumeExperienceFull(BaseModel):
    id: int
    company: str
    position: str
    experience_type: str | None = None
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


class ResumeSkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_NAME_LENGTH)
    sort_order: int = 0


class ResumeSkillUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=MAX_NAME_LENGTH)
    sort_order: int | None = None


class ResumeInterestCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_NAME_LENGTH)
    sort_order: int = 0


class ResumeInterestUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=MAX_NAME_LENGTH)
    sort_order: int | None = None


class ResumeLinkFull(BaseModel):
    id: int
    platform: str
    url: str
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeLinkCreate(BaseModel):
    platform: str = Field(..., min_length=1, max_length=MAX_PLATFORM_LENGTH)
    url: str = Field(..., min_length=1, max_length=MAX_LINK_LENGTH)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        return _normalize_url(value)


class ResumeLinkUpdate(BaseModel):
    platform: str | None = Field(None, min_length=1, max_length=MAX_PLATFORM_LENGTH)
    url: str | None = Field(None, min_length=1, max_length=MAX_LINK_LENGTH)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_url(value)


class ResumeEducationFull(BaseModel):
    id: int
    institution: str
    faculty: str | None = None
    degree: str | None = None
    years: str | None = None
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeLanguageFull(BaseModel):
    id: int
    name: str
    level: str | None = None
    sort_order: int = 0

    model_config = ConfigDict(from_attributes=True)


class ResumeEducationCreate(BaseModel):
    institution: str = Field(..., min_length=1, max_length=MAX_UNIVERSITY_LENGTH)
    faculty: str | None = Field(None, max_length=MAX_UNIVERSITY_LENGTH)
    degree: str | None = Field(None, max_length=MAX_UNIVERSITY_LENGTH)
    years: str | None = Field(None, max_length=MAX_YEARS_LENGTH)
    sort_order: int = 0


class ResumeEducationUpdate(BaseModel):
    institution: str | None = Field(None, min_length=1, max_length=MAX_UNIVERSITY_LENGTH)
    faculty: str | None = Field(None, max_length=MAX_UNIVERSITY_LENGTH)
    degree: str | None = Field(None, max_length=MAX_UNIVERSITY_LENGTH)
    years: str | None = Field(None, max_length=MAX_YEARS_LENGTH)
    sort_order: int | None = None


class ResumeLanguageCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_NAME_LENGTH)
    level: str | None = Field(None, max_length=MAX_LEVEL_LENGTH)
    sort_order: int = 0


class ResumeLanguageUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=MAX_NAME_LENGTH)
    level: str | None = Field(None, max_length=MAX_LEVEL_LENGTH)
    sort_order: int | None = None


class ResumeExperienceCreate(BaseModel):
    company: str = Field(..., min_length=1, max_length=MAX_COMPANY_POSITION_LENGTH)
    position: str = Field(..., min_length=1, max_length=MAX_COMPANY_POSITION_LENGTH)
    experience_type: str | None = Field(None, max_length=50)
    period_from: date | None = None
    period_to: date | None = None
    duration: str | None = Field(None, max_length=MAX_DURATION_LENGTH)
    description: str | None = Field(None, max_length=MAX_EXPERIENCE_DESCRIPTION_LENGTH)
    responsibilities: list[str] | None = None
    skills: list[str] | None = None
    sort_order: int = 0

    @model_validator(mode="after")
    def _check_period(self):
        if self.period_from and self.period_to and self.period_to < self.period_from:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        return self


class ResumeExperienceUpdate(BaseModel):
    company: str | None = Field(None, min_length=1, max_length=MAX_COMPANY_POSITION_LENGTH)
    position: str | None = Field(None, min_length=1, max_length=MAX_COMPANY_POSITION_LENGTH)
    experience_type: str | None = Field(None, max_length=50)
    period_from: date | None = None
    period_to: date | None = None
    duration: str | None = Field(None, max_length=MAX_DURATION_LENGTH)
    description: str | None = Field(None, max_length=MAX_EXPERIENCE_DESCRIPTION_LENGTH)
    responsibilities: list[str] | None = None
    skills: list[str] | None = None
    sort_order: int | None = None

    @model_validator(mode="after")
    def _check_period(self):
        if self.period_from and self.period_to and self.period_to < self.period_from:
            raise ValueError("Дата окончания не может быть раньше даты начала")
        return self


class ResumeCreate(BaseModel):
    header: str = Field(..., min_length=1, max_length=MAX_HEADER_LENGTH)
    author_id: int | None = None
    resume_text: str | None = Field(None, max_length=MAX_TEXT_LENGTH)
    role: str | None = Field(None, max_length=MAX_ROLE_LENGTH)
    about: str | None = Field(None, max_length=MAX_TEXT_LENGTH)
    cover_letter: str | None = Field(None, max_length=MAX_TEXT_LENGTH)
    has_experience: bool = True
    no_experience_description: str | None = Field(None, max_length=MAX_TEXT_LENGTH)
    is_visible: bool = False


class ResumeUpdate(BaseModel):
    header: str | None = Field(None, min_length=1, max_length=MAX_HEADER_LENGTH)
    resume_text: str | None = Field(None, max_length=MAX_TEXT_LENGTH)
    role: str | None = Field(None, max_length=MAX_ROLE_LENGTH)
    about: str | None = Field(None, max_length=MAX_TEXT_LENGTH)
    cover_letter: str | None = Field(None, max_length=MAX_TEXT_LENGTH)
    has_experience: bool | None = None
    no_experience_description: str | None = Field(None, max_length=MAX_TEXT_LENGTH)
    is_visible: bool | None = None
    # Сделать резюме основным. Переключение снимает флаг с предыдущего
    # основного резюме того же автора в той же транзакции.
    is_default: bool | None = None


class ResumeFull(ResumeCreate):
    id: int
    author_id: int
    views_count: int = 0
    invitations_count: int = 0
    # В ResumeCreate поля нет намеренно: какое резюме станет основным,
    # решает сервис (первое созданное), а не клиент.
    is_default: bool = False
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
