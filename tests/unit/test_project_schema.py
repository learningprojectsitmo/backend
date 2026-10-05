from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.schema import CreateIndex

from src.model.project import Project, ProjectParticipation, ProjectVacancy, Response
from src.model.user import User
from src.model.workspace import WorkSpaceParticipation
from src.schema.project import (
    MAX_VACANCY_TASK_LENGTH,
    PROJECT_AUTHOR_ROLE,
    ProjectFull,
    VacancyCreate,
    VacancyUpdate,
)

#: ``VacancyUpdate`` наследует валидаторы ``VacancyCreate``, поэтому правила
#: проверяются на обоих: правка проекта не должна принимать то, что отвергает
#: создание.
VACANCY_SCHEMAS = [VacancyCreate, VacancyUpdate]


@pytest.mark.parametrize("schema", VACANCY_SCHEMAS)
class TestVacancyTaskValidation:
    """Валидация задач роли: пустые, слишком длинные, повторяющиеся."""

    @pytest.mark.parametrize("tasks", [[], [""], ["   "], ["", "  ", "\n"]])
    def test_should_reject_role_without_tasks(self, schema, tasks):
        # given / when / then
        with pytest.raises(ValidationError):
            schema(title="Backend", tasks=tasks, required_count=1)

    def test_should_trim_tasks_and_drop_empty_ones(self, schema):
        # given
        payload = {"title": " Backend ", "tasks": ["  развернуть  ", "   ", "тесты"], "required_count": 1}

        # when
        vacancy = schema(**payload)

        # then
        assert vacancy.tasks == ["развернуть", "тесты"]
        assert vacancy.title == "Backend"

    def test_should_reject_task_over_length_limit(self, schema):
        # given
        too_long = "x" * (MAX_VACANCY_TASK_LENGTH + 1)

        # when / then
        with pytest.raises(ValidationError, match="длиннее"):
            schema(title="Backend", tasks=[too_long], required_count=1)

    def test_should_accept_task_at_length_limit(self, schema):
        # given
        at_limit = "x" * MAX_VACANCY_TASK_LENGTH

        # when
        vacancy = schema(title="Backend", tasks=[at_limit], required_count=1)

        # then
        assert vacancy.tasks == [at_limit]

    @pytest.mark.parametrize(
        "tasks",
        [
            ["тесты", "тесты"],
            ["a", "b", "a"],
            ["  деплой  ", "деплой"],
            ["x", "y", "z", "x", "y"],
        ],
    )
    def test_should_reject_duplicate_tasks(self, schema, tasks):
        # given / when / then
        with pytest.raises(ValidationError, match="не должны повторяться"):
            schema(title="Backend", tasks=tasks, required_count=1)

    def test_should_name_only_repeated_tasks_in_error(self, schema):
        # given: повтор только у второй задачи, чтобы в сообщении не было лишнего
        payload = {"title": "Backend", "tasks": ["тесты", "деплой", "тесты"], "required_count": 1}

        # when / then
        with pytest.raises(ValidationError) as exc:
            schema(**payload)
        message = str(exc.value)
        assert "«тесты»" in message
        assert "«деплой»" not in message

    def test_should_allow_same_task_in_different_roles(self, schema):
        # given: одинаковая задача допустима, запрет только внутри одной роли
        first = schema(title="Backend", tasks=["деплой"], required_count=1)
        second = schema(title="QA", tasks=["деплой"], required_count=1)

        # when / then
        assert first.tasks == second.tasks == ["деплой"]

    def test_should_reject_blank_title(self, schema):
        # given / when / then
        with pytest.raises(ValidationError, match="Роль не может быть пустой"):
            schema(title="   ", tasks=["деплой"], required_count=1)

    def test_should_reject_title_over_length_limit(self, schema):
        # given
        too_long = "x" * 201

        # when / then
        with pytest.raises(ValidationError):
            schema(title=too_long, tasks=["деплой"], required_count=1)


class TestVacancyUpdateSchema:
    """Различия между созданием и обновлением роли."""

    def test_should_keep_id_when_present(self):
        # given / when
        vacancy = VacancyUpdate(id=42, title="Backend", tasks=["деплой"], required_count=2)

        # then
        assert vacancy.id == 42

    def test_should_allow_missing_id_for_new_role(self):
        # given: роль, добавленная прямо в форме правки, id ещё не имеет
        vacancy = VacancyUpdate(title="Frontend", tasks=["вёрстка"], required_count=1)

        # then
        assert vacancy.id is None


