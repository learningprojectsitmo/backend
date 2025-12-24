from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.model.models import Project
from src.repository.project_repository import ProjectRepository
from src.schema.project import ProjectCreate, ProjectUpdate
from src.services.project_service import ProjectService

# Константы для тестов
EXPECTED_PROJECTS_COUNT = 2


class TestProjectService:
    """Тесты для ProjectService"""

    @pytest.mark.asyncio
    async def test_should_create_project_with_valid_data(self):
        """Тест должен создать проект с корректными данными"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_project = Project(id=1, name="Test Project", description="Test Description", author_id=1)
        mock_repository.create.return_value = mock_project

        project_service = ProjectService(mock_repository)

        project_data = ProjectCreate(name="Test Project", description="Test Description", author_id=1)

        # when
        result = await project_service.create_project(project_data, author_id=1)

        # then
        assert result == mock_project
        mock_repository.create.assert_called_once_with(project_data)

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
    async def test_should_update_project_with_valid_data(self):
        """Тест должен обновить проект с корректными данными"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        # Мокаем проект с правильным author_id для проверки авторства
        mock_project = Project(id=1, name="Test Project", description="Test Description", author_id=1)
        mock_repository.get_by_id.return_value = mock_project

        updated_project = Project(id=1, name="Updated Project", description="Updated Description", author_id=1)
        mock_repository.update.return_value = updated_project

        project_service = ProjectService(mock_repository)

        update_data = ProjectUpdate(name="Updated Project", description="Updated Description")

        # when
        result = await project_service.update_project(1, update_data, current_user_id=1)

        # then
        assert result == updated_project
        mock_repository.get_by_id.assert_called_once_with(1)
        mock_repository.update.assert_called_once_with(1, update_data)

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

    @pytest.mark.asyncio
    async def test_should_get_projects_paginated(self):
        """Тест должен получить проекты с пагинацией"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_projects = [
            Project(id=1, name="Project 1", description="Description 1", author_id=1),
            Project(id=2, name="Project 2", description="Description 2", author_id=1),
        ]
        mock_repository.get_multi.return_value = mock_projects
        mock_repository.count.return_value = 2

        project_service = ProjectService(mock_repository)

        # when
        projects, total = await project_service.get_projects_paginated(page=1, limit=10)

        # then
        assert projects == mock_projects
        assert total == EXPECTED_PROJECTS_COUNT
        assert len(projects) == EXPECTED_PROJECTS_COUNT
        mock_repository.get_multi.assert_called_once_with(skip=0, limit=10)
        mock_repository.count.assert_called_once()
