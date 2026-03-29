from __future__ import annotations

from unittest.mock import AsyncMock, Mock  # Добавили AsyncMock

import pytest

from src.model.models import Project
from src.repository.project_repository import ProjectRepository
from src.schema.project import ProjectCreate, ProjectUpdate
from src.services.project_service import ProjectService

EXPECTED_PROJECTS_COUNT = 2

class TestProjectService:
    """Тесты для ProjectService"""

    def _setup_mock_repo(self):
        """Вспомогательный метод для настройки мока репозитория с UOW"""
        mock_repo = Mock(spec=ProjectRepository)
        # Имитируем структуру self._project_repository.uow.session
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repo.uow = mock_uow
        return mock_repo

    @pytest.mark.asyncio
    async def test_should_create_project_with_valid_data(self):
        # given
        mock_repository = self._setup_mock_repo()
        mock_project = Project(id=1, name="Test Project", author_id=1)


        mock_repository.create.return_value = mock_project
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test Project", author_id=1)

        # when
        result = await project_service.create_project(project_data, author_id=1)

        # then
        assert result == mock_project

        payload = project_data.model_dump(exclude_none=True)
        payload.pop("tags", None)
        mock_repository.create.assert_called_once_with(payload)

    @pytest.mark.asyncio
    async def test_should_update_project_with_valid_data(self):
        # given
        mock_repository = self._setup_mock_repo()

        existing_project = Project(id=1, name="Old Name", author_id=1)
        mock_repository.get_by_id.return_value = existing_project

        updated_project = Project(id=1, name="Updated Project", author_id=1)
        mock_repository.update.return_value = updated_project
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        project_service = ProjectService(mock_repository)
        update_data = ProjectUpdate(name="Updated Project")

        # when
        result = await project_service.update_project(1, update_data, current_user_id=1)

        # then
        assert result == updated_project
        mock_repository.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_get_projects_paginated(self):
        # given
        mock_repository = self._setup_mock_repo()
        mock_projects = [
            Project(id=1, name="P1", author_id=1, participants=[], status=None),
            Project(id=2, name="P2", author_id=1, participants=[], status=None),
        ]

        mock_repository.get_projects_with_details.return_value = mock_projects
        mock_repository.count.return_value = 2

        project_service = ProjectService(mock_repository)

        # when
        projects, total = await project_service.get_projects_paginated(page=1, limit=10)

        # then
        assert len(projects) == EXPECTED_PROJECTS_COUNT
        assert total == EXPECTED_PROJECTS_COUNT
        mock_repository.get_projects_with_details.assert_called_once_with(skip=0, limit=10)

    @pytest.mark.asyncio
    async def test_should_get_project_by_id(self):
        """Тест должен получить проект по ID"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_project = Project(id=1, name="Test Project", description="Test Description", author_id=1)
        mock_repository.get_by_id.return_value = mock_project

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.get_project_by_id(1)

        # then
        assert result == mock_project
        mock_repository.get_by_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_return_none_for_nonexistent_project(self):
        """Тест должен вернуть None для несуществующего проекта"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_repository.get_by_id.return_value = None

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.get_project_by_id(999)

        # then
        assert result is None
        mock_repository.get_by_id.assert_called_once_with(999)

    @pytest.mark.asyncio
    async def test_should_delete_project_successfully(self):
        """Тест должен успешно удалить проект"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        # Мокаем проект с правильным author_id для проверки авторства
        mock_project = Project(id=1, name="Test Project", description="Test Description", author_id=1)
        mock_repository.get_by_id.return_value = mock_project
        mock_repository.delete.return_value = True

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.delete_project(1, current_user_id=1)

        # then
        assert result is True
        mock_repository.get_by_id.assert_called_once_with(1)
        mock_repository.delete.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_get_projects_by_author(self):
        """Тест должен получить проекты по автору"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_projects = [
            Project(id=1, name="Project 1", description="Description 1", author_id=1),
            Project(id=2, name="Project 2", description="Description 2", author_id=1),
        ]
        mock_repository.get_by_author_id.return_value = mock_projects

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.get_projects_by_author(1)

        # then
        assert result == mock_projects
        assert len(result) == EXPECTED_PROJECTS_COUNT
        mock_repository.get_by_author_id.assert_called_once_with(1)
