from __future__ import annotations

from typing import TYPE_CHECKING

from src.model.ideas import Idea, IdeaComment, IdeaTag, IdeaVote
from src.schema.ideas import (
    IdeaCommentResponse,
    IdeaCreate,
    IdeaFullResponse,
    IdeaListItem,
    IdeaTagResponse,
)
from src.services.base_service import BaseService

if TYPE_CHECKING:
    from src.repository.ideas_repository import IdeaCommentRepository, IdeaRepository, IdeaTagRepository


class IdeaService(BaseService[Idea, IdeaCreate, IdeaCreate]):
    def __init__(
        self,
        idea_repository: IdeaRepository,
        tag_repository: IdeaTagRepository,
        comment_repository: IdeaCommentRepository,
    ):
        super().__init__(idea_repository)
        self._idea_repository = idea_repository
        self._tag_repository = tag_repository
        self._comment_repository = comment_repository

    async def get_ideas_filtered(
        self,
        page: int = 1,
        limit: int = 100,
        search: str | None = None,
        sort: str | None = None,
        status: str | None = None,
        tag: str | None = None,
        current_user_id: int | None = None,
    ) -> dict:
        skip = (page - 1) * limit
        ideas = await self._idea_repository.get_ideas_filtered(
            search=search, sort=sort, status=status, tag=tag, skip=skip, limit=limit
        )
        total = await self._idea_repository.count_filtered(search=search, status=status, tag=tag)
        total_pages = (total + limit - 1) // limit if total > 0 else 0

        items = []
        for idea in ideas:
            user_vote = None
            if current_user_id is not None:
                vote = await self._idea_repository.get_user_vote(idea.id, current_user_id)
                user_vote = vote.direction if vote else None
            items.append(self._to_list_item(idea, user_vote))

        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }

    async def get_idea_full(self, idea_id: int, current_user_id: int | None = None) -> IdeaFullResponse | None:
        idea = await self._idea_repository.get_by_id(idea_id)
        if not idea:
            return None

        user_vote = None
        if current_user_id is not None:
            vote = await self._idea_repository.get_user_vote(idea.id, current_user_id)
            user_vote = vote.direction if vote else None

        return self._to_full_response(idea, user_vote)

    async def create_idea(self, data: IdeaCreate, author_id: int) -> Idea:
        idea = Idea(
            title=data.title,
            description=data.description,
            author_id=author_id,
        )

        if data.tags:
            for tag_name in data.tags:
                tag = await self._tag_repository.get_by_name(tag_name)
                if not tag:
                    tag = IdeaTag(name=tag_name, count=1)
                    self._idea_repository.uow.session.add(tag)
                else:
                    tag.count += 1
                idea.tags.append(tag)

        self._idea_repository.uow.session.add(idea)
        await self._idea_repository.uow.session.flush()
        return idea

    async def toggle_vote(self, idea_id: int, user_id: int, direction: str) -> Idea:
        idea = await self._idea_repository.get_by_id(idea_id)
        if not idea:
            raise ValueError("Idea not found")

        existing_vote = await self._idea_repository.get_user_vote(idea_id, user_id)

        if existing_vote:
            if existing_vote.direction == direction:
                await self._idea_repository.delete_vote(existing_vote.id)
                idea.votes += -1 if direction == "up" else 1
            else:
                old_direction = existing_vote.direction
                existing_vote.direction = direction
                idea.votes += (1 if direction == "up" else -1) + (-1 if old_direction == "up" else 1)
        else:
            vote = IdeaVote(idea_id=idea_id, user_id=user_id, direction=direction)
            self._idea_repository.uow.session.add(vote)
            idea.votes += 1 if direction == "up" else -1

        await self._idea_repository.uow.session.flush()
        return idea

    async def delete_idea(self, idea_id: int, user_id: int) -> bool:
        idea = await self._idea_repository.get_by_id(idea_id)
        if not idea:
            return False
        if idea.author_id != user_id:
            raise PermissionError("You can only delete your own ideas")

        for tag in idea.tags:
            tag.count -= 1

        return await self._idea_repository.delete(idea_id)

    async def get_comments(self, idea_id: int) -> list[IdeaCommentResponse]:
        comments = await self._comment_repository.get_by_idea_id(idea_id)
        return [
            IdeaCommentResponse(
                id=c.id,
                author={"id": c.author.id, "username": c.author.first_name or "Unknown"},
                text=c.text,
                created_at=c.created_at,
            )
            for c in comments
        ]

    async def add_comment(self, idea_id: int, author_id: int, text: str) -> IdeaComment:
        comment = IdeaComment(idea_id=idea_id, author_id=author_id, text=text)
        self._idea_repository.uow.session.add(comment)
        await self._idea_repository.uow.session.flush()
        return comment

    def _to_list_item(self, idea: Idea, user_vote: str | None = None) -> IdeaListItem:
        return IdeaListItem(
            id=idea.id,
            title=idea.title,
            description=idea.description,
            votes=idea.votes,
            user_vote=user_vote,
            comments_count=len(idea.comments) if idea.comments else 0,
            tags=[t.name for t in idea.tags] if idea.tags else [],
            status=idea.status,
            author={"id": idea.author.id, "username": idea.author.first_name or "Unknown"},
            created_at=idea.created_at,
        )

    def _to_full_response(self, idea: Idea, user_vote: str | None = None) -> IdeaFullResponse:
        return IdeaFullResponse(
            id=idea.id,
            title=idea.title,
            description=idea.description,
            votes=idea.votes,
            user_vote=user_vote,
            comments_count=len(idea.comments) if idea.comments else 0,
            tags=[t.name for t in idea.tags] if idea.tags else [],
            status=idea.status,
            author={"id": idea.author.id, "username": idea.author.first_name or "Unknown"},
            created_at=idea.created_at,
        )


class IdeaTagService(BaseService[IdeaTag, IdeaTag, IdeaTag]):
    def __init__(self, tag_repository: IdeaTagRepository):
        super().__init__(tag_repository)
        self._tag_repository = tag_repository

    async def get_all_tags(self) -> list[IdeaTagResponse]:
        tags = await self._tag_repository.get_all()
        return [IdeaTagResponse(id=t.id, name=t.name, count=t.count) for t in tags]

    async def create_tag(self, name: str) -> IdeaTag:
        existing = await self._tag_repository.get_by_name(name)
        if existing:
            return existing
        tag = IdeaTag(name=name, count=0)
        self._tag_repository.uow.session.add(tag)
        await self._tag_repository.uow.session.flush()
        return tag
