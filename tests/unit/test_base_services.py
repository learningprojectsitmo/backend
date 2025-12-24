from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.services.base_service import BaseService

# Константы для тестов
EXPECTED_OBJECTS_COUNT = 2
EXPECTED_TOTAL_COUNT = 42
EXPECTED_PAGE_SIZE = 10
EXPECTED_TOTAL_PAGES = 1


class MockModel:
    def __init__(self, id, name):
        self.id = id
        self.name = name


class MockCreateSchema:
    def __init__(self, name):
        self.name = name


class MockUpdateSchema:
    def __init__(self, name):
        self.name = name


class TestBaseService:
    """Тесты для BaseService"""

    @pytest.mark.asyncio
    async def test_should_get_by_id(self):
        """Тест должен получить объект по ID"""
        # given
        mock_repository = AsyncMock()
        mock_object = MockModel(id=1, name="Test Object")
        mock_repository.get_by_id.return_value = mock_object

        base_service = BaseService(mock_repository)

        # when
        result = await base_service.get_by_id(1)

        # then
        assert result == mock_object
        mock_repository.get_by_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_get_multiple_objects(self):
        """Тест должен получить несколько объектов"""
        # given
        mock_repository = AsyncMock()
        mock_objects = [MockModel(id=1, name="Object 1"), MockModel(id=2, name="Object 2")]
        mock_repository.get_multi.return_value = mock_objects

        base_service = BaseService(mock_repository)

        # when
        result = await base_service.get_multi(skip=0, limit=10)

        # then
        assert result == mock_objects
        assert len(result) == EXPECTED_OBJECTS_COUNT
        mock_repository.get_multi.assert_called_once_with(skip=0, limit=10)

    @pytest.mark.asyncio
    async def test_should_create_object(self):
        """Тест должен создать объект"""
        # given
        mock_repository = AsyncMock()
        mock_object = MockModel(id=1, name="New Object")
        mock_repository.create.return_value = mock_object

        base_service = BaseService(mock_repository)

        create_data = MockCreateSchema(name="New Object")

        # when
        result = await base_service.create(create_data)

        # then
        assert result == mock_object
        mock_repository.create.assert_called_once_with(create_data)

    @pytest.mark.asyncio
    async def test_should_update_object(self):
        """Тест должен обновить объект"""
        # given
        mock_repository = AsyncMock()
        updated_object = MockModel(id=1, name="Updated Object")
        mock_repository.update.return_value = updated_object

        base_service = BaseService(mock_repository)

        update_data = MockUpdateSchema(name="Updated Object")

        # when
        result = await base_service.update(1, update_data)

        # then
        assert result == updated_object
        mock_repository.update.assert_called_once_with(1, update_data)

    @pytest.mark.asyncio
    async def test_should_delete_object(self):
        """Тест должен удалить объект"""
        # given
        mock_repository = AsyncMock()
        mock_repository.delete.return_value = True

        base_service = BaseService(mock_repository)

        # when
        result = await base_service.delete(1)

        # then
        assert result is True
        mock_repository.delete.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_count_objects(self):
        """Тест должен подсчитать количество объектов"""
        # given
        mock_repository = AsyncMock()
        mock_repository.count.return_value = 42

        base_service = BaseService(mock_repository)

        # when
        result = await base_service.count()

        # then
        assert result == EXPECTED_TOTAL_COUNT
        mock_repository.count.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_get_paginated_results(self):
        """Тест должен получить результаты с пагинацией"""
        # given
        mock_repository = AsyncMock()
        mock_objects = [MockModel(id=1, name="Object 1"), MockModel(id=2, name="Object 2")]
        mock_repository.get_multi.return_value = mock_objects
        mock_repository.count.return_value = 2

        base_service = BaseService(mock_repository)

        # when
        result = await base_service.get_paginated(page=1, page_size=10)

        # then
        assert "items" in result
        assert "total" in result
        assert "page" in result
        assert "page_size" in result
        assert "total_pages" in result
        assert result["total"] == EXPECTED_OBJECTS_COUNT
        assert result["page"] == 1
        assert result["page_size"] == EXPECTED_PAGE_SIZE
        assert result["total_pages"] == EXPECTED_TOTAL_PAGES
        mock_repository.get_multi.assert_called_once_with(skip=0, limit=10)
        mock_repository.count.assert_called_once()
