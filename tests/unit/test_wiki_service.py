from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.project import Project
from src.model.user import User
from src.model.wiki import WikiPage
from src.schema.wiki import WikiPageCreate, WikiPageUpdate
from src.services.wiki_service import WikiService

PROJECT_ID = 10
SPACE_ID = 42
LEAD_ID = 100
TEACHER_ID = 200
MEMBER_ID = 300
OUTSIDER_ID = 400
PLATFORM_ADMIN_ID = 500
NEW_PAGE_ID = 555


def _project(author_id: int = LEAD_ID, workspace_id: int | None = SPACE_ID) -> Project:
    return Project(id=PROJECT_ID, name="Test", author_id=author_id, workspace_id=workspace_id)


def _page(
    page_id: int = 1,
    *,
    project_id: int = PROJECT_ID,
    author_id: int = LEAD_ID,
    visibility: str = "private",
    parent_id: int | None = None,
    title: str = "Страница",
    content: str = "<p>тело</p>",
) -> WikiPage:
    page = WikiPage(
        id=page_id,
        project_id=project_id,
        author_id=author_id,
        title=title,
        content=content,
        visibility=visibility,
        position=0,
    )
    page.parent_id = parent_id
    page.author = User(id=author_id, email=f"user{author_id}@example.com", first_name="Имя")
    return page


def _user(user_id: int) -> User:
    return User(id=user_id, email=f"user{user_id}@example.com", first_name="Имя")


def _session() -> Mock:
    """Мок AsyncSession: add синхронный, delete/flush/execute — корутины."""
    session = Mock()
    session.add = Mock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(return_value=_found(None))
    return session


def _found(value: object) -> Mock:
    """Результат execute() для exists-подобных выборок."""
    result = Mock()
    result.scalar_one_or_none.return_value = value
    return result


def _first(is_found: bool) -> Mock:
    result = Mock()
    result.first.return_value = object() if is_found else None
    return result


def _make(
    project: Project | None = None,
    *,
    participant: bool = False,
    editor: bool = False,
) -> tuple[WikiService, Mock]:
    """Сервис с подменёнными проверками членства.

    По умолчанию читатель — посторонний: ни участник, ни редактор.
    """
    service, wiki_repo = _make_raw(project)
    service._is_project_participant = AsyncMock(return_value=participant)  # type: ignore[method-assign]
    service._is_workspace_editor = AsyncMock(return_value=editor)  # type: ignore[method-assign]
    return service, wiki_repo


def _make_raw(project: Project | None = None) -> tuple[WikiService, Mock]:
    """Сервис с настоящими проверками членства — для их собственных тестов."""
    wiki_repo = Mock()
    wiki_repo.uow = Mock()
    wiki_repo.uow.session = _session()
    project_repo = Mock()
    project_repo.get_by_id = AsyncMock(return_value=project if project is not None else _project())
    return WikiService(wiki_repo, project_repository=project_repo), wiki_repo  # type: ignore[arg-type]


def _echo_created(wiki_repo: Mock, author_id: int) -> AsyncMock:
    """get_with_author возвращает ту страницу, которую сервис только что создал.

    Так тест проверяет весь путь create → повторное чтение → ответ, а не то,
    что тест сам подсунул в репозиторий. page_id игнорируется: до flush
    сервиса он ещё None, а id проставляет БД — здесь его играет NEW_PAGE_ID.
    """

    async def _get(page_id: int) -> WikiPage:
        created = wiki_repo.uow.session.add.call_args.args[0]
        created.id = NEW_PAGE_ID
        created.author = _user(author_id)
        return created

    return AsyncMock(side_effect=_get)


