from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.schema.education import EducationFull
from src.schema.language import LanguageFull
from src.schema.portfolio import PortfolioFull
from src.schema.project import MyProjectItem
from src.schema.resume import ResumeFull
from src.schema.workspace import Space


class ProfileResponse(BaseModel):
    id: int
    first_name: str
    last_name: str | None
    middle_name: str
    email: str | None
    phone: str | None
    tg_nickname: str | None
    vk_nickname: str | None
    role: str
    resumes: list[ResumeFull]
    portfolio: list[PortfolioFull]
    education: list[EducationFull]
    languages: list[LanguageFull]

    model_config = ConfigDict(from_attributes=True)


class PublicProfileResponse(ProfileResponse):
    """Публичный профиль пользователя (для просмотра чужих профилей).

    Резюме — только видимые (is_visible=True), портфолио/образование/языки,
    а также публичные пространства и созданные пользователем проекты.
    """

    spaces: list[Space] = []
    projects: list[MyProjectItem] = []
