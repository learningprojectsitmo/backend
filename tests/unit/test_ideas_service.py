# ruff: noqa: PLR2004
from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.model.ideas import Idea, IdeaTag
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