class TestWikiServiceAccess:
    @pytest.mark.asyncio
    async def test_should_allow_anonymous_to_read_public_page(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(visibility="public"))

        # when
        result = await service.get_page(PROJECT_ID, 1, None)

        # then
        assert result.visibility == "public"
        assert result.content == "<p>тело</p>"

    @pytest.mark.asyncio
    async def test_should_hide_private_page_from_anonymous_with_404(self):
        # given — 404, а не 403, иначе по id перебираются приватные страницы
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(visibility="private"))

        # when / then
        with pytest.raises(NotFoundError):
            await service.get_page(PROJECT_ID, 1, None)

    @pytest.mark.asyncio
    async def test_should_hide_private_page_from_outsider(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(visibility="private"))

        # when / then
        with pytest.raises(NotFoundError):
            await service.get_page(PROJECT_ID, 1, OUTSIDER_ID)

    @pytest.mark.asyncio
    async def test_should_allow_team_member_to_read_private_page(self):
        # given
        service, wiki_repo = _make(participant=True)
        wiki_repo.get_with_author = AsyncMock(return_value=_page(visibility="private"))

        # when
        result = await service.get_page(PROJECT_ID, 1, MEMBER_ID)

        # then
        assert result.visibility == "private"

    @pytest.mark.asyncio
    async def test_should_allow_platform_admin_to_read_private_page(self):
        # given — админ не состоит ни в проекте, ни в пространстве
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(visibility="private"))

        # when
        result = await service.get_page(PROJECT_ID, 1, PLATFORM_ADMIN_ID, is_admin=True)

        # then
        assert result.visibility == "private"

    @pytest.mark.asyncio
    async def test_should_limit_anonymous_list_to_public_visibility(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.count_by_project = AsyncMock(return_value=1)
        wiki_repo.get_by_project = AsyncMock(return_value=[_page(visibility="public")])

        # when
        result = await service.list_pages(PROJECT_ID, None)

        # then
        assert wiki_repo.get_by_project.await_args.kwargs["visibilities"] == ["public"]
        assert [item.visibility for item in result.items] == ["public"]

    @pytest.mark.asyncio
    async def test_should_give_team_member_both_visibilities_in_list(self):
        # given
        service, wiki_repo = _make(participant=True)
        wiki_repo.count_by_project = AsyncMock(return_value=2)
        wiki_repo.get_by_project = AsyncMock(return_value=[_page(1), _page(2)])

        # when
        await service.list_pages(PROJECT_ID, MEMBER_ID)

        # then
        assert wiki_repo.get_by_project.await_args.kwargs["visibilities"] == ["public", "private"]

    @pytest.mark.asyncio
    async def test_should_paginate_list_in_query(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.count_by_project = AsyncMock(return_value=10)
        wiki_repo.get_by_project = AsyncMock(return_value=[])

        # when
        result = await service.list_pages(PROJECT_ID, None, page=3, limit=4)

        # then
        assert (result.total, result.page, result.limit, result.total_pages) == (10, 3, 4, 3)
        kwargs = wiki_repo.get_by_project.await_args.kwargs
        assert kwargs["offset"] == 8
        assert kwargs["limit"] == 4

    @pytest.mark.asyncio
    async def test_should_filter_tree_by_visibility(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_by_project = AsyncMock(return_value=[_page(visibility="public")])

        # when
        tree = await service.get_tree(PROJECT_ID, None)

        # then
        assert wiki_repo.get_by_project.await_args.kwargs["visibilities"] == ["public"]
        assert len(tree) == 1

    @pytest.mark.asyncio
    async def test_should_reject_page_from_another_project(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(visibility="public", project_id=999))

        # when / then
        with pytest.raises(NotFoundError):
            await service.get_page(PROJECT_ID, 1, None)

    @pytest.mark.asyncio
    async def test_should_404_when_project_missing(self):
        # given
        service, _ = _make()
        service._project_repository.get_by_id = AsyncMock(return_value=None)  # type: ignore[attr-defined]

        # when / then
        with pytest.raises(NotFoundError):
            await service.get_page(PROJECT_ID, 1, None)


class TestWikiServiceTeamChecks:
    """Проверки членства на реальных запросах, без заглушек сервиса."""

    @pytest.mark.asyncio
    async def test_should_treat_project_author_as_team_member(self):
        # given — автору проекта не нужно ни одного запроса
        service, wiki_repo = _make_raw()
        wiki_repo.uow.session.execute = AsyncMock(side_effect=AssertionError("запрос не ожидался"))

        # when
        result = await service._is_team_member(_project(author_id=LEAD_ID), LEAD_ID)

        # then
        assert result is True

    @pytest.mark.asyncio
    async def test_should_treat_project_participant_as_team_member(self):
        # given
        service, wiki_repo = _make_raw()
        wiki_repo.uow.session.execute = AsyncMock(return_value=_found(object()))

        # when
        result = await service._is_team_member(_project(), MEMBER_ID)

        # then
        assert result is True

    @pytest.mark.asyncio
    async def test_should_treat_workspace_editor_as_team_member(self):
        # given — первый вызов ищет участие в проекте, второй роль в пространстве
        service, wiki_repo = _make_raw()
        wiki_repo.uow.session.execute = AsyncMock(side_effect=[_found(None), _first(True)])

        # when
        result = await service._is_team_member(_project(), TEACHER_ID)

        # then
        assert result is True
        assert wiki_repo.uow.session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_should_exclude_outsider_from_team(self):
        # given
        service, wiki_repo = _make_raw()
        wiki_repo.uow.session.execute = AsyncMock(side_effect=[_found(None), _first(False)])

        # when
        result = await service._is_team_member(_project(), OUTSIDER_ID)

        # then
        assert result is False

    @pytest.mark.asyncio
    async def test_should_not_check_workspace_roles_without_workspace(self):
        # given — проект вне пространства
        service, wiki_repo = _make_raw(project=_project(workspace_id=None))
        wiki_repo.uow.session.execute = AsyncMock(return_value=_found(None))

        # when
        result = await service._is_team_member(_project(workspace_id=None), MEMBER_ID)

        # then
        assert result is False
        assert wiki_repo.uow.session.execute.await_count == 1


class TestWikiServiceWrites:
    @pytest.mark.asyncio
    async def test_should_reject_create_from_outsider(self):
        # given
        service, _ = _make()
        service._is_team_member = AsyncMock(return_value=False)  # type: ignore[method-assign]

        # when / then
        with pytest.raises(PermissionError):
            await service.create_page(PROJECT_ID, OUTSIDER_ID, WikiPageCreate(title="X"))

    @pytest.mark.asyncio
    async def test_should_create_private_page_for_team_member(self):
        # given
        service, wiki_repo = _make()
        service._is_team_member = AsyncMock(return_value=True)  # type: ignore[method-assign]
        service._can_change_visibility = AsyncMock(return_value=False)  # type: ignore[method-assign]
        wiki_repo.get_max_position = AsyncMock(return_value=3)
        wiki_repo.get_with_author = _echo_created(wiki_repo, MEMBER_ID)

        # when
        result = await service.create_page(PROJECT_ID, MEMBER_ID, WikiPageCreate(title="  Онбординг  "))

        # then
        assert result.title == "Онбординг"
        assert result.visibility == "private"
        assert result.position == 4
        assert result.author is not None
        assert result.author.id == MEMBER_ID

    @pytest.mark.asyncio
    async def test_should_sanitize_content_on_create(self):
        # given
        service, wiki_repo = _make()
        service._is_team_member = AsyncMock(return_value=True)  # type: ignore[method-assign]
        wiki_repo.get_max_position = AsyncMock(return_value=0)
        wiki_repo.get_with_author = _echo_created(wiki_repo, LEAD_ID)
        service._can_change_visibility = AsyncMock(return_value=True)  # type: ignore[method-assign]

        # when
        await service.create_page(
            PROJECT_ID,
            LEAD_ID,
            WikiPageCreate(title="X", content="<p>ok</p><script>alert(1)</script>"),
        )

        # then
        created = wiki_repo.uow.session.add.call_args.args[0]
        assert created.content == "<p>ok</p>"

    @pytest.mark.asyncio
    async def test_should_reject_publish_by_ordinary_member(self):
        # given — участник команды не может выставить страницу публичной
        service, _ = _make()
        service._is_team_member = AsyncMock(return_value=True)  # type: ignore[method-assign]
        service._can_change_visibility = AsyncMock(return_value=False)  # type: ignore[method-assign]

        # when / then
        with pytest.raises(PermissionError):
            await service.create_page(PROJECT_ID, MEMBER_ID, WikiPageCreate(title="X", visibility="public"))

    @pytest.mark.asyncio
    async def test_should_allow_lead_to_publish(self):
        # given
        service, wiki_repo = _make()
        service._is_team_member = AsyncMock(return_value=True)  # type: ignore[method-assign]
        service._can_change_visibility = AsyncMock(return_value=True)  # type: ignore[method-assign]
        wiki_repo.get_max_position = AsyncMock(return_value=0)
        wiki_repo.get_with_author = _echo_created(wiki_repo, LEAD_ID)

        # when
        result = await service.create_page(PROJECT_ID, LEAD_ID, WikiPageCreate(title="X", visibility="public"))

        # then
        assert result.visibility == "public"

    @pytest.mark.asyncio
    async def test_should_reject_create_with_unknown_parent(self):
        # given
        service, wiki_repo = _make()
        service._is_team_member = AsyncMock(return_value=True)  # type: ignore[method-assign]
        wiki_repo.get_by_id = AsyncMock(return_value=None)

        # when / then
        with pytest.raises(NotFoundError):
            await service.create_page(PROJECT_ID, LEAD_ID, WikiPageCreate(title="X", parent_id=77))

    @pytest.mark.asyncio
    async def test_should_reject_update_by_another_member(self):
        # given — участник команды правит только свои страницы
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(author_id=LEAD_ID))

        # when / then
        with pytest.raises(PermissionError):
            await service.update_page(PROJECT_ID, 1, MEMBER_ID, WikiPageUpdate(title="New"))

    @pytest.mark.asyncio
    async def test_should_update_own_page_and_sanitize(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(author_id=MEMBER_ID))

        # when
        result = await service.update_page(
            PROJECT_ID,
            1,
            MEMBER_ID,
            WikiPageUpdate(title="Заголовок", content='<p>hi</p><img src=x onerror="alert(1)">'),
        )

        # then
        assert result.title == "Заголовок"
        assert "onerror" not in result.content
        wiki_repo.uow.session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_should_reread_page_after_flush(self):
        # given — после flush ORM expire'ит атрибуты, и page.author попытался бы
        # загрузиться лениво: в async это MissingGreenlet. Поэтому ответ строится
        # из повторного чтения, а не из pre-flush инстанса.
        service, wiki_repo = _make()
        stale = _page(author_id=LEAD_ID, title="Pre-flush")
        fresh = _page(author_id=LEAD_ID, title="После flush")
        wiki_repo.get_with_author = AsyncMock(side_effect=[stale, fresh])

        # when
        result = await service.update_page(PROJECT_ID, 1, LEAD_ID, WikiPageUpdate(title="После flush"))

        # then
        assert wiki_repo.get_with_author.await_count == 2
        assert result.title == "После flush"

    @pytest.mark.asyncio
    async def test_should_keep_unspecified_fields_untouched(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(
            return_value=_page(author_id=LEAD_ID, title="Старый", content="<p>старое</p>")
        )

        # when
        result = await service.update_page(PROJECT_ID, 1, LEAD_ID, WikiPageUpdate(title="Новый"))

        # then
        assert result.title == "Новый"
        assert result.content == "<p>старое</p>"
        assert result.visibility == "private"

    @pytest.mark.asyncio
    async def test_should_reject_visibility_change_by_ordinary_member(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(author_id=LEAD_ID, visibility="private"))
        service._can_edit = AsyncMock(return_value=True)  # type: ignore[method-assign]
        service._can_change_visibility = AsyncMock(return_value=False)  # type: ignore[method-assign]

        # when / then
        with pytest.raises(PermissionError):
            await service.update_page(PROJECT_ID, 1, MEMBER_ID, WikiPageUpdate(visibility="public"))

    @pytest.mark.asyncio
    async def test_should_allow_teacher_to_publish_private_page(self):
        # given — teacher не автор страницы, но у него есть право публикации
        service, wiki_repo = _make(editor=True)
        wiki_repo.get_with_author = AsyncMock(return_value=_page(author_id=MEMBER_ID, visibility="private"))
        service._can_change_visibility = AsyncMock(return_value=True)  # type: ignore[method-assign]

        # when
        result = await service.update_page(PROJECT_ID, 1, TEACHER_ID, WikiPageUpdate(visibility="public"))

        # then
        assert result.visibility == "public"

    @pytest.mark.asyncio
    async def test_should_reject_self_as_parent(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(page_id=5))

        # when / then
        with pytest.raises(ValidationError):
            await service.update_page(PROJECT_ID, 5, LEAD_ID, WikiPageUpdate(parent_id=5))

    @pytest.mark.asyncio
    async def test_should_reject_nesting_into_own_descendant(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(page_id=5))
        wiki_repo.get_by_id = AsyncMock(return_value=_page(page_id=9))
        wiki_repo.is_descendant = AsyncMock(return_value=True)

        # when / then
        with pytest.raises(ValidationError):
            await service.update_page(PROJECT_ID, 5, LEAD_ID, WikiPageUpdate(parent_id=9))

    @pytest.mark.asyncio
    async def test_should_reject_reparent_to_unknown_page(self):
        # given — иначе FK parent_id уронил бы flush на уровне БД
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(page_id=5))
        wiki_repo.get_by_id = AsyncMock(return_value=None)

        # when / then
        with pytest.raises(NotFoundError):
            await service.update_page(PROJECT_ID, 5, LEAD_ID, WikiPageUpdate(parent_id=9))

    @pytest.mark.asyncio
    async def test_should_reparent_page(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(page_id=5, parent_id=None))
        wiki_repo.get_by_id = AsyncMock(return_value=_page(page_id=9))
        wiki_repo.is_descendant = AsyncMock(return_value=False)

        # when
        result = await service.update_page(PROJECT_ID, 5, LEAD_ID, WikiPageUpdate(parent_id=9))

        # then
        assert result.parent_id == 9

    @pytest.mark.asyncio
    async def test_should_detach_page_when_parent_omitted(self):
        # given — parent_id=None передан явно, а не «не указан»
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(page_id=5, parent_id=9))

        # when
        result = await service.update_page(PROJECT_ID, 5, LEAD_ID, WikiPageUpdate(parent_id=None))

        # then
        assert result.parent_id is None

    @pytest.mark.asyncio
    async def test_should_delete_descendants_before_page(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(page_id=1, author_id=LEAD_ID))
        wiki_repo.get_subtree_ids = AsyncMock(return_value=[2, 3])
        wiki_repo.get_by_id = AsyncMock(side_effect=[_page(page_id=3, parent_id=2), _page(page_id=2, parent_id=1)])

        # when
        result = await service.delete_page(PROJECT_ID, 1, LEAD_ID)

        # then
        assert result is True
        # Потомки идут раньше родителя: внешний ключ parent_id без
        # ON DELETE CASCADE заставил бы Postgres отклонить удаление.
        assert [call.args[0].id for call in wiki_repo.uow.session.delete.await_args_list] == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_should_skip_already_removed_descendant(self):
        # given — страница исчезла между выборкой поддерева и удалением
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(page_id=1, author_id=LEAD_ID))
        wiki_repo.get_subtree_ids = AsyncMock(return_value=[2])
        wiki_repo.get_by_id = AsyncMock(return_value=None)

        # when
        result = await service.delete_page(PROJECT_ID, 1, LEAD_ID)

        # then
        assert result is True
        assert [call.args[0].id for call in wiki_repo.uow.session.delete.await_args_list] == [1]

    @pytest.mark.asyncio
    async def test_should_reject_delete_by_outsider(self):
        # given
        service, wiki_repo = _make()
        wiki_repo.get_with_author = AsyncMock(return_value=_page(author_id=LEAD_ID))
        service._can_edit = AsyncMock(return_value=False)  # type: ignore[method-assign]

        # when / then
        with pytest.raises(PermissionError):
            await service.delete_page(PROJECT_ID, 1, OUTSIDER_ID)