class TestProjectTeamMembers:
    """Роль и резюме в таблице команды (`ProjectFull.members`)."""

    @staticmethod
    def _project_with_team() -> Project:
        """Проект: автор, принятый участник и участник без принятого отклика."""
        author = User(id=1, first_name="Анна", last_name="Иванова", email="anna@test.ru")
        accepted_user = User(id=2, first_name="Пётр", last_name="Сидоров", email="petr@test.ru")
        manual_user = User(id=3, first_name="Ноля", last_name="Роль", email="nolia@test.ru")

        vacancy = ProjectVacancy(id=5, project_id=1, title="Backend", tasks=["развернуть"], required_count=1)

        accepted = Response(
            id=10,
            respondent_id=2,
            project_id=1,
            vacancy_id=5,
            type="response",
            status="accepted",
            resume_id=99,
        )
        accepted.vacancy = vacancy
        accepted.respondent = accepted_user
        accepted.resume_id = 99

        project = Project(
            id=1,
            name="Проект",
            author_id=1,
            workspace_id=7,
            stage_pending_approval=False,
        )
        project.tags = []
        project.status = None
        project.project_type = None
        project.current_stage = None
        project.stage_transitions = []
        project.responses = [accepted]
        project.vacancies = [vacancy]
        project.participants = [
            ProjectParticipation(id=1, project_id=1, participant_id=1, participant=author),
            ProjectParticipation(id=2, project_id=1, participant_id=2, participant=accepted_user),
            ProjectParticipation(id=3, project_id=1, participant_id=3, participant=manual_user),
        ]
        return project

    def test_should_fill_role_and_resume_from_accepted_response(self):
        # given
        project = self._project_with_team()

        # when
        members = ProjectFull.from_orm(project).members

        # then: участник, принятый по отклику, показывает роль и резюме
        accepted = next(m for m in members if m.user_id == 2)
        assert accepted.role == "Backend"
        assert accepted.resume_url == "/app/resume?id=99&workspaceId=7"

    def test_should_mark_project_author_as_author(self):
        # given: автора добавляют в участники при создании, без отклика
        project = self._project_with_team()

        # when
        members = ProjectFull.from_orm(project).members

        # then: роль не пустая, иначе колонка выглядит как «данных нет»
        author = next(m for m in members if m.user_id == 1)
        assert author.role == PROJECT_AUTHOR_ROLE

    def test_should_leave_resume_empty_without_accepted_response(self):
        # given: участник добавлен вручную, принятого отклика нет
        project = self._project_with_team()

        # when
        members = ProjectFull.from_orm(project).members

        # then: резюма нет — пустая ячейка ожидаема, а не потерянный URL
        manual = next(m for m in members if m.user_id == 3)
        assert manual.role == ""
        assert manual.resume_url == ""

    def test_should_not_use_pending_response_role(self):
        # given: отклик ещё не принят — человек в команде, но роль не закреплена
        project = self._project_with_team()
        project.responses[0].status = "pending"

        # when
        members = ProjectFull.from_orm(project).members

        # then
        accepted = next(m for m in members if m.user_id == 2)
        assert accepted.role == ""
        assert accepted.resume_url == ""


class TestParticipationUniqueIndexes:
    """Уникальность пары (проект, участник) и (пространство, участник).

    Регрессия: в `project_participation` накопились четыре строки на пару
    (21, 36) — по одной на каждый клик по кнопке подтверждения. Список
    участников проекта строится по этим строкам, поэтому человек показывался
    четырежды, а `participants_count` завышался.

    Проверяем именно `unique=True` в модели, а не только наличие индекса:
    неуникальный индекс по той же паре колонок не защищает от дублей, но
    выглядит в схеме почти так же — регрессия прошла бы незамеченной.
    """

    @staticmethod
    def _index(table, name: str):
        return next(idx for idx in table.indexes if idx.name == name)

    def test_project_participation_pair_is_unique(self):
        # given / when
        index = self._index(ProjectParticipation.__table__, "uq_pp_project_participant")

        # then
        assert index.unique is True
        assert [col.name for col in index.columns] == ["project_id", "participant_id"]

    def test_workspace_participation_pair_is_unique(self):
        # given / when
        index = self._index(WorkSpaceParticipation.__table__, "uq_wp_workspace_participant")

        # then
        assert index.unique is True
        assert [col.name for col in index.columns] == ["workspace_id", "participant_id"]

    def test_participation_indexes_reject_multiples_in_create_all(self):
        # given: DDL, который SQLAlchemy генерирует из моделей
        statements = {
            index.name: str(CreateIndex(index))
            for table in (ProjectParticipation.__table__, WorkSpaceParticipation.__table__)
            for index in table.indexes
        }

        # then: обе пары объявляются как UNIQUE на уровне самой схемы
        assert "CREATE UNIQUE INDEX uq_pp_project_participant" in statements["uq_pp_project_participant"]
        assert "CREATE UNIQUE INDEX uq_wp_workspace_participant" in statements["uq_wp_workspace_participant"]

    def test_reverse_lookup_index_stays_non_unique(self):
        # given / when: обратный список «проекты пользователя» / «пространства
        # пользователя» — там дубли как раз законны
        project_index = self._index(ProjectParticipation.__table__, "ix_pp_participant")
        workspace_index = self._index(WorkSpaceParticipation.__table__, "ix_wp_participant")

        # then
        assert project_index.unique is not True
        assert workspace_index.unique is not True
