from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.model.ideas import Idea, IdeaTag
from src.model.user import User
from src.schema.ideas import IdeaUpdate
from src.services.ideas_service import IdeaService


def _make_idea(idea_id: int, author_id: int, tags: list[IdeaTag] | None = None) -> Idea:
    return Idea(
        id=idea_id,
        title="Старая идея",
        description="Старое описание",
        author_id=author_id,
        status="new",
        tags=tags or [],
        author=User(id=author_id, first_name="Автор", last_name=None, middle_name=""),
        comments=[],
        votes=0,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _build_service(idea: Idea | None = None) -> tuple[IdeaService, Mock]:
    repo = Mock()
    repo.get_by_id = AsyncMock(return_value=idea)
    repo.delete = AsyncMock(return_value=True)
    repo.uow.session = Mock()
    repo.uow.session.flush = AsyncMock()

    tag_repo = Mock()
    comment_repo = Mock()
    service = IdeaService(repo, tag_repo, comment_repo)
    return service, repo


class TestIdeaUpdate:
    @pytest.mark.asyncio
    async def test_author_should_update_own_idea(self):
        # given
        idea = _make_idea(1, author_id=7)
        service, repo = _build_service(idea)
        data = IdeaUpdate(status="in_progress", title="Новая идея")

        # when
        result = await service.update_idea(1, data, user_id=7)

        # then
        assert result is not None
        assert result.status == "in_progress"
        assert result.title == "Новая идея"
        repo.uow.session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_non_author_should_be_rejected(self):
        # given
        idea = _make_idea(1, author_id=7)
        service, _ = _build_service(idea)
        data = IdeaUpdate(status="new")

        # when / then
        with pytest.raises(PermissionError):
            await service.update_idea(1, data, user_id=99, is_admin=False)

    @pytest.mark.asyncio
    async def test_admin_should_update_foreign_idea(self):
        # given
        idea = _make_idea(1, author_id=7)
        service, _ = _build_service(idea)
        data = IdeaUpdate(status="completed")

        # when
        result = await service.update_idea(1, data, user_id=99, is_admin=True)

        # then
        assert result is not None
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_should_return_none_when_idea_missing(self):
        # given
        service, _ = _build_service(None)
        data = IdeaUpdate(status="new")

        # when
        result = await service.update_idea(1, data, user_id=7)

        # then
        assert result is None


class TestIdeaDelete:
    @pytest.mark.asyncio
    async def test_author_should_delete_own_idea_and_decrement_tags(self):
        # given
        tag = IdeaTag(id=1, name="test", count=3)
        idea = _make_idea(1, author_id=7, tags=[tag])
        service, repo = _build_service(idea)

        # when
        deleted = await service.delete_idea(1, user_id=7)

        # then
        assert deleted is True
        assert tag.count == 2
        repo.delete.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_non_author_should_not_delete_foreign_idea(self):
        # given
        idea = _make_idea(1, author_id=7)
        service, _ = _build_service(idea)

        # when / then
        with pytest.raises(PermissionError):
            await service.delete_idea(1, user_id=99, is_admin=False)

    @pytest.mark.asyncio
    async def test_admin_should_delete_foreign_idea(self):
        # given
        idea = _make_idea(1, author_id=7)
        service, repo = _build_service(idea)

        # when
        deleted = await service.delete_idea(1, user_id=99, is_admin=True)

        # then
        assert deleted is True
        repo.delete.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_should_return_false_when_idea_missing(self):
        # given
        service, _ = _build_service(None)

        # when
        deleted = await service.delete_idea(1, user_id=7)

        # then
        assert deleted is False


class TestGetIdeasFiltered:
    """N+1 в списке идей: голоса пользователя тянулись по одному запросу на идею."""

    @staticmethod
    def _service(ideas: list[Idea], votes: dict[int, str]) -> tuple[IdeaService, Mock]:
        repo = Mock()
        repo.get_ideas_filtered = AsyncMock(return_value=ideas)
        repo.count_filtered = AsyncMock(return_value=len(ideas))
        repo.get_user_votes = AsyncMock(return_value=votes)
        service = IdeaService(repo, Mock(), Mock())
        return service, repo

    @pytest.mark.asyncio
    async def test_should_fetch_votes_in_single_query(self):
        # given
        ideas = [_make_idea(i, author_id=7) for i in (1, 2, 3, 4, 5)]
        service, repo = self._service(ideas, {})

        # when
        await service.get_ideas_filtered(current_user_id=42)

        # then
        repo.get_user_votes.assert_awaited_once_with([1, 2, 3, 4, 5], 42)

    @pytest.mark.asyncio
    async def test_should_not_query_votes_when_number_of_ideas_grows(self):
        # given
        ideas = [_make_idea(i, author_id=7) for i in range(1, 51)]
        service, repo = self._service(ideas, {})

        # when
        await service.get_ideas_filtered(current_user_id=42)

        # then
        assert repo.get_user_votes.await_count == 1

    @pytest.mark.asyncio
    async def test_should_map_votes_to_ideas(self):
        # given
        ideas = [_make_idea(1, author_id=7), _make_idea(2, author_id=7)]
        service, _ = self._service(ideas, {1: "up"})

        # when
        result = await service.get_ideas_filtered(current_user_id=42)

        # then
        assert [item.user_vote for item in result["items"]] == ["up", None]

    @pytest.mark.asyncio
    async def test_should_skip_vote_query_for_anonymous(self):
        # given
        ideas = [_make_idea(1, author_id=7)]
        service, repo = self._service(ideas, {})

        # when
        result = await service.get_ideas_filtered(current_user_id=None)

        # then
        repo.get_user_votes.assert_not_awaited()
        assert result["items"][0].user_vote is None
