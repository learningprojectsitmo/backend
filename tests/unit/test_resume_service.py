from __future__ import annotations

from unittest.mock import AsyncMock, Mock, call

import pytest

from src.core.exceptions import PermissionError
from src.model.resume import Resume
from src.repository.resume_repository import ResumeRepository
from src.schema.resume import ResumeCreate, ResumeUpdate
from src.services.resume_service import ResumeService

# Константы для тестов
EXPECTED_RESUMES_COUNT = 2


def _make_repo() -> Mock:
    """Репозиторий с асинхронными методами, задействованными сервисом."""
    repo = Mock(spec=ResumeRepository)
    repo.uow = Mock()
    repo.uow.session = Mock()
    repo.uow.session.flush = AsyncMock()
    repo.count_by_author_id = AsyncMock(return_value=EXPECTED_RESUMES_COUNT)
    repo.set_default = AsyncMock()
    repo.unset_other_defaults = AsyncMock(return_value=0)
    repo.clear_default = AsyncMock()
    repo.get_next_default_candidate_id = AsyncMock(return_value=None)
    repo.get_by_id = AsyncMock()
    repo.create = AsyncMock()
    repo.update = AsyncMock()
    repo.delete = AsyncMock(return_value=True)
    return repo


class TestResumeService:
    """Тесты для ResumeService"""

    @pytest.mark.asyncio
    async def test_should_create_resume_with_valid_data(self):
        """Тест должен создать резюме с корректными данными"""
        # given
        mock_repository = Mock()
        mock_repository.uow = Mock()
        mock_repository.uow.session = Mock()
        mock_repository.uow.session.flush = AsyncMock()
        mock_repository.count_by_author_id = AsyncMock(return_value=EXPECTED_RESUMES_COUNT)
        mock_repository.set_default = AsyncMock()
        mock_resume = Resume(id=1, header="Senior Developer", resume_text="Experienced Python developer", author_id=1)
        mock_repository.create = AsyncMock(return_value=mock_resume)

        resume_service = ResumeService(mock_repository)

        resume_data = ResumeCreate(header="Senior Developer", resume_text="Experienced Python developer", author_id=1)

        # when
        result = await resume_service.create_resume(resume_data, author_id=1)

        # then
        assert result == mock_resume
        mock_repository.create.assert_called_once_with(resume_data)
        # У автора уже есть резюме — новое не становится основным.
        mock_repository.set_default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_make_first_resume_default(self):
        """Первое резюме автора должно автоматически стать основным"""
        # given
        mock_repository = _make_repo()
        mock_repository.count_by_author_id = AsyncMock(return_value=0)
        mock_resume = Resume(id=7, header="Junior", author_id=1)
        mock_repository.create = AsyncMock(return_value=mock_resume)

        resume_service = ResumeService(mock_repository)
        resume_data = ResumeCreate(header="Junior", author_id=1)

        # when
        result = await resume_service.create_resume(resume_data, author_id=1)

        # then
        mock_repository.set_default.assert_awaited_once_with(7)
        assert result.is_default is True

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
        mock_repository = _make_repo()
        # Мокаем резюме с правильным author_id для проверки авторства
        mock_resume = Resume(
            id=1, header="Senior Developer", resume_text="Experienced Python developer", author_id=1, is_default=False
        )
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
        # В репозиторий уходит dict без is_default: признак «основное»
        # меняется мутацией ORM-объекта, а не полем payload.
        mock_repository.update.assert_called_once_with(
            1, {"header": "Updated Senior Developer", "resume_text": "Updated description"}
        )
        mock_repository.set_default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_switch_default_to_another_resume(self):
        """Установка is_default должна снимать признак с остальных резюме автора"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_default=False)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.update.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        # when
        await resume_service.update_resume(5, ResumeUpdate(is_default=True), current_user_id=1)

        # then
        # Порядок критичен: снять чужие флаги нужно до записи нового, иначе
        # uq_resume_author_default увидит два is_default = true у автора.
        mock_repository.unset_other_defaults.assert_awaited_once_with(1, 5)
        assert mock_resume.is_default is True

    @pytest.mark.asyncio
    async def test_should_move_default_when_hiding_default_resume(self):
        """Скрытие основного резюме должно перенести признак на другое видимое"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_default=True, is_visible=True)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.get_next_default_candidate_id.return_value = 3
        mock_repository.update.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        # when
        await resume_service.update_resume(5, ResumeUpdate(is_visible=False), current_user_id=1)

        # then
        mock_repository.get_next_default_candidate_id.assert_awaited_once_with(1, exclude_id=5, visible_only=True)
        # Именно clear_default, а не unset_other_defaults: тот исключает
        # keep_id, то есть оставил бы флаг на скрываемом резюме — и тогда
        # кандидат получил бы второй is_default = true, что ломает
        # uq_resume_author_default (проверено на реальной PostgreSQL).
        mock_repository.clear_default.assert_awaited_once_with(5)
        mock_repository.unset_other_defaults.assert_not_awaited()
        mock_repository.set_default.assert_awaited_once_with(3)
        assert mock_resume.is_default is False
        # is_default не должен попадать в payload: запись False сломала бы индекс.
        payload = mock_repository.update.await_args.args[1]
        assert "is_default" not in payload
        assert payload == {"is_visible": False}

    @pytest.mark.asyncio
    async def test_should_forbid_hiding_the_only_visible_resume(self):
        """Скрыть единственное видимое основное резюме нельзя — иначе карточка исчезнет"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_default=True, is_visible=True)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.get_next_default_candidate_id.return_value = None

        resume_service = ResumeService(mock_repository)

        # when & then
        with pytest.raises(ValueError, match="Нельзя скрыть основное резюме"):
            await resume_service.update_resume(5, ResumeUpdate(is_visible=False), current_user_id=1)

        mock_repository.set_default.assert_not_awaited()
        mock_repository.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_not_allow_removing_the_last_default_flag(self):
        """Снятие признака с основного запрещено: основное должно остаться ровно одно"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_default=True, is_visible=True)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.get_next_default_candidate_id.return_value = None
        mock_repository.update.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        # when & then
        with pytest.raises(ValueError, match="Нельзя снять признак основного"):
            await resume_service.update_resume(5, ResumeUpdate(is_default=False), current_user_id=1)

    @pytest.mark.asyncio
    async def test_should_promote_next_resume_after_deleting_default(self):
        """Удаление основного резюме не должно оставлять автора без основного"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_default=True)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.get_next_default_candidate_id.return_value = 3

        resume_service = ResumeService(mock_repository)

        # when
        result = await resume_service.delete_resume(5, current_user_id=1)

        # then
        assert result is True
        # session.delete() только помечает объект, поэтому до выставления флага
        # кандидату DELETE должен быть отправлен в БД.
        mock_repository.uow.session.flush.assert_awaited()
        mock_repository.set_default.assert_awaited_once_with(3)

    @pytest.mark.asyncio
    async def test_should_promote_hidden_resume_after_deleting_default_if_no_visible_left(self):
        # given
        # Видимых резюме не осталось — скрытым основным можно сделать резюме
        # напрямую через API, поэтому это не только теоретический случай.
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_default=True)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.get_next_default_candidate_id.side_effect = [None, 9]

        resume_service = ResumeService(mock_repository)

        # when
        result = await resume_service.delete_resume(5, current_user_id=1)

        # then
        assert result is True
        # Сначала ищем видимого кандидата, и только потом — любого.
        assert mock_repository.get_next_default_candidate_id.await_args_list == [
            call(1, exclude_id=5, visible_only=True),
            call(1, exclude_id=5, visible_only=False),
        ]
        mock_repository.set_default.assert_awaited_once_with(9)

    @pytest.mark.asyncio
    async def test_should_not_promote_resume_after_deleting_non_default(self):
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_default=False)
        mock_repository.get_by_id.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        # when
        await resume_service.delete_resume(5, current_user_id=1)

        # then
        mock_repository.set_default.assert_not_awaited()
        mock_repository.uow.session.flush.assert_not_awaited()

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
