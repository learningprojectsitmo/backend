from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from src.core.uow import IUnitOfWork
from src.model.ideas import Idea, IdeaComment, IdeaTag, IdeaVote
from src.repository.base_repository import BaseRepository
from src.schema.ideas import IdeaCommentCreate, IdeaCreate


class IdeaRepository(BaseRepository[Idea, IdeaCreate, IdeaCreate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = Idea

    async def get_ideas_filtered(
        self,
        search: str | None = None,
        sort: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Idea]:
        query = (
            select(Idea)
            .options(
                selectinload(Idea.tags),
                selectinload(Idea.author),
                selectinload(Idea.comments),
            )
        )

        if status and status != "all":
            query = query.where(Idea.status == status)

        if tag:
            query = query.where(Idea.tags.any(IdeaTag.name == tag))

        if search:
            q = f"%{search}%"
            query = query.where(
                Idea.title.ilike(q) | Idea.description.ilike(q)
            )

        query = query.order_by(Idea.votes.desc()) if sort == "popular" else query.order_by(Idea.created_at.desc())

        query = query.offset(skip).limit(limit)
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def count_filtered(
        self,
        search: str | None = None,
        status: str | None = None,
        tag: str | None = None,
    ) -> int:
        query = select(func.count()).select_from(Idea)

        if status and status != "all":
            query = query.where(Idea.status == status)

        if tag:
            query = query.where(Idea.tags.any(IdeaTag.name == tag))

        if search:
            q = f"%{search}%"
            query = query.where(
                Idea.title.ilike(q) | Idea.description.ilike(q)
            )

        result = await self.uow.session.execute(query)
        return result.scalar_one()

    async def get_by_id(self, id: int) -> Idea | None:
        query = (
            select(Idea)
            .where(Idea.id == id)
            .options(
                selectinload(Idea.tags),
                selectinload(Idea.author),
                selectinload(Idea.comments).selectinload(IdeaComment.author),
                selectinload(Idea.votes_list),
            )
        )
        result = await self.uow.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_vote(self, idea_id: int, user_id: int) -> IdeaVote | None:
        query = select(IdeaVote).where(
            IdeaVote.idea_id == idea_id,
            IdeaVote.user_id == user_id,
        )
        result = await self.uow.session.execute(query)
        return result.scalar_one_or_none()

    async def delete_vote(self, vote_id: int) -> None:
        await self.uow.session.execute(
            delete(IdeaVote).where(IdeaVote.id == vote_id)
        )


class IdeaTagRepository(BaseRepository[IdeaTag, IdeaTag, IdeaTag]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = IdeaTag

    async def get_by_name(self, name: str) -> IdeaTag | None:
        query = select(IdeaTag).where(IdeaTag.name == name)
        result = await self.uow.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(self) -> list[IdeaTag]:
        query = select(IdeaTag)
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def increment_count(self, tag_id: int) -> None:
        query = select(IdeaTag).where(IdeaTag.id == tag_id)
        result = await self.uow.session.execute(query)
        tag = result.scalar_one_or_none()
        if tag:
            tag.count += 1


class IdeaCommentRepository(BaseRepository[IdeaComment, IdeaCommentCreate, IdeaCommentCreate]):
    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = IdeaComment

    async def get_by_idea_id(self, idea_id: int) -> list[IdeaComment]:
        query = (
            select(IdeaComment)
            .where(IdeaComment.idea_id == idea_id)
            .options(selectinload(IdeaComment.author))
            .order_by(IdeaComment.created_at)
        )
        result = await self.uow.session.execute(query)
        return list(result.scalars().all())

    async def count_by_idea_id(self, idea_id: int) -> int:
        query = select(func.count()).select_from(IdeaComment).where(IdeaComment.idea_id == idea_id)
        result = await self.uow.session.execute(query)
        return result.scalar_one()
