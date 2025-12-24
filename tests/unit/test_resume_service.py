from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.core.exceptions import PermissionError
from src.model.models import Resume
from src.repository.resume_repository import ResumeRepository
from src.schema.resume import ResumeCreate, ResumeUpdate
from src.services.resume_service import ResumeService

# Константы для тестов
EXPECTED_RESUMES_COUNT = 2


class TestResumeService:
    """Тесты для ResumeService"""

    @pytest.mark.asyncio
    async def test_should_create_resume_with_valid_data(self):
        """Тест должен создать резюме с корректными данными"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        mock_resume = Resume(id=1, header="Senior Developer", resume_text="Experienced Python developer", author_id=1)
        mock_repository.create.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        resume_data = ResumeCreate(header="Senior Developer", resume_text="Experienced Python developer", author_id=1)

        # when
        result = await resume_service.create_resume(resume_data, author_id=1)

        # then
        assert result == mock_resume
        mock_repository.create.assert_called_once_with(resume_data)

    @pytest.mark.asyncio
    async def test_should_get_resume_by_id(self):
        """Тест должен получить резюме по ID"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        mock_resume = Resume(id=1, header="Senior Developer", resume_text="Experienced Python developer", author_id=1)
        mock_repository.get_by_id.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        # when
        result = await resume_service.get_resume_by_id(1)

        # then
        assert result == mock_resume
        mock_repository.get_by_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_return_none_for_nonexistent_resume(self):
        """Тест должен вернуть None для несуществующего резюме"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        mock_repository.get_by_id.return_value = None

        resume_service = ResumeService(mock_repository)

        # when
        result = await resume_service.get_resume_by_id(999)

        # then
        assert result is None
        mock_repository.get_by_id.assert_called_once_with(999)

    @pytest.mark.asyncio
    async def test_should_update_resume_by_author(self):
        """Тест должен обновить резюме автором"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        # Мокаем резюме с правильным author_id для проверки авторства
        mock_resume = Resume(id=1, header="Senior Developer", resume_text="Experienced Python developer", author_id=1)
        mock_repository.get_by_id.return_value = mock_resume

        updated_resume = Resume(id=1, header="Updated Senior Developer", resume_text="Updated description", author_id=1)
        mock_repository.update.return_value = updated_resume

        resume_service = ResumeService(mock_repository)

        update_data = ResumeUpdate(header="Updated Senior Developer", resume_text="Updated description")

        # when
        result = await resume_service.update_resume(1, update_data, current_user_id=1)

        # then
        assert result == updated_resume
        mock_repository.get_by_id.assert_called_once_with(1)
        mock_repository.update.assert_called_once_with(1, update_data)

    @pytest.mark.asyncio
    async def test_should_prevent_update_resume_by_non_author(self):
        """Тест должен предотвратить обновление резюме неавтором"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        # Мокаем резюме с author_id=1, а тест пытается обновить с current_user_id=2
        mock_resume = Resume(id=1, header="Senior Developer", resume_text="Experienced Python developer", author_id=1)
        mock_repository.get_by_id.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        update_data = ResumeUpdate(header="Unauthorized Update", resume_text="Should not be updated")

        # when & then
        with pytest.raises(PermissionError, match="Only author can update resume"):
            await resume_service.update_resume(1, update_data, current_user_id=2)

    @pytest.mark.asyncio
    async def test_should_delete_resume_by_author(self):
        """Тест должен удалить резюме автором"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        # Мокаем резюме с правильным author_id для проверки авторства
        mock_resume = Resume(id=1, header="Senior Developer", resume_text="Experienced Python developer", author_id=1)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.delete.return_value = True

        resume_service = ResumeService(mock_repository)

        # when
        result = await resume_service.delete_resume(1, current_user_id=1)

        # then
        assert result is True
        mock_repository.get_by_id.assert_called_once_with(1)
        mock_repository.delete.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_prevent_delete_resume_by_non_author(self):
        """Тест должен предотвратить удаление резюме неавтором"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        # Мокаем резюме с author_id=1, а тест пытается удалить с current_user_id=2
        mock_resume = Resume(id=1, header="Senior Developer", resume_text="Experienced Python developer", author_id=1)
        mock_repository.get_by_id.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        # when & then
        with pytest.raises(PermissionError, match="Only author can delete resume"):
            await resume_service.delete_resume(1, current_user_id=2)

    @pytest.mark.asyncio
    async def test_should_get_resumes_by_author(self):
        """Тест должен получить резюме пользователя"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        mock_resumes = [
            Resume(id=1, header="Developer Resume", author_id=1),
            Resume(id=2, header="Senior Developer Resume", author_id=1),
        ]
        mock_repository.get_by_author_id.return_value = mock_resumes

        resume_service = ResumeService(mock_repository)

        # when
        result = await resume_service.get_resumes_by_author(1)

        # then
        assert result == mock_resumes
        assert len(result) == EXPECTED_RESUMES_COUNT
        mock_repository.get_by_author_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_get_public_resumes(self):
        """Тест должен получить публичные резюме"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        mock_public_resumes = [
            Resume(id=1, header="Public Resume 1", author_id=1),
            Resume(id=2, header="Public Resume 2", author_id=2),
        ]
        # Метод get_public_resumes не существует, используем get_multi
        mock_repository.get_multi.return_value = mock_public_resumes

        resume_service = ResumeService(mock_repository)

        # when
        result = await resume_service.get_multi()

        # then
        assert result == mock_public_resumes
        assert len(result) == EXPECTED_RESUMES_COUNT
        mock_repository.get_multi.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_get_resumes_paginated(self):
        """Тест должен получить резюме с пагинацией"""
        # given
        mock_repository = Mock(spec=ResumeRepository)
        mock_resumes = [Resume(id=1, header="Resume 1", author_id=1), Resume(id=2, header="Resume 2", author_id=2)]
        mock_repository.get_multi.return_value = mock_resumes
        mock_repository.count.return_value = 2

        resume_service = ResumeService(mock_repository)

        # when
        resumes, total = await resume_service.get_resumes_paginated(page=1, limit=10)

        # then
        assert resumes == mock_resumes
        assert total == EXPECTED_RESUMES_COUNT
        assert len(resumes) == EXPECTED_RESUMES_COUNT
        mock_repository.get_multi.assert_called_once_with(skip=0, limit=10)
        mock_repository.count.assert_called_once()
