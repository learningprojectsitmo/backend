from __future__ import annotations

from unittest.mock import AsyncMock, Mock, call

import pytest

from src.core.exceptions import PermissionError
from src.model.resume import Resume, ResumeWorkspace
from src.repository.resume_repository import ResumeRepository
from src.schema.resume import ResumeCreate, ResumeSpaceAssign, ResumeUpdate
from src.services.resume_service import ResumeService

# Константы для тестов
EXPECTED_RESUMES_COUNT = 2


def _make_repo() -> Mock:
    """Репозиторий с асинхронными методами, задействованными сервисом."""
    repo = Mock(spec=ResumeRepository)
    repo.uow = Mock()
    repo.uow.session = Mock()
    repo.uow.session.flush = AsyncMock()
    repo.uow.session.delete = Mock()
    repo.count_by_author_id = AsyncMock(return_value=EXPECTED_RESUMES_COUNT)
    repo.get_member_workspace_names = AsyncMock(return_value={})
    repo.get_workspace_names = AsyncMock(return_value={})
    repo.get_space_links = AsyncMock(return_value={})
    repo.get_default_space_links = AsyncMock(return_value=[])
    repo.has_space_default = AsyncMock(return_value=False)
    repo.unset_other_space_defaults = AsyncMock(return_value=0)
    repo.clear_space_default = AsyncMock()
    repo.set_space_default = AsyncMock()
    repo.get_space_default_candidate_id = AsyncMock(return_value=None)
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
        mock_resume = Resume(id=1, header="Senior Developer", resume_text="Experienced Python developer", author_id=1)
        mock_repository.create = AsyncMock(return_value=mock_resume)

        resume_service = ResumeService(mock_repository)

        resume_data = ResumeCreate(header="Senior Developer", resume_text="Experienced Python developer", author_id=1)

        # when
        result = await resume_service.create_resume(resume_data, author_id=1)

        # then
        assert result == mock_resume
        # В репозиторий уходит dict: поле spaces не является колонкой resume.
        payload = mock_repository.create.await_args.args[0]
        assert isinstance(payload, dict)
        assert payload["header"] == "Senior Developer"
        assert "spaces" not in payload

    @pytest.mark.asyncio
    async def test_should_assign_spaces_on_create(self):
        """Резюме при создании назначается на пространства автора"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=7, header="Junior", author_id=1, is_visible=True)
        mock_repository.create = AsyncMock(return_value=mock_resume)
        mock_repository.get_member_workspace_names = AsyncMock(return_value={1: "Альфа"})

        resume_service = ResumeService(mock_repository)
        resume_data = ResumeCreate(
            header="Junior",
            author_id=1,
            is_visible=True,
            spaces=[ResumeSpaceAssign(workspace_id=1, is_default=True)],
        )

        # when
        result = await resume_service.create_resume(resume_data, author_id=1)

        # then
        assert result == mock_resume
        mock_repository.get_member_workspace_names.assert_awaited_once_with(1, [1])
        # Переключение «основное» снимает флаг с остальных резюме автора
        # в пространстве ДО записи нового (uq_rw_author_workspace_default).
        mock_repository.unset_other_space_defaults.assert_awaited_once_with(1, 1, keep_resume_id=7)

    @pytest.mark.asyncio
    async def test_should_reject_spaces_where_author_is_not_member(self):
        """Назначение резюме в пространство без членства запрещено"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=7, header="Junior", author_id=1, is_visible=True)
        mock_repository.create = AsyncMock(return_value=mock_resume)
        mock_repository.get_member_workspace_names = AsyncMock(return_value={})
        mock_repository.get_workspace_names = AsyncMock(return_value={99: "Чужое"})

        resume_service = ResumeService(mock_repository)
        resume_data = ResumeCreate(
            header="Junior",
            author_id=1,
            spaces=[ResumeSpaceAssign(workspace_id=99)],
        )

        # when & then
        with pytest.raises(ValueError, match="не являетесь их участником: Чужое"):
            await resume_service.create_resume(resume_data, author_id=1)

        mock_repository.set_space_default.assert_not_awaited()

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
        mock_repository.update.assert_called_once_with(
            1, {"header": "Updated Senior Developer", "resume_text": "Updated description"}
        )
        # Без spaces и is_visible менять назначения пространств не нужно.
        mock_repository.get_space_links.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_switch_space_default_when_assigning(self):
        """Явное назначение is_default снимает признак с остальных резюме автора в пространстве"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_visible=True)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.update.return_value = mock_resume
        mock_repository.get_member_workspace_names = AsyncMock(return_value={1: "Альфа"})
        link = ResumeWorkspace(id=10, resume_id=5, workspace_id=1, author_id=1, is_default=False)
        mock_repository.get_space_links = AsyncMock(return_value={1: link})

        resume_service = ResumeService(mock_repository)

        # when
        await resume_service.update_resume(
            5,
            ResumeUpdate(spaces=[ResumeSpaceAssign(workspace_id=1, is_default=True)]),
            current_user_id=1,
        )

        # then
        # Порядок критичен: снять чужие флаги нужно до записи нового, иначе
        # uq_rw_author_workspace_default увидит две строки is_default = true.
        mock_repository.unset_other_space_defaults.assert_awaited_once_with(1, 1, keep_resume_id=5)
        assert link.is_default is True
        # Явно назначили основное — восстановление основного не требуется.
        mock_repository.has_space_default.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_reassign_space_default_when_unassigning(self):
        """Снятие is_default переносит признак на другое видимое резюме пространства"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_visible=True)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.update.return_value = mock_resume
        mock_repository.get_member_workspace_names = AsyncMock(return_value={1: "Альфа"})
        link = ResumeWorkspace(id=10, resume_id=5, workspace_id=1, author_id=1, is_default=True)
        mock_repository.get_space_links = AsyncMock(return_value={1: link})
        mock_repository.get_space_default_candidate_id = AsyncMock(return_value=3)

        resume_service = ResumeService(mock_repository)

        # when
        await resume_service.update_resume(
            5,
            ResumeUpdate(spaces=[ResumeSpaceAssign(workspace_id=1, is_default=False)]),
            current_user_id=1,
        )

        # then
        # Именно clear_space_default, а не unset_other_space_defaults: тот
        # исключает keep_resume_id и оставил бы флаг на снимаемом резюме.
        mock_repository.clear_space_default.assert_awaited_once_with(5, 1)
        mock_repository.unset_other_space_defaults.assert_not_awaited()
        mock_repository.has_space_default.assert_awaited_once_with(1, 1)
        mock_repository.get_space_default_candidate_id.assert_awaited_once_with(1, 1, exclude_id=5, visible_only=True)
        mock_repository.set_space_default.assert_awaited_once_with(3, 1)
        assert link.is_default is False

    @pytest.mark.asyncio
    async def test_should_move_default_when_hiding_default_resume(self):
        """Скрытие основного резюме переносит признак на другое видимое в пространстве"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_visible=True)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.get_default_space_links = AsyncMock(
            return_value=[ResumeWorkspace(id=10, resume_id=5, workspace_id=1, author_id=1, is_default=True)]
        )
        mock_repository.get_workspace_names = AsyncMock(return_value={1: "Альфа"})
        mock_repository.get_space_default_candidate_id = AsyncMock(return_value=3)
        mock_repository.update.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        # when
        await resume_service.update_resume(5, ResumeUpdate(is_visible=False), current_user_id=1)

        # then
        mock_repository.get_space_default_candidate_id.assert_awaited_once_with(1, 1, exclude_id=5, visible_only=True)
        mock_repository.clear_space_default.assert_awaited_once_with(5, 1)
        mock_repository.set_space_default.assert_awaited_once_with(3, 1)
        payload = mock_repository.update.await_args.args[1]
        assert payload == {"is_visible": False}

    @pytest.mark.asyncio
    async def test_should_forbid_hiding_the_only_visible_resume(self):
        """Скрыть единственное видимое основное резюме нельзя — иначе карточка исчезнет"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1, is_visible=True)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.get_default_space_links = AsyncMock(
            return_value=[ResumeWorkspace(id=10, resume_id=5, workspace_id=1, author_id=1, is_default=True)]
        )
        mock_repository.get_workspace_names = AsyncMock(return_value={1: "Альфа"})
        mock_repository.get_space_default_candidate_id = AsyncMock(return_value=None)

        resume_service = ResumeService(mock_repository)

        # when & then
        with pytest.raises(ValueError, match="Нельзя скрыть резюме: оно является основным в пространствах: Альфа"):
            await resume_service.update_resume(5, ResumeUpdate(is_visible=False), current_user_id=1)

        # Ни один перенос не выполнен — сначала проверяем все пространства.
        mock_repository.clear_space_default.assert_not_awaited()
        mock_repository.set_space_default.assert_not_awaited()
        mock_repository.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_promote_next_resume_after_deleting_default(self):
        """Удаление основного резюме не должно оставлять автора без основного"""
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.get_default_space_links = AsyncMock(
            return_value=[ResumeWorkspace(id=10, resume_id=5, workspace_id=1, author_id=1, is_default=True)]
        )
        mock_repository.get_space_default_candidate_id = AsyncMock(return_value=3)

        resume_service = ResumeService(mock_repository)

        # when
        result = await resume_service.delete_resume(5, current_user_id=1)

        # then
        assert result is True
        # session.delete() только помечает объект, поэтому до выставления флага
        # кандидату DELETE должен быть отправлен в БД.
        mock_repository.uow.session.flush.assert_awaited()
        mock_repository.set_space_default.assert_awaited_once_with(3, 1)

    @pytest.mark.asyncio
    async def test_should_promote_hidden_resume_after_deleting_default_if_no_visible_left(self):
        # given
        # Видимых резюме не осталось — скрытым основным можно сделать резюме
        # напрямую через API, поэтому это не только теоретический случай.
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1)
        mock_repository.get_by_id.return_value = mock_resume
        mock_repository.get_default_space_links = AsyncMock(
            return_value=[ResumeWorkspace(id=10, resume_id=5, workspace_id=1, author_id=1, is_default=True)]
        )
        mock_repository.get_space_default_candidate_id = AsyncMock(side_effect=[None, 9])

        resume_service = ResumeService(mock_repository)

        # when
        result = await resume_service.delete_resume(5, current_user_id=1)

        # then
        assert result is True
        # Сначала ищем видимого кандидата, и только потом — любого.
        assert mock_repository.get_space_default_candidate_id.await_args_list == [
            call(1, 1, exclude_id=5, visible_only=True),
            call(1, 1, exclude_id=5, visible_only=False),
        ]
        mock_repository.set_space_default.assert_awaited_once_with(9, 1)

    @pytest.mark.asyncio
    async def test_should_not_promote_resume_after_deleting_non_default(self):
        # given
        mock_repository = _make_repo()
        mock_resume = Resume(id=5, header="Backend", author_id=1)
        mock_repository.get_by_id.return_value = mock_resume

        resume_service = ResumeService(mock_repository)

        # when
        await resume_service.delete_resume(5, current_user_id=1)

        # then
        mock_repository.set_space_default.assert_not_awaited()
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
        mock_repository.get_default_space_links = AsyncMock(return_value=[])
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
