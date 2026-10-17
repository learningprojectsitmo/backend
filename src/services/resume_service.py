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
    ResumeWorkspace,
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
    ResumeSpaceAssign,
    ResumeSpaceOut,
    ResumeUpdate,
    ResumeUserInfo,
)
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.model.user import User
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

    async def get_resume_detail(self, resume_id: int, viewer: User | None = None) -> ResumeDetail | None:
        resume = await self._resume_repository.get_by_id_with_all(resume_id)
        if not resume:
            return None

        if viewer and viewer.id != resume.author_id:
            role_name = viewer.role.name if viewer.role else ""
            if role_name not in ("admin", "teacher"):
                await self._resume_repository.increment_views_count(resume_id)
                await self._resume_repository.uow.session.refresh(resume)

        user = resume.user
        resume_full = ResumeFull.model_validate(resume)
        resume_full.spaces = [
            ResumeSpaceOut(
                workspace_id=link.workspace_id,
                workspace_name=link.workspace.name if link.workspace else "",
                is_default=link.is_default,
            )
            for link in resume.workspaces
        ]
        return ResumeDetail(
            resume=resume_full,
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
        spaces = list(resume_data.spaces)
        # spaces — не колонка resume: назначения на пространства создаёт
        # _apply_spaces отдельными строками resume_workspace.
        payload = resume_data.model_dump(exclude_unset=True, exclude={"spaces"})
        resume = await self._resume_repository.create(payload)
        await self._copy_profile_data_to_resume(resume.id, author_id)
        await self._resume_repository.uow.session.flush()
        if spaces:
            await self._apply_spaces(resume, spaces, visible=resume.is_visible)
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
                        flag=item.flag,
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

        if resume_data.spaces is not None:
            visible = resume.is_visible if resume_data.is_visible is None else resume_data.is_visible
            await self._apply_spaces(resume, resume_data.spaces, visible=visible)

        if resume_data.is_visible is False:
            # Скрытие основного резюме переносит признак на другое видимое
            # резюме того же пространства; если заменить нечего — запрещаем.
            await self._move_space_defaults_away_on_hide(resume)

        payload = resume_data.model_dump(exclude_unset=True, exclude={"spaces"})
        return await self._resume_repository.update(resume_id, payload)

    async def _apply_spaces(
        self,
        resume: Resume,
        spaces: list[ResumeSpaceAssign],
        *,
        visible: bool,
    ) -> None:
        """Заменить назначения резюме на пространства (replace-all).

        Инварианты:
        - автор должен состоять в каждом указанном пространстве;
        - «основное» не больше одного на автора в пространстве — при явном
          переключении флаг снимается с остальных немедленно (частичный
          уникальный индекс uq_rw_author_workspace_default);
        - если в пространстве не осталось основного резюме автора, признак
          достаётся видимому кандидату, а при его отсутствии — самому
          назначаемому резюме (если оно видимое).
        """
        repo = self._resume_repository
        session = repo.uow.session

        # Дедупликация: для каждого пространства побеждает последнее назначение.
        dedup: dict[int, ResumeSpaceAssign] = {}
        for assign in spaces:
            dedup[assign.workspace_id] = assign

        member_names = await repo.get_member_workspace_names(resume.author_id, list(dedup))
        missing = [ws_id for ws_id in dedup if ws_id not in member_names]
        if missing:
            names = await repo.get_workspace_names(missing)
            missing_titles = ", ".join(str(names.get(ws_id, ws_id)) for ws_id in missing)
            raise ValueError(
                f"Нельзя назначить резюме на пространства: вы не являетесь их участником: {missing_titles}."
            )

        existing = await repo.get_space_links(resume.id)

        affected: set[int] = set()
        for ws_id, link in existing.items():
            if ws_id not in dedup:
                if link.is_default:
                    affected.add(ws_id)
                await session.delete(link)
        await session.flush()

        for ws_id, assign in dedup.items():
            link = existing.get(ws_id)
            if link is None:
                link = ResumeWorkspace(
                    resume_id=resume.id,
                    workspace_id=ws_id,
                    author_id=resume.author_id,
                    is_default=False,
                )
                session.add(link)
                await session.flush()
                existing[ws_id] = link
            if assign.is_default:
                await repo.unset_other_space_defaults(resume.author_id, ws_id, keep_resume_id=resume.id)
                link.is_default = True
                affected.discard(ws_id)
                continue
            if link.is_default:
                await repo.clear_space_default(resume.id, ws_id)
                link.is_default = False
            affected.add(ws_id)

        await self._ensure_space_defaults(resume, affected, existing, visible=visible)

    async def _ensure_space_defaults(
        self,
        resume: Resume,
        affected: set[int],
        existing: dict[int, ResumeWorkspace],
        *,
        visible: bool,
    ) -> None:
        """Восстановить «основное» в пространствах, где его не осталось.

        Если в пространстве нет основного резюме автора, признак достаётся
        видимому кандидату, а при его отсутствии — самому назначаемому
        резюме (если оно видимое), иначе у участника не будет карточки.
        """
        repo = self._resume_repository
        for ws_id in affected:
            if await repo.has_space_default(resume.author_id, ws_id):
                continue
            candidate_id = await repo.get_space_default_candidate_id(
                resume.author_id,
                ws_id,
                exclude_id=resume.id,
                visible_only=True,
            )
            if candidate_id is not None:
                await repo.set_space_default(candidate_id, ws_id)
                continue
            link = existing.get(ws_id)
            if link is not None and visible and resume.header:
                await repo.set_space_default(resume.id, ws_id)

    async def _move_space_defaults_away_on_hide(self, resume: Resume) -> None:
        """Перенести «основное» с резюме во всех пространствах при скрытии.

        Если хотя бы в одном пространстве нет другого видимого резюме —
        операция запрещается: сообщение уже готово для показа пользователю.
        """
        repo = self._resume_repository
        links = await repo.get_default_space_links(resume.id)
        if not links:
            return

        names = await repo.get_workspace_names([link.workspace_id for link in links])
        moves: list[tuple[int, int]] = []
        blocked: list[int] = []
        for link in links:
            candidate_id = await repo.get_space_default_candidate_id(
                resume.author_id,
                link.workspace_id,
                exclude_id=resume.id,
                visible_only=True,
            )
            if candidate_id is None:
                blocked.append(link.workspace_id)
            else:
                moves.append((link.workspace_id, candidate_id))

        if blocked:
            blocked_titles = ", ".join(str(names.get(ws_id, ws_id)) for ws_id in blocked)
            raise ValueError(
                "Нельзя скрыть резюме: оно является основным в пространствах: "
                f"{blocked_titles}. Сначала сделайте основным другое видимое резюме в этих пространствах."
            )

        for workspace_id, candidate_id in moves:
            # Порядок критичен: сначала снять флаг с текущего основного,
            # затем поставить кандидату — иначе в пространстве окажется
            # два основных и uq_rw_author_workspace_default упадёт.
            await repo.clear_space_default(resume.id, workspace_id)
            await repo.set_space_default(candidate_id, workspace_id)

    async def delete_resume(self, resume_id: int, current_user_id: int) -> bool:
        """Удалить резюме (только автор может удалять)"""
        resume = await self.get_resume_by_id(resume_id)
        if not resume:
            return False

        if resume.author_id != current_user_id:
            raise PermissionError("Only author can delete resume")

        default_links = await self._resume_repository.get_default_space_links(resume_id)
        deleted = await self._resume_repository.delete(resume_id)
        if deleted and default_links:
            # Удаление основного в пространстве не должно оставлять автора
            # без карточки на странице пространства. Сначала ищем видимое
            # (оно и попадёт в карточку), но если видимых не осталось — берём
            # любое: лучше скрытое основное, чем автор вообще без признака.
            session = self._resume_repository.uow.session
            # session.delete() только помечает объект, а DELETE уходит на
            # flush; без него кандидат получил бы is_default = true при ещё
            # существующей строке основного и уникальный индекс упал бы.
            await session.flush()
            for link in default_links:
                candidate_id = await self._resume_repository.get_space_default_candidate_id(
                    resume.author_id,
                    link.workspace_id,
                    exclude_id=resume_id,
                    visible_only=True,
                )
                if candidate_id is None:
                    candidate_id = await self._resume_repository.get_space_default_candidate_id(
                        resume.author_id,
                        link.workspace_id,
                        exclude_id=resume_id,
                        visible_only=False,
                    )
                if candidate_id is not None:
                    await self._resume_repository.set_space_default(candidate_id, link.workspace_id)
        return deleted

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

    # ─── Словарь навыков/интересов (автодополнение) ─────────────────────────

    async def get_skill_suggestions(self, query: str, limit: int = 20) -> list[str]:
        """Уникальные навыки по всем резюме, отфильтрованные по подстроке."""
        return await self._resume_repository.get_distinct_skill_names(query.strip(), limit)

    async def get_interest_suggestions(self, query: str, limit: int = 20) -> list[str]:
        """Уникальные интересы по всем резюме, отфильтрованные по подстроке."""
        return await self._resume_repository.get_distinct_interest_names(query.strip(), limit)

    async def _check_ownership(self, resume_id: int, current_user_id: int) -> Resume:
        """Проверить, что пользователь является автором резюме"""
        resume = await self.get_resume_by_id(resume_id)
        if not resume:
            raise PermissionError("Resume not found")
        if resume.author_id != current_user_id:
            raise PermissionError("Only author can modify this resume")
        return resume
