from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from src.model.project import Project, ProjectStatus
from src.model.user import Role, User
from src.model.workspace import WorkSpace
from src.services.search_service import SearchService


def _make_service() -> tuple[SearchService, Mock, Mock, Mock]:
    project_service = Mock()
    project_service.search_projects_by_text = AsyncMock(return_value=[])
    workspace_service = Mock()
    workspace_service.search_spaces_by_text = AsyncMock(return_value=[])
    user_service = Mock()
    user_service.search_users_by_text = AsyncMock(return_value=[])

    service = SearchService(project_service, workspace_service, user_service)
    return service, project_service, workspace_service, user_service


def _project(project_id: int, name: str, workspace_id: int = 3) -> Project:
    project = Project(
        id=project_id,
        name=name,
        description=f"Описание {name}",
        workspace_id=workspace_id,
        theme=None,
        progress=42,
    )
    project.workspace = WorkSpace(id=workspace_id, name="Комната 113", author_id=1, status_id=1)
    project.status = ProjectStatus(id=1, name="active")
    return project


def _user(user_id: int, last_name: str) -> User:
    user = User(
        id=user_id,
        email=f"user{user_id}@example.com",
        first_name="Иван",
        middle_name="Иванович",
        last_name=last_name,
        phone=None,
    )
    user.role = Role(id=2, name="student")
    return user


async def test_search_empty_query_returns_empty_and_skips_repositories() -> None:
    # given
    service, project_service, workspace_service, user_service = _make_service()

    # when
    result = await service.search("   ", user_id=1)

    # then
    assert result.projects == []
    assert result.spaces == []
    assert result.users == []
    project_service.search_projects_by_text.assert_not_awaited()
    workspace_service.search_spaces_by_text.assert_not_awaited()
    user_service.search_users_by_text.assert_not_awaited()


async def test_search_short_query_returns_empty() -> None:
    # given
    service, project_service, workspace_service, user_service = _make_service()

    # when
    result = await service.search("а", user_id=1)

    # then
    assert result.projects == []
    assert result.spaces == []
    assert result.users == []
    project_service.search_projects_by_text.assert_not_awaited()
    workspace_service.search_spaces_by_text.assert_not_awaited()
    user_service.search_users_by_text.assert_not_awaited()


async def test_search_maps_visible_projects() -> None:
    # given
    service, project_service, workspace_service, user_service = _make_service()
    project_service.search_projects_by_text = AsyncMock(return_value=[_project(1, "Хакатон"), _project(2, "Стартап")])
    workspace_service.search_spaces_by_text = AsyncMock(return_value=[])
    user_service.search_users_by_text = AsyncMock(return_value=[])

    # when
    result = await service.search("хак", user_id=1, project_limit=5)

    # then
    assert len(result.projects) == 2
    first = result.projects[0]
    assert first.id == 1
    assert first.name == "Хакатон"
    assert first.description == "Описание Хакатон"
    assert first.workspace_id == 3
    assert first.workspace_name == "Комната 113"
    assert first.status == "active"
    assert first.progress == 42
    project_service.search_projects_by_text.assert_awaited_once_with("хак", limit=5, viewer_id=1)


async def test_search_maps_visible_spaces() -> None:
    # given
    service, project_service, workspace_service, user_service = _make_service()
    project_service.search_projects_by_text = AsyncMock(return_value=[])
    workspace_service.search_spaces_by_text = AsyncMock(
        return_value=[
            {
                "id": 7,
                "title": "Хакерспейс",
                "description": "Пространство",
                "category": "IT",
                "projects_count": 3,
                "members_count": 12,
            }
        ]
    )
    user_service.search_users_by_text = AsyncMock(return_value=[])

    # when
    result = await service.search("хак", user_id=1, space_limit=4)

    # then
    assert len(result.spaces) == 1
    space = result.spaces[0]
    assert space.id == 7
    assert space.title == "Хакерспейс"
    assert space.category == "IT"
    assert space.projects_count == 3
    assert space.members_count == 12
    workspace_service.search_spaces_by_text.assert_awaited_once_with("хак", 1, limit=4)


async def test_search_maps_users() -> None:
    # given
    service, project_service, workspace_service, user_service = _make_service()
    project_service.search_projects_by_text = AsyncMock(return_value=[])
    workspace_service.search_spaces_by_text = AsyncMock(return_value=[])
    user_service.search_users_by_text = AsyncMock(return_value=[_user(9, "Петров"), _user(10, "Сидоров")])

    # when
    result = await service.search("пет", user_id=1, user_limit=8)

    # then
    assert len(result.users) == 2
    first = result.users[0]
    assert first.id == 9
    assert first.last_name == "Петров"
    assert first.first_name == "Иван"
    assert first.middle_name == "Иванович"
    assert first.email == "user9@example.com"
    assert first.role == "student"
    user_service.search_users_by_text.assert_awaited_once_with("пет", limit=8)


async def test_search_trims_query() -> None:
    # given
    service, project_service, workspace_service, user_service = _make_service()

    # when
    await service.search("  хак  ", user_id=1)

    # then
    project_service.search_projects_by_text.assert_awaited_once_with("хак", limit=5, viewer_id=1)
    workspace_service.search_spaces_by_text.assert_awaited_once_with("хак", 1, limit=5)
    user_service.search_users_by_text.assert_awaited_once_with("хак", limit=10)
