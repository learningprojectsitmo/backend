from __future__ import annotations

from typing import TYPE_CHECKING

from src.schema.profile import ProfileResponse
from src.schema.resume import ResumeFull

if TYPE_CHECKING:
    from src.repository.education_repository import EducationRepository
    from src.repository.language_repository import LanguageRepository
    from src.repository.portfolio_repository import PortfolioRepository
    from src.repository.resume_repository import ResumeRepository
    from src.repository.user_repository import UserRepository


class ProfileService:
    def __init__(
        self,
        user_repository: UserRepository,
        resume_repository: ResumeRepository,
        portfolio_repository: PortfolioRepository,
        education_repository: EducationRepository,
        language_repository: LanguageRepository,
    ):
        self._user_repository = user_repository
        self._resume_repository = resume_repository
        self._portfolio_repository = portfolio_repository
        self._education_repository = education_repository
        self._language_repository = language_repository

    async def get_profile(self, user_id: int) -> ProfileResponse:
        user = await self._user_repository.get_by_id_with_role(user_id)
        if not user:
            raise ValueError("User not found")

        resumes = await self._resume_repository.get_by_author_id(user_id)
        portfolio = await self._portfolio_repository.get_by_user_id(user_id)
        education = await self._education_repository.get_by_user_id(user_id)
        languages = await self._language_repository.get_by_user_id(user_id)

        return ProfileResponse(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            middle_name=user.middle_name,
            email=user.email,
            phone=user.phone,
            tg_nickname=user.tg_nickname,
            vk_nickname=user.vk_nickname,
            role=user.role.name if user.role else "member",
            resumes=[ResumeFull.model_validate(r) for r in resumes],
            portfolio=list(portfolio),
            education=list(education),
            languages=list(languages),
        )
