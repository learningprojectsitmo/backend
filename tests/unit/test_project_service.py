from __future__ import annotations

import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock  # Добавили AsyncMock

import pytest

from src.core.exceptions import NotFoundError, PermissionError, ValidationError
from src.model.notification import NotificationType
from src.model.project import Project, ProjectStage, ProjectType, ProjectVacancy, Response
from src.model.resume import Resume
from src.model.settings import SpaceSettings
from src.model.user import Role, User
from src.model.workspace import WorkSpace
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
        # По умолчанию пользователь не редактор ни в одном пространстве
        editor_result = Mock()
        editor_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=editor_result)
        return mock_repo

    @staticmethod
    def _make_type_with_stages() -> ProjectType:
        """Проектный тип с двумя этапами (первый — скрыт от участников)"""
        project_type = ProjectType(id=1, name="Type")
        first = ProjectStage(id=11, name="Initial", order=0, project_type_id=1, visible_to_participants=False)
        second = ProjectStage(id=12, name="Development", order=1, project_type_id=1, visible_to_participants=True)
        project_type.stages = [first, second]
        return project_type

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

    @staticmethod
    def _workspace_create_side_effects(
        *,
        workspace_role_name: str = "manager",
        settings: SpaceSettings | None = None,
        existing_projects: int | None = None,
    ) -> list[Mock]:
        """Порядок ``session.execute`` в :meth:`ProjectService.create_project` при заданном workspace_id.

        1) участие в пространстве и его роль, 2) настройки пространства — можно ли
        создавать несколько проектов, 3) [необязательно] число проектов автора,
        4) настройка «требовать тип проекта», 5) дедлайн пространства,
        6) статус draft, 7) первый этап типа проекта, 8) все этапы типа проекта.
        """
        participation_result = Mock()
        participation_result.first.return_value = (object(), Role(id=4, name=workspace_role_name))

        settings_result = Mock()
        settings_result.scalar_one_or_none.return_value = settings

        results = [participation_result, settings_result]
        if settings is None or not settings.allow_multi_project_creation:
            count_result = Mock()
            count_result.scalar_one.return_value = existing_projects or 0
            results.append(count_result)
        results += [settings_result, settings_result]

        draft_result = Mock()
        draft_result.scalar_one_or_none.return_value = AsyncMock(id=99, name="draft")
        first_stage_result = Mock()
        first_stage_result.scalar_one_or_none.return_value = ProjectStage(
            id=11, name="Initial", order=0, project_type_id=1
        )
        all_stages_result = Mock()
        all_stages_result.scalars.return_value.all.return_value = []
        results += [draft_result, first_stage_result, all_stages_result]
        return results

    @pytest.mark.parametrize("workspace_role_name", ["manager", "admin", "teacher"])
    @pytest.mark.asyncio
    async def test_should_allow_create_project_in_workspace_for_managing_roles(self, workspace_role_name):
        # given
        mock_repository = self._setup_mock_repo()
        mock_project = Project(id=1, name="Test Project", author_id=1, workspace_id=5)
        mock_repository.create.return_value = mock_project
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        mock_uow = Mock()
        mock_session = Mock()
        mock_session.execute = AsyncMock(
            side_effect=self._workspace_create_side_effects(
                workspace_role_name=workspace_role_name,
                settings=SpaceSettings(
                    id=1,
                    space_id=5,
                    settings_type_id=1,
                    require_project_type_on_create=False,
                    allow_multi_project_creation=False,
                ),
                existing_projects=0,
            )
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
        """По умолчанию (настройка выключена) автор может создать только один проект"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.create.return_value = Project(id=1, name="Test", author_id=1, workspace_id=5)
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        mock_uow = Mock()
        mock_session = Mock()
        mock_session.execute = AsyncMock(
            side_effect=self._workspace_create_side_effects(settings=None, existing_projects=1)
        )
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
        mock_repository.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_allow_second_project_when_multi_creation_enabled(self):
        """С включённой настройкой создаётся несколько проектов — счётчик не проверяется"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_project = Project(id=2, name="Second", author_id=1, workspace_id=5)
        mock_repository.create.return_value = mock_project
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        mock_uow = Mock()
        mock_session = Mock()
        mock_session.execute = AsyncMock(
            side_effect=self._workspace_create_side_effects(
                settings=SpaceSettings(
                    id=1,
                    space_id=5,
                    settings_type_id=1,
                    require_project_type_on_create=False,
                    allow_multi_project_creation=True,
                ),
                existing_projects=7,
            )
        )
        mock_session.refresh = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.add = Mock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Second", author_id=1, workspace_id=5)

        # when
        result = await project_service.create_project(project_data, author_id=1)

        # then
        assert result == mock_project

    @pytest.mark.asyncio
    async def test_should_ignore_author_id_from_request(self):
        """author_id в теле запроса игнорируется: автором становится текущий пользователь"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.create.return_value = Project(id=1, name="Test", author_id=1)
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        draft_query_result = Mock()
        draft_query_result.scalar_one_or_none.return_value = AsyncMock(id=99, name="draft")
        mock_repository.uow.session.execute = AsyncMock(return_value=draft_query_result)

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test", author_id=999)

        # when
        await project_service.create_project(project_data, author_id=1)

        # then
        payload = mock_repository.create.call_args[0][0]
        assert payload["author_id"] == 1

    @pytest.mark.asyncio
    async def test_should_block_create_project_without_type_when_settings_require_it(self):
        """Настройка «требовать тип проекта» блокирует создание без типа в пространстве"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.create.return_value = Project(id=1, name="Test", author_id=1, workspace_id=5)
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        mock_uow = Mock()
        mock_session = Mock()
        mock_session.execute = AsyncMock(
            side_effect=self._workspace_create_side_effects(
                settings=SpaceSettings(id=1, space_id=5, settings_type_id=1, require_project_type_on_create=True),
                existing_projects=0,
            )
        )
        mock_session.refresh = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.add = Mock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test", author_id=1, workspace_id=5)

        # when / then
        with pytest.raises(ValidationError):
            await project_service.create_project(project_data, author_id=1)

    @pytest.mark.asyncio
    async def test_should_block_create_project_without_type_when_settings_row_absent(self):
        """По умолчанию (нет строки настроек) создание без типа в пространстве запрещено"""
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.create.return_value = Project(id=1, name="Test", author_id=1, workspace_id=5)
        mock_repository.get_or_create_tags = AsyncMock(return_value=[])

        mock_uow = Mock()
        mock_session = Mock()
        mock_session.execute = AsyncMock(
            side_effect=self._workspace_create_side_effects(settings=None, existing_projects=0)
        )
        mock_session.refresh = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.add = Mock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow

        project_service = ProjectService(mock_repository)
        project_data = ProjectCreate(name="Test", author_id=1, workspace_id=5)

        # when / then
        with pytest.raises(ValidationError):
            await project_service.create_project(project_data, author_id=1)

    @pytest.mark.asyncio
    async def test_should_allow_multi_project_creation_without_workspace(self):
        """Без пространства ограничения на число проектов нет"""
        # given
        project_service = ProjectService(self._setup_mock_repo())

        # when / then
        assert await project_service.workspace_allows_multi_project_creation(None) is True

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

    def _vacancy_sync_setup(self, vacancies: list[ProjectVacancy], response_counts: dict[int, int] | None = None):
        """Репозиторий и проект для проверки синхронизации ролей.

        ``response_counts`` — сколько откликов висит на каждой роли
        (для ``ProjectVacancy`` без откликов ключа нет).
        """
        mock_repo = self._setup_mock_repo()
        mock_repo.get_response_counts_by_vacancy_ids = AsyncMock(return_value=response_counts or {})

        existing_project = Project(id=1, name="Project", author_id=1, vacancies=vacancies)
        mock_repo.get_by_id.return_value = existing_project
        mock_repo.update.return_value = existing_project
        mock_repo.get_or_create_tags = AsyncMock(return_value=[])
        return mock_repo, existing_project

    @pytest.mark.asyncio
    async def test_should_update_existing_vacancy_in_place_keeping_its_id(self):
        # given: роль с откликами, у которой в правке изменились поля
        mock_repo, project = self._vacancy_sync_setup(
            vacancies=[ProjectVacancy(id=5, project_id=1, title="Backend", tasks=["t"], required_count=2)],
        )
        project_service = ProjectService(mock_repo)

        # when
        await project_service.update_project(
            1,
            ProjectUpdate(vacancies=[{"id": 5, "title": "Backend dev", "tasks": ["a", "b"], "required_count": 3}]),
            current_user_id=1,
        )

        # then: та же строка обновлена, ничего не удалено и не создано
        vacancy = project.vacancies[0]
        assert vacancy.id == 5
        assert vacancy.title == "Backend dev"
        assert vacancy.tasks == ["a", "b"]
        assert vacancy.required_count == 3
        assert vacancy.project_id == 1
        assert len(project.vacancies) == 1
        mock_repo.uow.session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_create_vacancy_without_id_and_keep_existing_one(self):
        # given
        mock_repo, project = self._vacancy_sync_setup(
            vacancies=[ProjectVacancy(id=5, project_id=1, title="Backend", tasks=["t"], required_count=1)],
        )
        project_service = ProjectService(mock_repo)

        # when: приехала существующая роль и новая (без id)
        await project_service.update_project(
            1,
            ProjectUpdate(
                vacancies=[
                    {"id": 5, "title": "Backend", "tasks": ["t"], "required_count": 1},
                    {"title": "Frontend", "tasks": ["ui"], "required_count": 1},
                ]
            ),
            current_user_id=1,
        )

        # then: создана ровно одна новая роль, существующая не тронута
        added = [call.args[0] for call in mock_repo.uow.session.add.call_args_list]
        created = [v for v in added if isinstance(v, ProjectVacancy)]
        assert len(created) == 1
        assert created[0].title == "Frontend"
        assert created[0].project_id == 1
        assert project.vacancies[0].title == "Backend"
        assert mock_repo.uow.session.delete.call_count == 0

    @pytest.mark.asyncio
    async def test_should_archive_vacancy_without_responses(self):
        # given: на снимаемую роль никто не откликался
        mock_repo, project = self._vacancy_sync_setup(
            vacancies=[
                ProjectVacancy(id=5, project_id=1, title="Backend", tasks=["t"], required_count=1),
                ProjectVacancy(id=6, project_id=1, title="QA", tasks=["q"], required_count=1),
            ],
            response_counts={5: 1},
        )
        project_service = ProjectService(mock_repo)

        # when: роль 6 убрали из списка
        await project_service.update_project(
            1,
            ProjectUpdate(vacancies=[{"id": 5, "title": "Backend", "tasks": ["t"], "required_count": 1}]),
            current_user_id=1,
        )

        # then: снятая роль архивирована, а не удалена — строка хранит
        # историю откликов, ссылки response.vacancy_id остаются рабочими
        by_id = {v.id: v for v in project.vacancies}
        assert by_id[6].archived is True
        # default колонки применяется при flush, поэтому у незаполненной роли
        # значение ещё None — важно, что это не True
        assert not by_id[5].archived
        mock_repo.uow.session.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_reject_removing_vacancy_with_responses(self):
        # given: на удаляемую роль есть отклик
        mock_repo, _ = self._vacancy_sync_setup(
            vacancies=[
                ProjectVacancy(id=5, project_id=1, title="Backend", tasks=["t"], required_count=1),
                ProjectVacancy(id=6, project_id=1, title="QA", tasks=["q"], required_count=1),
            ],
            response_counts={6: 3},
        )
        project_service = ProjectService(mock_repo)

        # when / then: правка падает, и название роли есть в сообщении
        with pytest.raises(ValidationError, match=re.escape("«QA» — 3")):
            await project_service.update_project(
                1,
                ProjectUpdate(vacancies=[{"id": 5, "title": "Backend", "tasks": ["t"], "required_count": 1}]),
                current_user_id=1,
            )
        assert mock_repo.uow.session.delete.call_count == 0

    @pytest.mark.asyncio
    async def test_should_reject_vacancy_id_from_another_project(self):
        # given: в payload подставлен id роли из чужого проекта
        mock_repo, _ = self._vacancy_sync_setup(vacancies=[])
        project_service = ProjectService(mock_repo)

        # when / then
        with pytest.raises(ValidationError, match=re.escape("id=99")):
            await project_service.update_project(
                1,
                ProjectUpdate(vacancies=[{"id": 99, "title": "Hacker", "tasks": ["t"], "required_count": 1}]),
                current_user_id=1,
            )
        assert mock_repo.uow.session.delete.call_count == 0

    @pytest.mark.asyncio
    async def test_should_reject_duplicate_vacancy_id(self):
        # given: одна и та же роль прислана дважды
        mock_repo, _ = self._vacancy_sync_setup(
            vacancies=[ProjectVacancy(id=5, project_id=1, title="Backend", tasks=["t"], required_count=1)],
        )
        project_service = ProjectService(mock_repo)

        # when / then
        with pytest.raises(ValidationError, match=re.escape("продублирована")):
            await project_service.update_project(
                1,
                ProjectUpdate(
                    vacancies=[
                        {"id": 5, "title": "Backend", "tasks": ["t"], "required_count": 1},
                        {"id": 5, "title": "Backend", "tasks": ["t"], "required_count": 1},
                    ]
                ),
                current_user_id=1,
            )
        assert mock_repo.uow.session.delete.call_count == 0

    @pytest.mark.asyncio
    async def test_should_not_touch_vacancies_when_field_absent(self):
        # given: правим только название проекта
        mock_repo, project = self._vacancy_sync_setup(
            vacancies=[ProjectVacancy(id=5, project_id=1, title="Backend", tasks=["t"], required_count=1)],
        )
        project_service = ProjectService(mock_repo)

        # when
        await project_service.update_project(1, ProjectUpdate(name="New name"), current_user_id=1)

        # then
        assert mock_repo.uow.session.delete.call_count == 0
        assert project.vacancies[0].title == "Backend"

    @pytest.mark.asyncio
    async def test_should_get_projects_paginated(self):
        # given
        mock_repository = self._setup_mock_repo()
        mock_projects = [
            Project(id=1, name="P1", author_id=1, participants=[], status=None),
            Project(id=2, name="P2", author_id=1, participants=[], status=None),
        ]

        mock_repository.get_projects_page.return_value = (mock_projects, EXPECTED_PROJECTS_COUNT)

        project_service = ProjectService(mock_repository)

        # when
        projects, total = await project_service.get_projects_paginated(page=1, limit=10, viewer_id=1)

        # then
        assert len(projects) == EXPECTED_PROJECTS_COUNT
        assert total == EXPECTED_PROJECTS_COUNT
        _, kwargs = mock_repository.get_projects_page.call_args
        assert kwargs["workspace_id"] is None
        assert kwargs["skip"] == 0
        assert kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_should_return_total_from_count_instead_of_page_length(self):
        # given — на первой странице 10 проектов, а всего их 25
        mock_repository = self._setup_mock_repo()
        page = [Project(id=i, name=f"P{i}", author_id=1) for i in range(10)]
        mock_repository.get_projects_page.return_value = (page, 25)

        project_service = ProjectService(mock_repository)

        # when
        _, total = await project_service.get_projects_paginated(page=2, limit=10, viewer_id=1)

        # then
        assert total == 25
        _, kwargs = mock_repository.get_projects_page.call_args
        assert kwargs["skip"] == 10

    @pytest.mark.asyncio
    async def test_should_pass_filters_to_repository(self):
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.get_projects_page.return_value = ([], 0)

        project_service = ProjectService(mock_repository)

        # when
        await project_service.get_projects_by_workspace(
            workspace_id=1,
            page=1,
            limit=10,
            viewer_id=1,
            search="мед",
            stages=["Создание тз"],
            tags=["ml"],
            member_ids=[3],
        )

        # then
        _, kwargs = mock_repository.get_projects_page.call_args
        assert kwargs["workspace_id"] == 1
        assert kwargs["search"] == "мед"
        assert kwargs["stages"] == ["Создание тз"]
        assert kwargs["tags"] == ["ml"]
        assert kwargs["member_ids"] == [3]

    @pytest.mark.asyncio
    async def test_should_hide_stage_one_draft_from_participant(self):
        # given
        mock_repository = self._setup_mock_repo()
        draft = Project(
            id=1, name="Draft", author_id=5, current_stage_id=11, project_type=self._make_type_with_stages()
        )
        mock_repository.get_projects_by_participant_id.return_value = [draft]

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.get_my_projects(user_id=1)

        # then
        assert result.items == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_should_show_stage_one_draft_to_author(self):
        # given
        mock_repository = self._setup_mock_repo()
        draft = Project(
            id=1, name="Draft", author_id=5, current_stage_id=11, project_type=self._make_type_with_stages()
        )
        mock_repository.get_projects_by_participant_id.return_value = [draft]

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.get_my_projects(user_id=5)

        # then
        assert len(result.items) == 1
        assert result.items[0].id == 1

    @pytest.mark.asyncio
    async def test_should_show_second_stage_project_to_everyone(self):
        # given
        mock_repository = self._setup_mock_repo()
        published = Project(
            id=1, name="Published", author_id=5, current_stage_id=12, project_type=self._make_type_with_stages()
        )
        mock_repository.get_projects_by_participant_id.return_value = [published]

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.get_my_projects(user_id=1)

        # then
        assert len(result.items) == 1
        assert result.items[0].id == 1

    @pytest.mark.asyncio
    async def test_should_show_first_stage_project_when_visible_to_participants(self):
        # given — первый этап помечен как видимый участникам
        mock_repository = self._setup_mock_repo()
        project_type = ProjectType(id=1, name="Type")
        project_type.stages = [
            ProjectStage(id=11, name="Initial", order=0, project_type_id=1, visible_to_participants=True),
        ]
        visible = Project(id=1, name="Visible", author_id=5, current_stage_id=11, project_type=project_type)
        mock_repository.get_projects_by_participant_id.return_value = [visible]

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.get_my_projects(user_id=1)

        # then
        assert len(result.items) == 1
        assert result.items[0].id == 1

    @pytest.mark.asyncio
    async def test_should_hide_second_stage_project_when_hidden_from_participants(self):
        # given — второй (не первый) этап скрыт от участников
        mock_repository = self._setup_mock_repo()
        project_type = ProjectType(id=1, name="Type")
        project_type.stages = [
            ProjectStage(id=11, name="Initial", order=0, project_type_id=1, visible_to_participants=True),
            ProjectStage(id=12, name="Hidden", order=1, project_type_id=1, visible_to_participants=False),
        ]
        hidden = Project(id=1, name="Hidden", author_id=5, current_stage_id=12, project_type=project_type)
        mock_repository.get_projects_by_participant_id.return_value = [hidden]

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.get_my_projects(user_id=1)

        # then
        assert result.items == []
        assert result.total == 0

    @staticmethod
    def _criteria_sql(call_args) -> str:
        visible = call_args.kwargs["visible"]
        if visible is None:
            return ""
        return str(visible.compile(compile_kwargs={"literal_binds": True}))

    @pytest.mark.asyncio
    async def test_should_filter_drafts_in_paginated_list(self):
        # given — черновики отсекаются в SQL, до пагинации
        mock_repository = self._setup_mock_repo()
        mock_repository.get_projects_page.return_value = ([], 0)

        project_service = ProjectService(mock_repository)

        # when
        _, total = await project_service.get_projects_paginated(page=1, limit=10, viewer_id=1)

        # then
        sql = self._criteria_sql(mock_repository.get_projects_page.call_args)
        assert "NOT (project.project_type_id IN" in sql
        assert "project.author_id = 1" in sql
        assert total == 0

    @pytest.mark.asyncio
    async def test_should_not_filter_anything_for_anonymous_viewer(self):
        # given
        mock_repository = self._setup_mock_repo()
        mock_repository.get_projects_page.return_value = ([], 0)

        project_service = ProjectService(mock_repository)

        # when
        await project_service.get_projects_by_workspace(workspace_id=1, page=1, limit=10, viewer_id=None)

        # then
        assert self._criteria_sql(mock_repository.get_projects_page.call_args) == ""

    @pytest.mark.asyncio
    async def test_should_show_draft_to_workspace_admin_in_list(self):
        # given — редактор пространства видит черновики
        mock_repository = self._setup_mock_repo()
        mock_repository.get_projects_page.return_value = ([], 0)

        editor_query_result = Mock()
        editor_query_result.scalars.return_value.all.return_value = [1]
        mock_repository.uow.session.execute.return_value = editor_query_result

        project_service = ProjectService(mock_repository)

        # when
        await project_service.get_projects_by_workspace(workspace_id=1, page=1, limit=10, viewer_id=1)

        # then
        sql = self._criteria_sql(mock_repository.get_projects_page.call_args)
        assert "project.workspace_id IN (1)" in sql

    @pytest.mark.asyncio
    async def test_should_hide_draft_from_non_editor_in_workspace_list(self):
        # given — участник без роли admin/teacher
        mock_repository = self._setup_mock_repo()
        mock_repository.get_projects_page.return_value = ([], 0)

        editor_query_result = Mock()
        editor_query_result.scalars.return_value.all.return_value = []
        mock_repository.uow.session.execute.return_value = editor_query_result

        project_service = ProjectService(mock_repository)

        # when
        await project_service.get_projects_by_workspace(workspace_id=1, page=1, limit=10, viewer_id=1)

        # then
        sql = self._criteria_sql(mock_repository.get_projects_page.call_args)
        assert "project.workspace_id IN" not in sql
        assert "project.author_id = 1" in sql

    @pytest.mark.asyncio
    async def test_should_check_editor_role_in_all_workspaces_for_global_list(self):
        # given — список по всем пространствам
        mock_repository = self._setup_mock_repo()
        mock_repository.get_projects_page.return_value = ([], 0)

        editor_query_result = Mock()
        editor_query_result.scalars.return_value.all.return_value = [1, 7]
        mock_repository.uow.session.execute.return_value = editor_query_result

        project_service = ProjectService(mock_repository)

        # when
        await project_service.get_projects_paginated(page=1, limit=10, viewer_id=1)

        # then
        sql = self._criteria_sql(mock_repository.get_projects_page.call_args)
        assert "project.workspace_id IN (1, 7)" in sql

    @pytest.mark.asyncio
    async def test_is_workspace_editor_should_return_true_for_admin_role(self):
        # given
        mock_repository = self._setup_mock_repo()
        editor_query_result = Mock()
        editor_query_result.first.return_value = (42,)
        mock_repository.uow.session.execute.return_value = editor_query_result

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.is_workspace_editor(user_id=1, workspace_id=1)

        # then
        assert result is True

    @pytest.mark.asyncio
    async def test_is_workspace_editor_should_return_true_for_teacher_role(self):
        # given
        mock_repository = self._setup_mock_repo()
        editor_query_result = Mock()
        editor_query_result.first.return_value = (42,)
        mock_repository.uow.session.execute.return_value = editor_query_result

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.is_workspace_editor(user_id=1, workspace_id=1)

        # then
        assert result is True

    @pytest.mark.asyncio
    async def test_is_workspace_editor_should_return_false_for_other_roles(self):
        # given
        mock_repository = self._setup_mock_repo()
        editor_query_result = Mock()
        editor_query_result.first.return_value = None
        mock_repository.uow.session.execute.return_value = editor_query_result

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.is_workspace_editor(user_id=1, workspace_id=1)

        # then
        assert result is False

    @pytest.mark.asyncio
    async def test_is_workspace_editor_should_return_false_without_workspace(self):
        # given
        mock_repository = self._setup_mock_repo()
        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.is_workspace_editor(user_id=1, workspace_id=None)

        # then
        assert result is False
        mock_repository.uow.session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_to_project_list_item_should_include_current_stage(self):
        # given
        project_service = ProjectService(self._setup_mock_repo())
        current_stage_id = 11
        current_stage_name = "Утверждение темы"
        stage = ProjectStage(id=current_stage_id, name=current_stage_name, order=0, project_type_id=1)
        project = Project(id=1, name="P", author_id=5, current_stage_id=current_stage_id, progress=40)
        project.current_stage = stage

        # when
        item = project_service.to_project_list_item(project)

        # then
        assert item.current_stage_id == current_stage_id
        assert item.current_stage_name == current_stage_name

    @pytest.mark.asyncio
    async def test_to_project_list_item_should_allow_missing_current_stage(self):
        # given
        project_service = ProjectService(self._setup_mock_repo())
        project = Project(id=1, name="P", author_id=5)

        # when
        item = project_service.to_project_list_item(project)

        # then
        assert item.current_stage_id is None
        assert item.current_stage_name is None

    @pytest.mark.asyncio
    async def test_should_treat_stage_zero_and_missing_type_consistently(self):
        # given
        project_service = ProjectService(self._setup_mock_repo())

        no_type = Project(id=1, name="No Type", author_id=1)
        not_started = Project(id=2, name="Not Started", author_id=1, project_type=self._make_type_with_stages())

        # when / then
        assert project_service.is_draft(no_type) is False
        assert project_service.is_draft(not_started) is True

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
        require_type_result = Mock()
        require_type_result.scalar_one_or_none.return_value = SpaceSettings(
            id=1, space_id=5, settings_type_id=1, require_project_type_on_create=False
        )
        mock_session.execute = AsyncMock(
            side_effect=[ws_result, count_result, require_type_result, settings_result, draft_result, ws_sync_result]
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
        require_type_result = Mock()
        require_type_result.scalar_one_or_none.return_value = SpaceSettings(
            id=1, space_id=5, settings_type_id=1, require_project_type_on_create=False
        )
        mock_session.execute = AsyncMock(
            side_effect=[ws_result, count_result, require_type_result, settings_result, draft_result, ws_sync_result]
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


class TestMultiProjectRestriction:
    """Запрет участия в нескольких проектах одного пространства."""

    def _make_accepted_response(self, response_id: int, user_id: int, project_id: int) -> Response:
        return Response(
            id=response_id,
            respondent_id=user_id,
            project_id=project_id,
            type="response",
            status="accepted",
        )

    def _make_pending_invitation(self, invitation_id: int, user_id: int, project_id: int) -> Response:
        return Response(
            id=invitation_id,
            respondent_id=user_id,
            project_id=project_id,
            type="invitation",
            status="pending",
        )

    def _settings_result(self, allow_multi: bool):
        result = Mock()
        result.scalar_one_or_none.return_value = SpaceSettings(
            space_id=7, allow_multi_project_participation=allow_multi
        )
        return result

    @pytest.mark.asyncio
    async def test_confirm_join_marks_sibling_pending_as_in_team_when_restriction_on(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        mock_repository.get_response_by_id_for_update = AsyncMock(return_value=self._make_accepted_response(1, 2, 3))
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.get_by_id = AsyncMock(
            return_value=Project(id=3, name="P", author_id=1, workspace_id=7, max_participants=None)
        )
        mock_repository.is_user_participant_in_other_project = AsyncMock(return_value=False)
        mock_repository.add_participant = AsyncMock()
        mock_repository.update_response_status = AsyncMock(return_value=True)
        mock_repository.mark_sibling_pending_as_in_team = AsyncMock(return_value=2)
        mock_session.execute = AsyncMock(side_effect=[self._settings_result(False), self._settings_result(False)])

        project_service = ProjectService(mock_repository)

        # when
        await project_service.confirm_join(1, 2)

        # then
        mock_repository.add_participant.assert_awaited_once_with(3, 2)
        mock_repository.update_response_status.assert_awaited_once_with(1, "in_team")
        mock_repository.mark_sibling_pending_as_in_team.assert_awaited_once_with(2, 1, 7)

    @pytest.mark.asyncio
    async def test_confirm_join_skips_marking_when_restriction_off(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        mock_repository.get_response_by_id_for_update = AsyncMock(return_value=self._make_accepted_response(1, 2, 3))
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.get_by_id = AsyncMock(
            return_value=Project(id=3, name="P", author_id=1, workspace_id=7, max_participants=None)
        )
        mock_repository.add_participant = AsyncMock()
        mock_repository.update_response_status = AsyncMock(return_value=True)
        mock_repository.mark_sibling_pending_as_in_team = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[self._settings_result(True), self._settings_result(True)])

        project_service = ProjectService(mock_repository)

        # when
        await project_service.confirm_join(1, 2)

        # then
        mock_repository.add_participant.assert_awaited_once_with(3, 2)
        mock_repository.update_response_status.assert_awaited_once_with(1, "in_team")
        mock_repository.mark_sibling_pending_as_in_team.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_join_blocks_when_user_already_in_another_project(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        mock_repository.get_response_by_id_for_update = AsyncMock(return_value=self._make_accepted_response(1, 2, 3))
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.get_by_id = AsyncMock(
            return_value=Project(id=3, name="P", author_id=1, workspace_id=7, max_participants=None)
        )
        mock_repository.is_user_participant_in_other_project = AsyncMock(return_value=True)
        mock_repository.add_participant = AsyncMock()
        mock_session.execute = AsyncMock(return_value=self._settings_result(False))

        project_service = ProjectService(mock_repository)

        # when / then
        with pytest.raises(ValidationError, match="уже участвуете"):
            await project_service.confirm_join(1, 2)
        mock_repository.add_participant.assert_not_called()
        mock_repository.mark_sibling_pending_as_in_team.assert_not_called()

    @pytest.mark.asyncio
    async def test_accept_invitation_marks_sibling_pending_as_in_team_when_restriction_on(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        mock_repository.get_response_by_id_for_update = AsyncMock(return_value=self._make_pending_invitation(5, 2, 3))
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.get_by_id = AsyncMock(
            return_value=Project(id=3, name="P", author_id=1, workspace_id=7, max_participants=None)
        )
        mock_repository.is_user_participant_in_other_project = AsyncMock(return_value=False)
        mock_repository.update_response_status = AsyncMock(return_value=self._make_pending_invitation(5, 2, 3))
        mock_repository.add_participant = AsyncMock()
        mock_repository.mark_sibling_pending_as_in_team = AsyncMock(return_value=1)
        mock_session.execute = AsyncMock(side_effect=[self._settings_result(False), self._settings_result(False)])

        project_service = ProjectService(mock_repository)

        # when
        await project_service.accept_invitation(5, 2)

        # then
        mock_repository.add_participant.assert_awaited_once_with(3, 2)
        mock_repository.mark_sibling_pending_as_in_team.assert_awaited_once_with(2, 5, 7)

    @pytest.mark.asyncio
    async def test_accept_invitation_blocks_when_user_already_in_another_project(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        mock_repository.get_response_by_id_for_update = AsyncMock(return_value=self._make_pending_invitation(5, 2, 3))
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.get_by_id = AsyncMock(
            return_value=Project(id=3, name="P", author_id=1, workspace_id=7, max_participants=None)
        )
        mock_repository.is_user_participant_in_other_project = AsyncMock(return_value=True)
        mock_repository.update_response_status = AsyncMock()
        mock_repository.add_participant = AsyncMock()
        mock_session.execute = AsyncMock(return_value=self._settings_result(False))

        project_service = ProjectService(mock_repository)

        # when / then
        with pytest.raises(ValidationError, match="уже участвуете"):
            await project_service.accept_invitation(5, 2)
        mock_repository.update_response_status.assert_not_called()
        mock_repository.add_participant.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_my_invitations_exposes_restriction_flag(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        invitation = self._make_pending_invitation(5, 2, 3)
        invitation.project = Project(id=3, name="P", description="D", author_id=1, workspace_id=7)
        mock_repository.get_invitations_by_invitee_id = AsyncMock(return_value=[invitation])
        mock_repository.get_user_project_scopes = AsyncMock(return_value=[])
        flags_result = Mock()
        flags_result.all.return_value = [(7, False)]
        mock_session.execute = AsyncMock(return_value=flags_result)

        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.get_my_invitations(2)

        # then
        assert result.total == 1
        assert result.items[0].allow_multi_project_participation is False

    def _setup_profile_list(
        self,
        *,
        responses: list[Response],
        allow_multi: bool,
        user_scopes: list[tuple[int, int | None]],
    ) -> tuple[Mock, AsyncMock, ProjectService]:
        """Репозиторий для списков профиля: отклики/приглашения + занятость по пространствам."""
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        mock_repository.get_responses_by_respondent_id = AsyncMock(return_value=responses)
        mock_repository.get_invitations_by_invitee_id = AsyncMock(return_value=responses)
        mock_repository.get_user_project_scopes = AsyncMock(return_value=user_scopes)
        flags_result = Mock()
        flags_result.all.return_value = [(7, allow_multi)]
        mock_session.execute = AsyncMock(return_value=flags_result)
        return mock_repository, mock_session, ProjectService(mock_repository)

    @staticmethod
    def _make_project_with_stage() -> Project:
        """Проект с этапом: ProjectFull.from_orm требует заполненный stage."""
        stage = ProjectStage(id=1, name="S", order=1, requires_approval=False, project_type_id=1)
        return Project(
            id=3,
            name="P",
            author_id=1,
            workspace_id=7,
            max_participants=None,
            current_stage=stage,
            # server_default не применяется, пока объект не сброшен в БД
            stage_pending_approval=False,
        )

    def _make_profile_response(
        self, response_id: int, status: str, project_id: int, workspace_id: int | None
    ) -> Response:
        response = Response(
            id=response_id,
            respondent_id=2,
            project_id=project_id,
            type="response",
            status=status,
            created_at=datetime(2026, 1, 1),
        )
        response.project = Project(
            id=project_id, name=f"P{project_id}", description="D", author_id=1, workspace_id=workspace_id
        )
        return response

    @pytest.mark.asyncio
    async def test_should_mark_accepted_response_as_in_team_when_joined_another_project(self):
        # given: отклик принят, но участник уже в другом проекте этого пространства
        response = self._make_profile_response(1, "accepted", project_id=3, workspace_id=7)
        _, _, project_service = self._setup_profile_list(
            responses=[response], allow_multi=False, user_scopes=[(3, 7), (5, 7)]
        )

        # when
        result = await project_service.get_my_responses(2)

        # then
        assert result.items[0].status == "in_team"
        assert result.items[0].busy_in_other_project is True

    @pytest.mark.asyncio
    async def test_should_mark_pending_response_as_in_team_when_joined_another_project(self):
        # given
        response = self._make_profile_response(1, "pending", project_id=3, workspace_id=7)
        _, _, project_service = self._setup_profile_list(
            responses=[response], allow_multi=False, user_scopes=[(3, 7), (5, 7)]
        )

        # when
        result = await project_service.get_my_responses(2)

        # then
        assert result.items[0].status == "in_team"

    @pytest.mark.asyncio
    async def test_should_keep_accepted_response_when_user_joined_same_project_only(self):
        # given: единственный проект пользователя — тот, на который он откликнулся
        response = self._make_profile_response(1, "accepted", project_id=3, workspace_id=7)
        _, _, project_service = self._setup_profile_list(responses=[response], allow_multi=False, user_scopes=[(3, 7)])

        # when
        result = await project_service.get_my_responses(2)

        # then
        assert result.items[0].status == "accepted"
        assert result.items[0].busy_in_other_project is False

    @pytest.mark.asyncio
    async def test_should_scope_busy_to_response_workspace(self):
        # given: занят в проекте ДРУГОГО пространства — это не помеха
        response = self._make_profile_response(1, "accepted", project_id=3, workspace_id=7)
        _, _, project_service = self._setup_profile_list(
            responses=[response], allow_multi=False, user_scopes=[(3, 7), (9, 8)]
        )

        # when
        result = await project_service.get_my_responses(2)

        # then
        assert result.items[0].status == "accepted"
        assert result.items[0].busy_in_other_project is False

    @pytest.mark.asyncio
    async def test_should_keep_accepted_response_when_multi_participation_allowed(self):
        # given: в пространстве разрешено состоять в нескольких проектах
        response = self._make_profile_response(1, "accepted", project_id=3, workspace_id=7)
        _, _, project_service = self._setup_profile_list(
            responses=[response], allow_multi=True, user_scopes=[(3, 7), (5, 7)]
        )

        # when
        result = await project_service.get_my_responses(2)

        # then
        assert result.items[0].status == "accepted"
        assert result.items[0].busy_in_other_project is False

    @pytest.mark.asyncio
    async def test_should_not_rewrite_rejected_response(self):
        # given: решение сторон пересмотру не подлежит
        response = self._make_profile_response(1, "rejected", project_id=3, workspace_id=7)
        _, _, project_service = self._setup_profile_list(
            responses=[response], allow_multi=False, user_scopes=[(3, 7), (5, 7)]
        )

        # when
        result = await project_service.get_my_responses(2)

        # then
        assert result.items[0].status == "rejected"
        assert result.items[0].busy_in_other_project is True

    @pytest.mark.asyncio
    async def test_should_mark_pending_invitation_as_in_team_when_joined_another_project(self):
        # given
        invitation = self._make_profile_response(5, "pending", project_id=3, workspace_id=7)
        invitation.type = "invitation"
        _, _, project_service = self._setup_profile_list(
            responses=[invitation], allow_multi=False, user_scopes=[(3, 7), (5, 7)]
        )

        # when
        result = await project_service.get_my_invitations(2)

        # then
        assert result.items[0].status == "in_team"
        assert result.items[0].busy_in_other_project is True

    @pytest.mark.asyncio
    async def test_build_full_should_pass_busy_ids_to_schema(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        project = self._make_project_with_stage()
        mock_repository.get_workspace_busy_participant_ids = AsyncMock(return_value={2, 5})
        mock_session.execute = AsyncMock(return_value=self._settings_result(False))

        project_service = ProjectService(mock_repository)

        # when
        full = await project_service.build_full(project, 1)

        # then
        mock_repository.get_workspace_busy_participant_ids.assert_awaited_once_with(7, 3)
        assert full.workspace_id == 7

    @pytest.mark.asyncio
    async def test_build_full_should_skip_busy_query_when_multi_allowed(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        project = self._make_project_with_stage()
        mock_repository.get_workspace_busy_participant_ids = AsyncMock()
        mock_session.execute = AsyncMock(return_value=self._settings_result(True))

        project_service = ProjectService(mock_repository)

        # when
        await project_service.build_full(project, 1)

        # then
        mock_repository.get_workspace_busy_participant_ids.assert_not_called()

    @pytest.mark.asyncio
    async def test_invite_to_project_should_block_candidate_busy_in_another_project(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        project = Project(id=3, name="P", author_id=1, workspace_id=7, max_participants=None)
        mock_repository.get_by_id = AsyncMock(return_value=project)
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.has_pending_response = AsyncMock(return_value=False)
        mock_repository.is_user_participant_in_other_project = AsyncMock(return_value=True)
        mock_session.execute = AsyncMock(return_value=self._settings_result(False))

        project_service = ProjectService(mock_repository)

        # when / then
        with pytest.raises(ValidationError, match="уже состоит в другом проекте"):
            await project_service.invite_to_project(3, 1, 2)
        mock_repository.create_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_invite_to_project_should_allow_busy_candidate_when_multi_allowed(self):
        # given
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        project = Project(id=3, name="P", author_id=1, workspace_id=7, max_participants=None)
        mock_repository.get_by_id = AsyncMock(return_value=project)
        mock_repository.is_user_in_project = AsyncMock(return_value=False)
        mock_repository.has_pending_response = AsyncMock(return_value=False)
        mock_repository.is_user_participant_in_other_project = AsyncMock(return_value=True)
        mock_repository.create_response = AsyncMock(return_value=Response(id=9, project_id=3, respondent_id=2))
        mock_session.execute = AsyncMock(return_value=self._settings_result(True))

        project_service = ProjectService(mock_repository)

        # when
        await project_service.invite_to_project(3, 1, 2)

        # then
        mock_repository.create_response.assert_awaited_once()


class TestParticipationDuplicates:
    """Повторное принятие заявки не должно плодить строки участия.

    Регрессия: на проде у одного человека накопились четыре строки в
    `project_participation` на пару (project_id, participant_id) — по одной на
    каждый клик по кнопке подтверждения. Список участников проекта строится по
    этим строкам, поэтому человек показывался четырежды.

    Отсюда два требования к сервису: блокировка строки заявки (сериализует
    параллельные запросы) и guard на уже существующее участие (повторный запрос
    — не ошибка, а уже сделанное дело).
    """

    def _accepted_response(self, response_id: int = 1, user_id: int = 2, project_id: int = 3) -> Response:
        return Response(
            id=response_id,
            respondent_id=user_id,
            project_id=project_id,
            type="response",
            status="accepted",
        )

    def _pending_invitation(self, invitation_id: int = 5, user_id: int = 2, project_id: int = 3) -> Response:
        return Response(
            id=invitation_id,
            respondent_id=user_id,
            project_id=project_id,
            type="invitation",
            status="pending",
        )

    def _repo(self, **kwargs) -> Mock:
        repository = Mock(spec=ProjectRepository)
        uow = Mock()
        uow.session = AsyncMock()
        repository.uow = uow
        repository.get_response_by_id_for_update = AsyncMock(
            return_value=kwargs.pop("response", None),
        )
        repository.get_by_id = AsyncMock(
            return_value=Project(id=3, name="P", author_id=1, workspace_id=None, max_participants=None),
        )
        # По умолчанию участника в проекте нет — иначе новый guard срезал бы
        # тело метода раньше, чем его интересно проверить.
        repository.is_user_in_project = AsyncMock(return_value=False)
        repository.is_user_participant_in_other_project = AsyncMock(return_value=False)
        repository.add_participant = AsyncMock()
        repository.update_response_status = AsyncMock(return_value=True)
        repository.decrement_vacancy_count = AsyncMock()
        for key, value in kwargs.items():
            setattr(repository, key, value)
        return repository

    def _stateful_repo(self, response: Response) -> Mock:
        """Репозиторий, который помнит состояние — как реальная БД.

        Нужен для тестов на повторный запрос: `add_participant` обязан увидеть
        уже добавленную строку, а статус заявки — обновлённый. Статические
        `AsyncMock(return_value=...)` этого не моделируют, и тест на «две
        строки участия» проходит, ничего не проверяя.
        """
        repository = self._repo(response=response)
        repository.participations = []
        repository.status_updates = []
        repository.vacancy_decrements = []

        async def _add_participant(project_id: int, user_id: int):
            pair = (project_id, user_id)
            if pair in repository.participations:
                return Mock()
            repository.participations.append(pair)
            return Mock()

        async def _is_user_in_project(project_id: int, user_id: int) -> bool:
            return (project_id, user_id) in repository.participations

        async def _update_response_status(response_id: int, status: str):
            repository.status_updates.append((response_id, status))
            response.status = status
            return response

        async def _decrement(vacancy_id: int):
            repository.vacancy_decrements.append(vacancy_id)

        repository.add_participant = AsyncMock(side_effect=_add_participant)
        repository.is_user_in_project = AsyncMock(side_effect=_is_user_in_project)
        repository.update_response_status = AsyncMock(side_effect=_update_response_status)
        repository.decrement_vacancy_count = AsyncMock(side_effect=_decrement)
        return repository

    @pytest.mark.asyncio
    async def test_confirm_join_takes_row_lock_on_response(self):
        # given
        repository = self._repo(response=self._accepted_response())

        # when
        await ProjectService(repository).confirm_join(1, 2)

        # then: заявка читается под блокировкой, иначе параллельные запросы
        # прочитают один статус и оба вставят участие
        repository.get_response_by_id_for_update.assert_awaited_once_with(1)
        repository.add_participant.assert_awaited_once_with(3, 2)

    @pytest.mark.asyncio
    async def test_confirm_join_is_noop_when_already_participant(self):
        # given: участие уже есть (пользователь вступил по приглашению, а этот
        # отклик остался в accepted) — вторая строка участия не создаётся
        repository = self._repo(response=self._accepted_response(), is_user_in_project=AsyncMock(return_value=True))

        # when
        await ProjectService(repository).confirm_join(1, 2)

        # then
        repository.add_participant.assert_not_called()
        repository.decrement_vacancy_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_confirm_join_double_request_creates_one_participation(self):
        # given: два «клика» подряд на одну и ту же заявку
        repository = self._stateful_repo(self._accepted_response())
        service = ProjectService(repository)

        # when
        first = await service.confirm_join(1, 2)
        second = await service.confirm_join(1, 2)

        # then: ровно одна строка участия, оба вызова успешны
        assert repository.participations == [(3, 2)]
        assert first is not None and second is not None

    @pytest.mark.asyncio
    async def test_confirm_join_noop_when_status_already_in_team(self):
        # given: именно состояние после первого успешного подтверждения —
        # строка участия создана, статус уже in_team. Именно к нему приходит
        # второй клик по кнопке.
        repository = self._stateful_repo(self._accepted_response())
        service = ProjectService(repository)
        await service.confirm_join(1, 2)

        # when
        await service.confirm_join(1, 2)

        # then: повтор — не ошибка и не новая строка участия
        assert repository.participations == [(3, 2)]
        assert repository.status_updates == [(1, "in_team")]

    @pytest.mark.asyncio
    async def test_confirm_join_rejects_repeat_after_user_left_project(self):
        # given: пользователь был в проекте, вышел, статус заявки — in_team.
        # Повторное подтверждение тут уже НЕ no-op: участие снято, заявка
        # терминальная, и вернуть 200 молча было бы враньём.
        response = self._accepted_response()
        response.status = "in_team"
        repository = self._repo(response=response, is_user_in_project=AsyncMock(return_value=False))

        # when / then
        with pytest.raises(ValidationError, match="accepted"):
            await ProjectService(repository).confirm_join(1, 2)
        repository.add_participant.assert_not_called()

    @pytest.mark.asyncio
    async def test_accept_invitation_takes_row_lock(self):
        # given
        repository = self._repo(response=self._pending_invitation())

        # when
        await ProjectService(repository).accept_invitation(5, 2)

        # then
        repository.get_response_by_id_for_update.assert_awaited_once_with(5)
        repository.add_participant.assert_awaited_once_with(3, 2)

    @pytest.mark.asyncio
    async def test_accept_invitation_is_noop_when_already_participant(self):
        # given: пользователь уже в проекте, приглашение висит pending
        repository = self._repo(
            response=self._pending_invitation(),
            is_user_in_project=AsyncMock(return_value=True),
            update_response_status=AsyncMock(return_value=None),
        )

        # when
        await ProjectService(repository).accept_invitation(5, 2)

        # then: главное — не вторая строка участия
        repository.add_participant.assert_not_called()
        repository.decrement_vacancy_count.assert_not_called()

    @pytest.mark.asyncio
    async def test_accept_invitation_double_request_creates_one_participation(self):
        # given
        repository = self._stateful_repo(self._pending_invitation())
        service = ProjectService(repository)

        # when
        await service.accept_invitation(5, 2)
        await service.accept_invitation(5, 2)

        # then
        assert repository.participations == [(3, 2)]

    @pytest.mark.asyncio
    async def test_accept_invitation_noop_when_status_already_accepted(self):
        # given: состояние после первого принятия — участие есть, статус accepted
        repository = self._stateful_repo(self._pending_invitation())
        service = ProjectService(repository)
        await service.accept_invitation(5, 2)

        # when: повторный клик «Принять»
        await service.accept_invitation(5, 2)

        # then
        assert repository.participations == [(3, 2)]
        assert repository.vacancy_decrements == []


class TestListAllResponses:
    """Тесты для ProjectService.list_all_responses (общий список откликов)"""

    @staticmethod
    def _make_row(
        *,
        response_id: int,
        project_id: int,
        workspace_id: int | None,
        type_: str = "response",
        status: str = "pending",
    ) -> Response:
        created = datetime(2026, 1, 1)
        row = Response(
            id=response_id,
            respondent_id=42,
            project_id=project_id,
            type=type_,
            status=status,
            created_at=created,
            updated_at=created,
        )
        workspace = None
        if workspace_id is not None:
            workspace = WorkSpace(id=workspace_id, name=f"Space {workspace_id}", author_id=1, status_id=1)
        row.project = Project(
            id=project_id, name=f"Project {project_id}", author_id=1, workspace_id=workspace_id, workspace=workspace
        )
        row.respondent = User(id=42, first_name="Анна", last_name="Петрова", email="anna@example.com")
        return row

    def _setup(
        self,
        *,
        role_name: str | None,
        editor_workspace_ids: list[int],
        rows: list[Response],
        allow_multi: bool = True,
        total: int | None = None,
    ) -> tuple[AsyncMock, ProjectService, Mock]:
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow

        editor_result = Mock()
        editor_result.scalars.return_value.all.return_value = editor_workspace_ids

        rows_result = Mock()
        rows_result.scalars.return_value.all.return_value = rows

        flags_result = Mock()
        flags_result.all.return_value = [(ws, allow_multi) for ws in {r.project.workspace_id for r in rows}]

        busy_result = Mock()
        busy_result.scalars.return_value.all.return_value = []

        # Ответы подбираются по тексту запроса, а не по порядку вызовов: у
        # глобального админа критерий видимости возвращается сразу, и запрос
        # за id пространств-редакторов не выполняется вовсе. Привязка к
        # позиции `[0]` ломалась вслед за любым изменением числа запросов.
        async def _execute(stmt: object) -> Mock:
            sql = str(stmt).lower()
            if "workspace_participation.workspace_id" in sql:
                return editor_result
            if "space_settings" in sql:
                return flags_result
            if "project_participation.participant_id" in sql:
                return busy_result
            return rows_result

        mock_session.scalar = AsyncMock(return_value=total if total is not None else len(rows))
        mock_session.execute = AsyncMock(side_effect=_execute)

        viewer = User(id=7, first_name="Пётр", last_name="Преподаватель", email="t@example.com")
        viewer.role = Role(id=2, name=role_name) if role_name else None
        return mock_session, ProjectService(mock_repository), viewer

    @staticmethod
    def _page_query(mock_session: AsyncMock) -> str:
        """SQL запроса выборки откликов (не одного из вспомогательных).

        `literal_binds` — чтобы условия читались как `response.type = 'invitation'`,
        а не как `:type_1`: проверять фильтры по месту.parameters куда менее читаемо.
        """
        for call in mock_session.execute.await_args_list:
            stmt = call.args[0]
            if "from response" not in str(stmt).lower():
                continue
            return str(stmt.compile(compile_kwargs={"literal_binds": True}))
        raise AssertionError("запрос выборки откликов не выполнялся")

    @pytest.mark.asyncio
    async def test_admin_should_see_all_projects_without_scope(self):
        # given
        row = self._make_row(response_id=1, project_id=3, workspace_id=7)
        mock_session, service, viewer = self._setup(role_name="admin", editor_workspace_ids=[], rows=[row])

        # when
        result = await service.list_all_responses(viewer, page=1, limit=20)

        # then
        assert result.total == 1
        assert result.total_pages == 1
        assert result.items[0].project_name == "Project 3"
        assert result.items[0].workspace_name == "Space 7"
        assert result.items[0].respondent_email == "anna@example.com"
        # Админ не ограничен: критерий видимости не добавляется к выборке
        page_query = self._page_query(mock_session)
        assert "project.author_id" not in page_query

    @pytest.mark.asyncio
    async def test_sentinel_all_should_not_narrow_the_query(self):
        # given
        row = self._make_row(response_id=1, project_id=3, workspace_id=7)
        mock_session, service, viewer = self._setup(role_name="admin", editor_workspace_ids=[], rows=[row])

        # when
        # «Все» на фронтенде отправляется как "all"; в БД таких значений нет,
        # поэтому условие вида Response.type == "all" вернуло бы ноль строк.
        await service.list_all_responses(viewer, page=1, limit=20, type_filter="all", status="all")

        # then
        # У admin scope тоже пустой, поэтому в запросе не должно быть WHERE вообще.
        count_query = str(mock_session.scalar.await_args_list[0].args[0])
        assert "WHERE" not in count_query.upper()

    @pytest.mark.asyncio
    async def test_teacher_should_be_scoped_to_own_and_editor_projects(self):
        # given
        row = self._make_row(response_id=1, project_id=3, workspace_id=7)
        mock_session, service, viewer = self._setup(role_name="teacher", editor_workspace_ids=[7, 9], rows=[row])

        # when
        result = await service.list_all_responses(viewer, page=1, limit=20)

        # then
        page_query = self._page_query(mock_session)
        assert "project.author_id = 7" in page_query
        # Порядок внутри IN не фиксирован: id пространств приходят из set,
        # поэтому сравниваем по составу, а не по строке целиком.
        in_list = re.search(r"project\.workspace_id IN \(([^)]*)\)", page_query)
        assert in_list, page_query
        assert {int(part) for part in in_list.group(1).split(",")} == {7, 9}
        assert result.items[0].id == 1

    @pytest.mark.asyncio
    async def test_teacher_without_editor_workspaces_should_see_only_own_projects(self):
        # given
        row = self._make_row(response_id=1, project_id=3, workspace_id=7)
        mock_session, service, viewer = self._setup(role_name="teacher", editor_workspace_ids=[], rows=[row])

        # when
        result = await service.list_all_responses(viewer, page=1, limit=20)

        # then
        page_query = self._page_query(mock_session)
        assert "project.author_id = 7" in page_query
        assert "workspace_id IN" not in page_query
        assert result.items[0].name == "Анна Петрова"

    @pytest.mark.asyncio
    async def test_filters_should_be_applied_before_pagination(self):
        # given
        row = self._make_row(response_id=1, project_id=3, workspace_id=7, type_="invitation", status="accepted")
        mock_session, service, viewer = self._setup(role_name="admin", editor_workspace_ids=[], rows=[row], total=41)

        # when
        result = await service.list_all_responses(
            viewer,
            page=3,
            limit=10,
            type_filter="invitation",
            status="accepted",
            workspace_id=7,
            project_id=3,
            search="anna",
        )

        # then
        assert result.total == 41
        assert result.total_pages == 5
        assert result.page == 3
        assert result.limit == 10
        page_query = self._page_query(mock_session)
        assert "response.type = 'invitation'" in page_query
        assert "response.status = 'accepted'" in page_query
        assert "project.workspace_id = 7" in page_query
        assert "response.project_id = 3" in page_query
        # ilike рендерится как lower(...) LIKE lower(...), а не оператором ILIKE.
        assert 'lower("user".first_name) LIKE lower(' in page_query
        assert "OFFSET" in page_query
        assert "ORDER BY response.created_at DESC" in page_query

    @pytest.mark.asyncio
    async def test_should_mark_busy_respondent_when_workspace_forbids_multi_participation(self):
        # given
        row = self._make_row(response_id=1, project_id=3, workspace_id=7, status="pending")
        mock_session, service, viewer = self._setup(
            role_name="admin", editor_workspace_ids=[], rows=[row], allow_multi=False
        )
        mock_session.execute = AsyncMock(
            side_effect=[
                self._rows_result(rows=[row]),
                self._flags_result([(7, False)]),
                self._busy_result([42]),
            ]
        )
        mock_session.scalar = AsyncMock(return_value=1)

        # when
        result = await service.list_all_responses(viewer, page=1, limit=20)

        # then
        assert result.items[0].status == "in_team"
        assert result.items[0].busy_in_other_project is True
        assert result.items[0].allow_multi_project_participation is False

    @staticmethod
    def _rows_result(*, rows: list[Response]) -> Mock:
        result = Mock()
        result.scalars.return_value.all.return_value = rows
        return result

    @staticmethod
    def _flags_result(rows: list[tuple[int, bool]]) -> Mock:
        result = Mock()
        result.all.return_value = rows
        return result

    @staticmethod
    def _busy_result(participant_ids: list[int]) -> Mock:
        result = Mock()
        result.scalars.return_value.all.return_value = participant_ids
        return result


class TestRemoveParticipant:
    """Тесты для ProjectService.remove_participant (автор или глобальный админ)"""

    def _setup(self, *, project_author_id: int = 1) -> tuple[Mock, Mock, AsyncMock]:
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        mock_repository.get_by_id = AsyncMock(return_value=Project(id=3, name="P", author_id=project_author_id))
        mock_repository.get_accepted_response_for_participant = AsyncMock(return_value=None)
        mock_repository.remove_participant = AsyncMock(return_value=True)
        return mock_repository, mock_uow, mock_session

    def _role_result(self, role_name: str | None) -> Mock:
        role_result = Mock()
        role_result.scalar_one_or_none.return_value = role_name
        return role_result

    @pytest.mark.asyncio
    async def test_should_allow_author_to_remove_participant(self):
        # given
        mock_repository, _, mock_session = self._setup(project_author_id=1)
        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.remove_participant(3, 42, current_user_id=1)

        # then
        assert result is True
        mock_session.execute.assert_not_called()
        mock_repository.remove_participant.assert_awaited_once_with(3, 42)

    @pytest.mark.asyncio
    async def test_should_allow_global_admin_to_remove_participant(self):
        # given
        mock_repository, _, mock_session = self._setup(project_author_id=1)
        mock_session.execute = AsyncMock(return_value=self._role_result("admin"))
        project_service = ProjectService(mock_repository)

        # when
        result = await project_service.remove_participant(3, 42, current_user_id=999)

        # then
        assert result is True
        mock_repository.remove_participant.assert_awaited_once_with(3, 42)

    @pytest.mark.asyncio
    async def test_should_deny_non_admin_non_author(self):
        # given
        mock_repository, _, mock_session = self._setup(project_author_id=1)
        mock_session.execute = AsyncMock(return_value=self._role_result("member"))
        project_service = ProjectService(mock_repository)

        # when / then
        with pytest.raises(PermissionError, match="Only project author or admin can remove participants"):
            await project_service.remove_participant(3, 42, current_user_id=999)
        mock_repository.remove_participant.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_deny_removing_project_author(self):
        # given
        mock_repository, _, mock_session = self._setup(project_author_id=1)
        mock_session.execute = AsyncMock(return_value=self._role_result("admin"))
        project_service = ProjectService(mock_repository)

        # when / then
        with pytest.raises(ValidationError, match="Cannot remove the project author"):
            await project_service.remove_participant(3, 1, current_user_id=999)
        mock_repository.remove_participant.assert_not_called()


class TestCancelInvitation:
    """Тесты для ProjectService.cancel_invitation (автор проекта либо админ пространства)"""

    def _setup(self, *, author_id: int = 1, workspace_id: int = 7) -> tuple[Mock, AsyncMock, ProjectService]:
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        mock_repository.get_response_by_id = AsyncMock(
            return_value=Response(id=5, respondent_id=2, project_id=3, type="invitation", status="pending")
        )
        mock_repository.get_by_id = AsyncMock(
            return_value=Project(id=3, name="P", author_id=author_id, workspace_id=workspace_id)
        )
        mock_repository.update_response_status = AsyncMock(return_value=Response(id=5, type="invitation"))

        async def _get(model, ident, *args, **kwargs):
            # session.get используется и для актёра уведомления, и для работы
            # пространства при проверке прав (WorkSpace в моке нет → None).
            if model is User:
                return User(id=2, first_name="Анна", last_name="Петрова", email="anna@example.com")
            return None

        mock_session.get = AsyncMock(side_effect=_get)
        mock_session.execute = AsyncMock(return_value=self._empty_result())
        return mock_repository, mock_session, ProjectService(mock_repository)

    @staticmethod
    def _empty_result() -> Mock:
        """Результат запроса без строк: нет ни глобальной роли, ни членства в пространстве."""
        result = Mock()
        result.scalar_one_or_none.return_value = None
        result.first.return_value = None
        return result

    @staticmethod
    def _role_result(role_name: str) -> Mock:
        role_result = Mock()
        role_result.scalar_one_or_none.return_value = role_name
        return role_result

    @staticmethod
    def _workspace_editor_result() -> Mock:
        editor_result = Mock()
        editor_result.first.return_value = object()
        return editor_result

    @pytest.mark.asyncio
    async def test_should_allow_author_to_cancel_invitation(self):
        # given
        mock_repository, _, project_service = self._setup(author_id=1)
        notification_service = Mock()
        notification_service.create_notification = AsyncMock()
        mail_service = Mock()
        mail_service.send_invitation_cancelled_email = AsyncMock(return_value=True)
        project_service._notification_service = notification_service
        project_service._mail_service = mail_service

        # when
        result = await project_service.cancel_invitation(5, current_user_id=1)

        # then
        assert result.id == 5
        mock_repository.update_response_status.assert_awaited_once_with(5, "cancelled")
        assert (
            notification_service.create_notification.await_args.kwargs["type"] == NotificationType.invitation_cancelled
        )
        mail_service.send_invitation_cancelled_email.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_allow_workspace_teacher_to_cancel_invitation(self):
        # given
        mock_repository, mock_session, project_service = self._setup(author_id=1)
        # первым запросом проверяется глобальная роль, вторым — роль в пространстве
        mock_session.execute = AsyncMock(
            side_effect=[self._role_result("teacher"), self._workspace_editor_result()],
        )

        # when
        await project_service.cancel_invitation(5, current_user_id=99)

        # then
        mock_repository.update_response_status.assert_awaited_once_with(5, "cancelled")

    @pytest.mark.asyncio
    async def test_should_deny_stranger_to_cancel_invitation(self):
        # given
        mock_repository, mock_session, project_service = self._setup(author_id=1)
        mock_session.execute = AsyncMock(
            side_effect=[self._role_result("member"), self._empty_result()],
        )

        # when / then
        with pytest.raises(PermissionError, match="Only project author or workspace admin can cancel invitations"):
            await project_service.cancel_invitation(5, current_user_id=99)
        mock_repository.update_response_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_not_cancel_non_pending_invitation(self):
        # given
        mock_repository, _, project_service = self._setup()
        mock_repository.get_response_by_id = AsyncMock(
            return_value=Response(id=5, respondent_id=2, project_id=3, type="invitation", status="accepted")
        )

        # when / then
        with pytest.raises(ValidationError, match="Can only cancel pending invitations"):
            await project_service.cancel_invitation(5, current_user_id=1)
        mock_repository.update_response_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_not_cancel_response(self):
        # given
        mock_repository, _, project_service = self._setup()
        mock_repository.get_response_by_id = AsyncMock(
            return_value=Response(id=5, respondent_id=2, project_id=3, type="response", status="pending")
        )

        # when / then
        with pytest.raises(ValidationError, match="This is not an invitation"):
            await project_service.cancel_invitation(5, current_user_id=1)
        mock_repository.update_response_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_raise_not_found_for_missing_invitation(self):
        # given
        mock_repository, _, project_service = self._setup()
        mock_repository.get_response_by_id = AsyncMock(return_value=None)

        # when / then
        with pytest.raises(NotFoundError, match="Invitation not found"):
            await project_service.cancel_invitation(5, current_user_id=1)
        mock_repository.update_response_status.assert_not_called()


class TestManageResponses:
    """Принять/отклонить отклик: общий состав прав и причина отказа.

    Права те же, что показывает фронт (``canManageProject``): автор проекта,
    глобальные admin/teacher, автор пространства и его admin/teacher.
    """

    @staticmethod
    def _result(role_name: str | None = None, *, editor: bool = False) -> Mock:
        """Результат запроса прав: роль из ``role`` + членство в пространстве."""
        result = Mock()
        result.scalar_one_or_none.return_value = role_name
        result.first.return_value = object() if editor else None
        return result

    def _setup(self, *, author_id: int = 1, workspace_id: int | None = None) -> tuple[Mock, AsyncMock, ProjectService]:
        mock_repository = Mock(spec=ProjectRepository)
        mock_uow = Mock()
        mock_session = AsyncMock()
        mock_uow.session = mock_session
        mock_repository.uow = mock_uow
        mock_repository.get_response_by_id = AsyncMock(
            return_value=Response(id=5, respondent_id=2, project_id=3, type="response", status="pending")
        )
        mock_repository.get_by_id = AsyncMock(
            return_value=Project(id=3, name="P", author_id=author_id, workspace_id=workspace_id)
        )
        mock_repository.update_response_status = AsyncMock(
            return_value=Response(id=5, type="response", status="rejected")
        )

        async def _get(model, ident, *args, **kwargs):
            # session.get нужен и для актёра уведомления, и для проверки
            # авторства пространства (в моке WorkSpace не подставляем).
            if model is User:
                return User(id=99, first_name="Иван", last_name="Иванов", email="ivan@example.com")
            return None

        mock_session.get = AsyncMock(side_effect=_get)
        mock_session.execute = AsyncMock(return_value=self._result(None))
        return mock_repository, mock_session, ProjectService(mock_repository)

    @pytest.mark.asyncio
    async def test_should_pass_reason_to_repository_when_rejecting(self):
        # given
        mock_repository, _, project_service = self._setup(author_id=1)

        # when
        result = await project_service.reject_response(5, author_id=1, reason="Не хватает опыта")

        # then: причина уезжает в ту же транзакцию, что и статус
        assert result.status == "rejected"
        mock_repository.update_response_status.assert_awaited_once_with(
            5, "rejected", rejection_reason="Не хватает опыта"
        )

    @pytest.mark.asyncio
    async def test_should_reject_without_reason(self):
        # given
        mock_repository, _, project_service = self._setup(author_id=1)

        # when: причина не передана — отказ «без причины»
        await project_service.reject_response(5, author_id=1)

        # then
        mock_repository.update_response_status.assert_awaited_once_with(5, "rejected", rejection_reason=None)

    @pytest.mark.asyncio
    async def test_should_allow_workspace_editor_to_reject(self):
        # given: не автор проекта, но admin/teacher пространства
        mock_repository, mock_session, project_service = self._setup(author_id=1, workspace_id=7)
        mock_session.execute = AsyncMock(
            side_effect=[self._result("member"), self._result(editor=True)],
        )

        # when
        await project_service.reject_response(5, author_id=99, reason="Не подходит")

        # then
        mock_repository.update_response_status.assert_awaited_once_with(5, "rejected", rejection_reason="Не подходит")

    @pytest.mark.asyncio
    async def test_should_allow_workspace_editor_to_accept(self):
        # given
        mock_repository, mock_session, project_service = self._setup(author_id=1, workspace_id=7)
        mock_session.execute = AsyncMock(
            side_effect=[self._result("member"), self._result(editor=True)],
        )

        # when
        await project_service.accept_response(5, author_id=99)

        # then
        mock_repository.update_response_status.assert_awaited_once_with(5, "accepted")

    @pytest.mark.asyncio
    async def test_should_allow_global_teacher_without_workspace(self):
        # given: глобальный teacher управляет откликами любого проекта
        mock_repository, mock_session, project_service = self._setup(author_id=1, workspace_id=None)
        mock_session.execute = AsyncMock(return_value=self._result("teacher"))

        # when
        await project_service.reject_response(5, author_id=99)

        # then
        mock_repository.update_response_status.assert_awaited_once_with(5, "rejected", rejection_reason=None)

    @pytest.mark.asyncio
    async def test_should_deny_stranger_to_reject(self):
        # given: ни автор, ни роли, ни прав в пространстве
        mock_repository, mock_session, project_service = self._setup(author_id=1, workspace_id=7)
        mock_session.execute = AsyncMock(
            side_effect=[self._result("member"), self._result()],
        )

        # when / then
        with pytest.raises(PermissionError, match="not allowed to reject"):
            await project_service.reject_response(5, author_id=99, reason="Причина")
        mock_repository.update_response_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_deny_stranger_to_accept(self):
        # given
        mock_repository, mock_session, project_service = self._setup(author_id=1, workspace_id=7)
        mock_session.execute = AsyncMock(
            side_effect=[self._result("member"), self._result()],
        )

        # when / then
        with pytest.raises(PermissionError, match="not allowed to accept"):
            await project_service.accept_response(5, author_id=99)
        mock_repository.update_response_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_reject_only_pending_responses(self):
        # given
        mock_repository, _, project_service = self._setup(author_id=1)
        mock_repository.get_response_by_id = AsyncMock(
            return_value=Response(id=5, respondent_id=2, project_id=3, type="response", status="accepted")
        )

        # when / then
        with pytest.raises(ValidationError, match="Can only reject pending responses"):
            await project_service.reject_response(5, author_id=1, reason="Поздно")
        mock_repository.update_response_status.assert_not_called()
