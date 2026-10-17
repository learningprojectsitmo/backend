from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.resume import (
    Resume,
    ResumeInterest,
    ResumeSkill,
    ResumeWorkspace,
)
from src.model.user import User
from src.model.workspace import WorkSpace, WorkSpaceParticipation
from src.repository.base_repository import BaseRepository
from src.schema.resume import ResumeCreate, ResumeUpdate


class ResumeRepository(BaseRepository[Resume, ResumeCreate, ResumeUpdate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Resume

    async def get_by_author_id(self, author_id: int) -> list[Resume]:
        """Получить резюме по автору"""

        result = await self.uow.session.execute(
            select(Resume).where(Resume.author_id == author_id),
        )
        return list(result.scalars().all())

    async def count_by_author_id(self, author_id: int) -> int:
        result = await self.uow.session.execute(
            select(func.count()).select_from(Resume).where(Resume.author_id == author_id),
        )
        return result.scalar()

    # ─── Связи резюме с пространствами (resume_workspace) ────────────────────

    async def get_space_links(self, resume_id: int) -> dict[int, ResumeWorkspace]:
        """Все назначения резюме на пространства: workspace_id → связь."""
        result = await self.uow.session.execute(
            select(ResumeWorkspace).where(ResumeWorkspace.resume_id == resume_id),
        )
        return {link.workspace_id: link for link in result.scalars().all()}

    async def get_default_space_links(self, resume_id: int) -> list[ResumeWorkspace]:
        """Связи, в которых это резюме основное (показывается на странице)."""
        result = await self.uow.session.execute(
            select(ResumeWorkspace).where(
                ResumeWorkspace.resume_id == resume_id,
                ResumeWorkspace.is_default.is_(True),
            ),
        )
        return list(result.scalars().all())

    async def unset_other_space_defaults(self, author_id: int, workspace_id: int, keep_resume_id: int) -> int:
        """Снять «основное» со всех резюме автора в пространстве, кроме keep.

        Нужен для переключения признака НА этот резюме: guard
        ``resume_id != keep_resume_id`` не даёт снять флаг, который в той же
        транзакции только что поставили. UPDATE выполняется немедленно —
        иначе частичный уникальный индекс uq_rw_author_workspace_default увидит
        две строки is_default = true до flush.
        """
        result = await self.uow.session.execute(
            update(ResumeWorkspace)
            .where(
                ResumeWorkspace.author_id == author_id,
                ResumeWorkspace.workspace_id == workspace_id,
                ResumeWorkspace.resume_id != keep_resume_id,
                ResumeWorkspace.is_default.is_(True),
            )
            .values(is_default=False),
        )
        return result.rowcount or 0

    async def clear_space_default(self, resume_id: int, workspace_id: int) -> None:
        """Немедленно снять признак основного с резюме в конкретном пространстве."""
        await self.uow.session.execute(
            update(ResumeWorkspace)
            .where(
                ResumeWorkspace.resume_id == resume_id,
                ResumeWorkspace.workspace_id == workspace_id,
            )
            .values(is_default=False),
        )

    async def set_space_default(self, resume_id: int, workspace_id: int) -> None:
        """Немедленно сделать резюме основным в пространстве (само ничего не снимает)."""
        await self.uow.session.execute(
            update(ResumeWorkspace)
            .where(
                ResumeWorkspace.resume_id == resume_id,
                ResumeWorkspace.workspace_id == workspace_id,
            )
            .values(is_default=True),
        )

    async def has_space_default(self, author_id: int, workspace_id: int) -> bool:
        """Есть ли у автора основное резюме в пространстве."""
        result = await self.uow.session.execute(
            select(ResumeWorkspace.id)
            .where(
                ResumeWorkspace.author_id == author_id,
                ResumeWorkspace.workspace_id == workspace_id,
                ResumeWorkspace.is_default.is_(True),
            )
            .limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def get_space_default_candidate_id(
        self,
        author_id: int,
        workspace_id: int,
        *,
        exclude_id: int,
        visible_only: bool,
    ) -> int | None:
        """Резюме автора, которым можно заменить основное в пространстве.

        Кандидат обязан быть назначено на это пространство (связь
        resume_workspace), иначе замена не даст автору карточки на странице.

        ``exclude_id`` обязателен: в момент вызова скрываемое/удаляемое резюме
        ещё в БД и иначе единственный кандидат — оно само.
        """
        query = (
            select(Resume.id)
            .join(ResumeWorkspace, ResumeWorkspace.resume_id == Resume.id)
            .where(
                ResumeWorkspace.author_id == author_id,
                ResumeWorkspace.workspace_id == workspace_id,
                Resume.id != exclude_id,
            )
        )
        if visible_only:
            query = query.where(Resume.is_visible.is_(True), Resume.header != "")
            query = query.order_by(Resume.id)
        else:
            query = query.order_by(
                Resume.is_visible.desc(),
                (Resume.header != "").desc(),
                Resume.id,
            )
        result = await self.uow.session.execute(query.limit(1))
        return result.scalar()

    async def get_member_workspace_names(self, author_id: int, workspace_ids: list[int]) -> dict[int, str]:
        """Названия пространств, в которых автор состоит (для валидации назначения)."""
        if not workspace_ids:
            return {}
        result = await self.uow.session.execute(
            select(WorkSpace.id, WorkSpace.name)
            .join(WorkSpaceParticipation, WorkSpaceParticipation.workspace_id == WorkSpace.id)
            .where(
                WorkSpaceParticipation.participant_id == author_id,
                WorkSpace.id.in_(workspace_ids),
            ),
        )
        return {row.id: row.name for row in result.all()}

    async def get_workspace_names(self, workspace_ids: list[int]) -> dict[int, str]:
        """Названия пространств без проверки членства (для текстов ошибок)."""
        if not workspace_ids:
            return {}
        result = await self.uow.session.execute(
            select(WorkSpace.id, WorkSpace.name).where(WorkSpace.id.in_(workspace_ids)),
        )
        return {row.id: row.name for row in result.all()}

    async def get_by_id_with_all(self, resume_id: int) -> Resume | None:
        query = (
            select(Resume)
            .where(Resume.id == resume_id)
            .options(
                selectinload(Resume.user).selectinload(User.role),
                selectinload(Resume.experiences),
                selectinload(Resume.skills),
                selectinload(Resume.interests),
                selectinload(Resume.links),
                selectinload(Resume.educations),
                selectinload(Resume.languages),
                selectinload(Resume.workspaces).selectinload(ResumeWorkspace.workspace),
            )
        )
        result = await self.uow.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_author_paginated(self, author_id: int, skip: int = 0, limit: int = 10) -> list[Resume]:
        """Получить резюме автора с пагинацией."""
        result = await self.uow.session.execute(
            select(Resume).where(Resume.author_id == author_id).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    # ─── Словарь навыков/интересов (автодополнение) ─────────────────────────

    async def get_distinct_skill_names(self, query: str, limit: int) -> list[str]:
        """Уникальные названия навыков по всем резюме (для подсказок).

        Названия схлопываются без учёта регистра (NumPy/Numpy → одно).
        """
        stmt = select(func.min(ResumeSkill.name)).group_by(func.lower(ResumeSkill.name))
        if query:
            stmt = stmt.where(ResumeSkill.name.ilike(f"%{query}%"))
        result = await self.uow.session.execute(
            stmt.order_by(func.lower(ResumeSkill.name)).limit(limit),
        )
        return list(result.scalars().all())

    async def get_distinct_interest_names(self, query: str, limit: int) -> list[str]:
        """Уникальные названия интересов по всем резюме (для подсказок).

        Названия схлопываются без учёта регистра (NumPy/Numpy → одно).
        """
        stmt = select(func.min(ResumeInterest.name)).group_by(func.lower(ResumeInterest.name))
        if query:
            stmt = stmt.where(ResumeInterest.name.ilike(f"%{query}%"))
        result = await self.uow.session.execute(
            stmt.order_by(func.lower(ResumeInterest.name)).limit(limit),
        )
        return list(result.scalars().all())

    async def increment_views_count(self, resume_id: int) -> None:
        """Увеличить счётчик просмотров резюме."""
        await self.uow.session.execute(
            update(Resume).where(Resume.id == resume_id).values(views_count=Resume.views_count + 1),
        )
        await self.uow.session.flush()
