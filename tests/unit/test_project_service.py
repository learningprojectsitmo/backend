from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock  # Добавили AsyncMock

import pytest

from src.core.exceptions import PermissionError, ValidationError
from src.model.project import Project
from src.model.resume import Resume
from src.model.settings import SpaceSettings
from src.model.user import Role
from src.repository.project_repository import ProjectRepository
from src.repository.resume_repository import ResumeRepository
from src.schema.project import ProjectCreate, ProjectUpdate
from src.services.project_service import ProjectService

EXPECTED_PROJECTS_COUNT = 2
RESPONSE_ID = 10
RESUME_ID = 7


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

        draft_query_result = Mock()
        draft_query_result.scalar_one_or_none.return_value = AsyncMock(id=99, name="draft")
        mock_repository.uow.session.execute = AsyncMock(return_value=draft_query_result)

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test Project", author_id=1)

        # when
        result = await project_service.create_project(project_data, author_id=1)

        # then
        assert result == mock_project

        payload = project_data.model_dump(exclude_none=True)
        payload["status_id"] = 99
        payload.pop("tags", None)
        mock_repository.create.assert_called_once_with(payload)

    @pytest.mark.asyncio
    async def test_should_deny_create_project_in_workspace_for_non_manager(self):
        # given
        mock_repository = self._setup_mock_repo()
        mock_uow = Mock()
        mock_session = Mock()
        mock_result = Mock()
        mock_result.first.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test", author_id=1, workspace_id=5)

        # when / then
        with pytest.raises(PermissionError):
            await project_service.create_project(project_data, author_id=1)
        mock_repository.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_allow_create_project_in_workspace_for_manager(self):
        # given
        mock_repository = self._setup_mock_repo()
        manager_role = Role(id=4, name="manager")
        mock_project = Project(id=1, name="Test Project", author_id=1, workspace_id=5)
        mock_repository.create.return_value = mock_project
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        mock_uow = Mock()
        mock_session = Mock()
        mock_result = Mock()
        mock_result.first.return_value = (object(), manager_role)
        count_result = Mock()
        count_result.scalar_one.return_value = 0
        settings_result = Mock()
        settings_result.scalar_one_or_none.return_value = None
        draft_query_result = Mock()
        draft_query_result.scalar_one_or_none.return_value = AsyncMock(id=99, name="draft")
        ws_sync_result = Mock()
        ws_sync_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(
            side_effect=[mock_result, count_result, settings_result, draft_query_result, ws_sync_result]
        )
        mock_session.refresh = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.add = Mock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test", author_id=1, workspace_id=5)

        # when
        result = await project_service.create_project(project_data, author_id=1)

        # then
        assert result == mock_project

    @pytest.mark.asyncio
    async def test_should_block_manager_from_creating_second_project_in_workspace(self):
        # given
        mock_repository = self._setup_mock_repo()
        manager_role = Role(id=4, name="manager")
        mock_repository.create.return_value = Project(id=1, name="Test", author_id=1, workspace_id=5)
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        mock_uow = Mock()
        mock_session = Mock()
        mock_result = Mock()
        mock_result.first.return_value = (object(), manager_role)
        count_result = Mock()
        count_result.scalar_one.return_value = 1
        mock_session.execute = AsyncMock(side_effect=[mock_result, count_result])
        mock_session.refresh = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.add = Mock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test", author_id=1, workspace_id=5)

        # when / then
        with pytest.raises(PermissionError):
            await project_service.create_project(project_data, author_id=1)

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
        """Тест должен успешно удалить проект при наличии права project:delete"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_project = Project(id=1, name="Test Project", description="Test Description", author_id=1)
        mock_repository.get_by_id.return_value = mock_project
        mock_repository.delete.return_value = True

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.delete_project(1, is_admin=True)

        # then
        assert result is True
        mock_repository.get_by_id.assert_called_once_with(1)
        mock_repository.delete.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_allow_admin_to_delete_others_project(self):
        """Админ (is_admin=True) может удалить проект, автором которого не является"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_project = Project(id=1, name="Test Project", description="Test Description", author_id=99)
        mock_repository.get_by_id.return_value = mock_project
        mock_repository.delete.return_value = True

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.delete_project(1, is_admin=True)

        # then
        assert result is True
        mock_repository.delete.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_deny_delete_project_for_non_author_non_admin(self):
        """Пользователь без права project:delete не может удалить проект"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_project = Project(id=1, name="Test Project", description="Test Description", author_id=99)
        mock_repository.get_by_id.return_value = mock_project
        mock_repository.delete.return_value = True

        project_service = ProjectService(mock_repository)

        # when / then
        with pytest.raises(PermissionError):
            await project_service.delete_project(1, is_admin=False)
        mock_repository.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_deny_author_without_permission_to_delete_own_project(self):
        """Автор проекта без права project:delete (галочки «Удалить») не может удалить даже свой проект"""
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_project = Project(id=1, name="Test Project", description="Test Description", author_id=1)
        mock_repository.get_by_id.return_value = mock_project
        mock_repository.delete.return_value = True

        project_service = ProjectService(mock_repository)

        # when / then
        with pytest.raises(PermissionError):
            await project_service.delete_project(1, is_admin=False)
        mock_repository.delete.assert_not_called()

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
    async def test_should_apply_workspace_deadline_to_created_project(self):
        """Дедлайн из настроек пространства применяется при создании проекта"""
        # given
        mock_repository = self._setup_mock_repo()
        manager_role = Role(id=4, name="manager")
        deadline = datetime(2026, 12, 31, tzinfo=UTC)
        mock_project = Project(id=1, name="Test", author_id=1, workspace_id=5)
        mock_repository.create.return_value = mock_project
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        mock_session = mock_repository.uow.session
        ws_result = Mock()
        ws_result.first.return_value = (object(), manager_role)
        count_result = Mock()
        count_result.scalar_one.return_value = 0
        settings_result = Mock()
        settings_result.scalar_one_or_none.return_value = SpaceSettings(
            id=1, space_id=5, settings_type_id=1, default_project_deadline=deadline
        )
        draft_result = Mock()
        draft_result.scalar_one_or_none.return_value = AsyncMock(id=99, name="draft")
        ws_sync_result = Mock()
        ws_sync_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(
            side_effect=[ws_result, count_result, settings_result, draft_result, ws_sync_result]
        )
        mock_session.refresh = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.add = Mock()

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test", author_id=1, workspace_id=5)

        # when
        result = await project_service.create_project(project_data, author_id=1)

        # then
        assert result == mock_project
        payload = project_data.model_dump(exclude_none=True)
        payload.pop("tags", None)
        payload.pop("vacancies", None)
        payload["status_id"] = 99
        payload["deadline"] = deadline
        mock_repository.create.assert_called_once_with(payload)

    @pytest.mark.asyncio
    async def test_should_not_set_deadline_when_workspace_setting_absent(self):
        """Без дедлайна в настройках пространства проект создаётся без дедлайна"""
        # given
        mock_repository = self._setup_mock_repo()
        manager_role = Role(id=4, name="manager")
        mock_project = Project(id=1, name="Test", author_id=1, workspace_id=5)
        mock_repository.create.return_value = mock_project
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        mock_session = mock_repository.uow.session
        ws_result = Mock()
        ws_result.first.return_value = (object(), manager_role)
        count_result = Mock()
        count_result.scalar_one.return_value = 0
        settings_result = Mock()
        settings_result.scalar_one_or_none.return_value = SpaceSettings(
            id=1, space_id=5, settings_type_id=1, default_project_deadline=None
        )
        draft_result = Mock()
        draft_result.scalar_one_or_none.return_value = AsyncMock(id=99, name="draft")
        ws_sync_result = Mock()
        ws_sync_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(
            side_effect=[ws_result, count_result, settings_result, draft_result, ws_sync_result]
        )
        mock_session.refresh = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.add = Mock()

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test", author_id=1, workspace_id=5)

        # when
        result = await project_service.create_project(project_data, author_id=1)

        # then
        assert result == mock_project
        payload = project_data.model_dump(exclude_none=True)
        payload.pop("tags", None)
        payload.pop("vacancies", None)
        payload["status_id"] = 99
        assert "deadline" not in payload
        mock_repository.create.assert_called_once_with(payload)

    @pytest.mark.asyncio
    async def test_should_require_resume_when_applying(self):
        """Отклик на проект без резюме должен отклоняться"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.get_by_id = AsyncMock(return_value=Project(id=1, name="P", author_id=2))
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.has_pending_response = AsyncMock(return_value=False)
        mock_repository.has_pending_invitation = AsyncMock(return_value=False)

        project_service = ProjectService(mock_repository, resume_repository=Mock(spec=ResumeRepository))

        # when
        with pytest.raises(ValidationError, match="Resume is required"):
            await project_service.apply_for_project(project_id=1, user_id=1, resume_id=None)

    @pytest.mark.asyncio
    async def test_should_reject_apply_with_foreign_resume(self):
        """Отклик с чужим резюме должен отклоняться"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.get_by_id = AsyncMock(return_value=Project(id=1, name="P", author_id=2))
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.has_pending_response = AsyncMock(return_value=False)
        mock_repository.has_pending_invitation = AsyncMock(return_value=False)

        mock_resume_repository = Mock(spec=ResumeRepository)
        mock_resume_repository.get_by_id = AsyncMock(return_value=Resume(id=5, author_id=99, header="Чужое резюме"))

        project_service = ProjectService(mock_repository, resume_repository=mock_resume_repository)

        # when
        with pytest.raises(ValidationError, match="your own resume"):
            await project_service.apply_for_project(project_id=1, user_id=1, vacancy_id=None, resume_id=5)

    @pytest.mark.asyncio
    async def test_should_reject_apply_with_nonexistent_resume(self):
        """Отклик с несуществующим резюме должен отклоняться"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.get_by_id = AsyncMock(return_value=Project(id=1, name="P", author_id=2))
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.has_pending_response = AsyncMock(return_value=False)
        mock_repository.has_pending_invitation = AsyncMock(return_value=False)

        mock_resume_repository = Mock(spec=ResumeRepository)
        mock_resume_repository.get_by_id = AsyncMock(return_value=None)

        project_service = ProjectService(mock_repository, resume_repository=mock_resume_repository)

        # when
        with pytest.raises(ValidationError, match="Resume not found"):
            await project_service.apply_for_project(project_id=1, user_id=1, vacancy_id=None, resume_id=999)

    @pytest.mark.asyncio
    async def test_should_apply_with_own_resume(self):
        """Отклик со своим резюме должен создаваться"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.get_by_id = AsyncMock(return_value=Project(id=1, name="P", author_id=2))
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.has_pending_response = AsyncMock(return_value=False)
        mock_repository.has_pending_invitation = AsyncMock(return_value=False)
        mock_repository.create_response = AsyncMock(return_value=Mock(id=RESPONSE_ID, vacancy=Mock(title=None)))

        mock_resume_repository = Mock(spec=ResumeRepository)
        mock_resume_repository.get_by_id = AsyncMock(
            return_value=Resume(id=RESUME_ID, author_id=1, header="Моё резюме")
        )

        project_service = ProjectService(mock_repository, resume_repository=mock_resume_repository)

        # when
        result = await project_service.apply_for_project(project_id=1, user_id=1, vacancy_id=None, resume_id=RESUME_ID)

        # then
        assert result.id == RESPONSE_ID
        mock_repository.create_response.assert_awaited_once_with(
            respondent_id=1, project_id=1, vacancy_id=None, resume_id=RESUME_ID, type="response"
        )

    @pytest.mark.asyncio
    async def test_should_reject_apply_for_participant(self):
        """Участник проекта не должен иметь возможность откликнуться"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.get_by_id = AsyncMock(return_value=Project(id=1, name="P", author_id=2))
        mock_repository.is_user_in_project = AsyncMock(return_value=True)
        mock_repository.has_pending_response = AsyncMock(return_value=False)
        mock_repository.has_pending_invitation = AsyncMock(return_value=False)

        mock_resume_repository = Mock(spec=ResumeRepository)
        mock_resume_repository.get_by_id = AsyncMock(
            return_value=Resume(id=RESUME_ID, author_id=1, header="Моё резюме")
        )

        project_service = ProjectService(mock_repository, resume_repository=mock_resume_repository)

        # when
        with pytest.raises(ValidationError, match="already a participant"):
            await project_service.apply_for_project(project_id=1, user_id=1, vacancy_id=None, resume_id=RESUME_ID)
