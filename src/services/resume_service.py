from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from src.core.exceptions import PermissionError
from src.model.resume import (
    Resume,
    ResumeEducation,
    ResumeExperience,
    ResumeInterest,
    ResumeLanguage,
    ResumeLink,
    ResumeSkill,
)
from src.schema.resume import (
    ResumeCreate,
    ResumeDetail,
    ResumeEducationCreate,
    ResumeEducationFull,
    ResumeEducationUpdate,
    ResumeExperienceCreate,
    ResumeExperienceFull,
    ResumeExperienceUpdate,
    ResumeFull,
    ResumeInterestCreate,
    ResumeInterestFull,
    ResumeInterestUpdate,
    ResumeLanguageCreate,
    ResumeLanguageFull,
    ResumeLanguageUpdate,
    ResumeLinkCreate,
    ResumeLinkFull,
    ResumeLinkUpdate,
    ResumeSkillCreate,
    ResumeSkillFull,
    ResumeSkillUpdate,
    ResumeUpdate,
    ResumeUserInfo,
)
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.education_repository import EducationRepository
    from src.repository.language_repository import LanguageRepository
    from src.repository.portfolio_repository import PortfolioRepository
    from src.repository.resume_repository import ResumeRepository


class ResumeService(BaseService[Resume, ResumeCreate, ResumeUpdate]):
    def __init__(
        self,
        resume_repository: ResumeRepository,
        portfolio_repository: PortfolioRepository | None = None,
        education_repository: EducationRepository | None = None,
        language_repository: LanguageRepository | None = None,
    ):
        super().__init__(resume_repository)
        self._resume_repository = resume_repository
        self._portfolio_repository = portfolio_repository
        self._education_repository = education_repository
        self._language_repository = language_repository

    async def get_resume_by_id(self, resume_id: int) -> Resume | None:
        """Получить резюме по ID"""
        return await self._resume_repository.get_by_id(resume_id)

    async def get_resume_detail(self, resume_id: int) -> ResumeDetail | None:
        resume = await self._resume_repository.get_by_id_with_all(resume_id)
        if not resume:
            return None

        user = resume.user
        return ResumeDetail(
            resume=ResumeFull.model_validate(resume),
            user=ResumeUserInfo(
                id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                middle_name=user.middle_name,
                email=user.email,
                phone=user.phone,
                tg_nickname=user.tg_nickname,
                vk_nickname=user.vk_nickname,
                role=user.role.name if user.role else None,
            ),
            experiences=[ResumeExperienceFull.model_validate(e) for e in (resume.experiences or [])],
            skills=[ResumeSkillFull.model_validate(s) for s in (resume.skills or [])],
            interests=[ResumeInterestFull.model_validate(i) for i in (resume.interests or [])],
            links=[ResumeLinkFull.model_validate(link) for link in (resume.links or [])],
            educations=[ResumeEducationFull.model_validate(e) for e in (resume.educations or [])],
            languages=[ResumeLanguageFull.model_validate(lang) for lang in (resume.languages or [])],
        )

    async def get_resumes_by_author(self, author_id: int) -> list[Resume]:
        """Получить резюме по автору"""
        return await self._resume_repository.get_by_author_id(author_id)

    async def get_resumes_paginated(self, page: int = 1, limit: int = 10) -> tuple[list[Resume], int]:
        """Получить резюме с пагинацией"""
        skip = (page - 1) * limit
        resumes = await self._resume_repository.get_multi(skip=skip, limit=limit)
        total = await self._resume_repository.count()
        return resumes, total

    async def get_user_resumes_paginated(
        self, user_id: int, page: int = 1, limit: int = 10
    ) -> tuple[list[Resume], int]:
        """Получить резюме пользователя с пагинацией"""
        skip = (page - 1) * limit
        resumes = await self._resume_repository.get_by_author_paginated(user_id, skip=skip, limit=limit)
        total = await self._resume_repository.count_by_author_id(user_id)
        return resumes, total

    async def create_resume(self, resume_data: ResumeCreate, author_id: int) -> Resume:
        """Создать новое резюме с копированием данных из профиля"""
        if not resume_data.author_id:
            resume_data.author_id = author_id
        resume = await self._resume_repository.create(resume_data)
        await self._copy_profile_data_to_resume(resume.id, author_id)
        await self._resume_repository.uow.session.flush()
        return resume

    async def _copy_profile_data_to_resume(self, resume_id: int, user_id: int) -> None:
        """Скопировать портфолио, образование и языки из профиля в резюме"""
        session = self._resume_repository.uow.session

        if self._portfolio_repository:
            portfolio_items = await self._portfolio_repository.get_by_user_id(user_id)
            for item in portfolio_items:
                session.add(
                    ResumeLink(
                        resume_id=resume_id,
                        platform=item.title,
                        url=item.url,
                        sort_order=0,
                    )
                )

        if self._education_repository:
            education_items = await self._education_repository.get_by_user_id(user_id)
            for item in education_items:
                session.add(
                    ResumeEducation(
                        resume_id=resume_id,
                        institution=item.institution,
                        faculty=item.faculty,
                        degree=item.degree,
                        years=item.years,
                        sort_order=0,
                    )
                )

        if self._language_repository:
            language_items = await self._language_repository.get_by_user_id(user_id)
            for item in language_items:
                session.add(
                    ResumeLanguage(
                        resume_id=resume_id,
                        name=item.name,
                        level=item.level,
                        sort_order=0,
                    )
                )

    async def update_resume(self, resume_id: int, resume_data: ResumeUpdate, current_user_id: int) -> Resume | None:
        """Обновить резюме (только автор может обновлять)"""
        resume = await self.get_resume_by_id(resume_id)
        if not resume:
            return None

        if resume.author_id != current_user_id:
            raise PermissionError("Only author can update resume")

        return await self._resume_repository.update(resume_id, resume_data)

    async def delete_resume(self, resume_id: int, current_user_id: int) -> bool:
        """Удалить резюме (только автор может удалять)"""
        resume = await self.get_resume_by_id(resume_id)
        if not resume:
            return False

        if resume.author_id != current_user_id:
            raise PermissionError("Only author can delete resume")

        return await self._resume_repository.delete(resume_id)

    # ─── ResumeLink CRUD ────────────────────────────────────────────────────

    async def create_resume_link(self, resume_id: int, link_data: ResumeLinkCreate, current_user_id: int) -> ResumeLink:
        await self._check_ownership(resume_id, current_user_id)
        session = self._resume_repository.uow.session
        obj = ResumeLink(resume_id=resume_id, **link_data.model_dump())
        session.add(obj)
        await session.flush()
        return obj

    async def update_resume_link(
        self, link_id: int, link_data: ResumeLinkUpdate, current_user_id: int
    ) -> ResumeLink | None:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeLink).where(ResumeLink.id == link_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return None
        await self._check_ownership(obj.resume_id, current_user_id)
        for field, value in link_data.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await session.flush()
        return obj

    async def delete_resume_link(self, link_id: int, current_user_id: int) -> bool:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeLink).where(ResumeLink.id == link_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return False
        await self._check_ownership(obj.resume_id, current_user_id)
        await session.delete(obj)
        await session.flush()
        return True

    # ─── ResumeEducation CRUD ───────────────────────────────────────────────

    async def create_resume_education(
        self, resume_id: int, edu_data: ResumeEducationCreate, current_user_id: int
    ) -> ResumeEducation:
        await self._check_ownership(resume_id, current_user_id)
        session = self._resume_repository.uow.session
        obj = ResumeEducation(resume_id=resume_id, **edu_data.model_dump())
        session.add(obj)
        await session.flush()
        return obj

    async def update_resume_education(
        self, edu_id: int, edu_data: ResumeEducationUpdate, current_user_id: int
    ) -> ResumeEducation | None:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeEducation).where(ResumeEducation.id == edu_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return None
        await self._check_ownership(obj.resume_id, current_user_id)
        for field, value in edu_data.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await session.flush()
        return obj

    async def delete_resume_education(self, edu_id: int, current_user_id: int) -> bool:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeEducation).where(ResumeEducation.id == edu_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return False
        await self._check_ownership(obj.resume_id, current_user_id)
        await session.delete(obj)
        await session.flush()
        return True

    # ─── ResumeLanguage CRUD ────────────────────────────────────────────────

    async def create_resume_language(
        self, resume_id: int, lang_data: ResumeLanguageCreate, current_user_id: int
    ) -> ResumeLanguage:
        await self._check_ownership(resume_id, current_user_id)
        session = self._resume_repository.uow.session
        obj = ResumeLanguage(resume_id=resume_id, **lang_data.model_dump())
        session.add(obj)
        await session.flush()
        return obj

    async def update_resume_language(
        self, lang_id: int, lang_data: ResumeLanguageUpdate, current_user_id: int
    ) -> ResumeLanguage | None:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeLanguage).where(ResumeLanguage.id == lang_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return None
        await self._check_ownership(obj.resume_id, current_user_id)
        for field, value in lang_data.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await session.flush()
        return obj

    async def delete_resume_language(self, lang_id: int, current_user_id: int) -> bool:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeLanguage).where(ResumeLanguage.id == lang_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return False
        await self._check_ownership(obj.resume_id, current_user_id)
        await session.delete(obj)
        await session.flush()
        return True

    # ─── ResumeExperience CRUD ─────────────────────────────────────────────

    async def create_resume_experience(
        self, resume_id: int, exp_data: ResumeExperienceCreate, current_user_id: int
    ) -> ResumeExperience:
        await self._check_ownership(resume_id, current_user_id)
        session = self._resume_repository.uow.session
        obj = ResumeExperience(resume_id=resume_id, **exp_data.model_dump())
        session.add(obj)
        await session.flush()
        return obj

    async def update_resume_experience(
        self, exp_id: int, exp_data: ResumeExperienceUpdate, current_user_id: int
    ) -> ResumeExperience | None:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeExperience).where(ResumeExperience.id == exp_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return None
        await self._check_ownership(obj.resume_id, current_user_id)
        for field, value in exp_data.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await session.flush()
        return obj

    async def delete_resume_experience(self, exp_id: int, current_user_id: int) -> bool:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeExperience).where(ResumeExperience.id == exp_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return False
        await self._check_ownership(obj.resume_id, current_user_id)
        await session.delete(obj)
        await session.flush()
        return True

    # ─── ResumeSkill CRUD ──────────────────────────────────────────────────

    async def create_resume_skill(
        self, resume_id: int, skill_data: ResumeSkillCreate, current_user_id: int
    ) -> ResumeSkill:
        await self._check_ownership(resume_id, current_user_id)
        session = self._resume_repository.uow.session
        obj = ResumeSkill(resume_id=resume_id, **skill_data.model_dump())
        session.add(obj)
        await session.flush()
        return obj

    async def update_resume_skill(
        self, skill_id: int, skill_data: ResumeSkillUpdate, current_user_id: int
    ) -> ResumeSkill | None:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeSkill).where(ResumeSkill.id == skill_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return None
        await self._check_ownership(obj.resume_id, current_user_id)
        for field, value in skill_data.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await session.flush()
        return obj

    async def delete_resume_skill(self, skill_id: int, current_user_id: int) -> bool:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeSkill).where(ResumeSkill.id == skill_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return False
        await self._check_ownership(obj.resume_id, current_user_id)
        await session.delete(obj)
        await session.flush()
        return True

    # ─── ResumeInterest CRUD ───────────────────────────────────────────────

    async def create_resume_interest(
        self, resume_id: int, interest_data: ResumeInterestCreate, current_user_id: int
    ) -> ResumeInterest:
        await self._check_ownership(resume_id, current_user_id)
        session = self._resume_repository.uow.session
        obj = ResumeInterest(resume_id=resume_id, **interest_data.model_dump())
        session.add(obj)
        await session.flush()
        return obj

    async def update_resume_interest(
        self, interest_id: int, interest_data: ResumeInterestUpdate, current_user_id: int
    ) -> ResumeInterest | None:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeInterest).where(ResumeInterest.id == interest_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return None
        await self._check_ownership(obj.resume_id, current_user_id)
        for field, value in interest_data.model_dump(exclude_unset=True).items():
            setattr(obj, field, value)
        await session.flush()
        return obj

    async def delete_resume_interest(self, interest_id: int, current_user_id: int) -> bool:
        session = self._resume_repository.uow.session
        result = await session.execute(select(ResumeInterest).where(ResumeInterest.id == interest_id))
        obj = result.scalar_one_or_none()
        if not obj:
            return False
        await self._check_ownership(obj.resume_id, current_user_id)
        await session.delete(obj)
        await session.flush()
        return True

    async def _check_ownership(self, resume_id: int, current_user_id: int) -> Resume:
        """Проверить, что пользователь является автором резюме"""
        resume = await self.get_resume_by_id(resume_id)
        if not resume:
            raise PermissionError("Resume not found")
        if resume.author_id != current_user_id:
            raise PermissionError("Only author can modify this resume")
        return resume
