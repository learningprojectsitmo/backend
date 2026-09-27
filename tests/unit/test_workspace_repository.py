from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from src.repository.workspace_repository import WorkSpaceRepository


def _make_result(*, scalar: int | None = 0, rows: list | None = None) -> Mock:
    """Заглушка результата execute: count отдаёт scalar, выборка — mappings().all()."""
    result = Mock()
    result.scalar.return_value = scalar
    result.mappings.return_value.all.return_value = rows if rows is not None else []
    return result


def _make_repository() -> tuple[WorkSpaceRepository, AsyncMock]:
    """Репозиторий с перехваченными запросами — execute заменён на AsyncMock."""
    uow = Mock()
    uow.session = Mock()
    uow.session.execute = AsyncMock(side_effect=[_make_result(), _make_result()])
    return WorkSpaceRepository(uow), uow.session.execute


def _sql_of(call_args: tuple) -> str:
    """Компилирует перехваченный SELECT в читаемый SQL с подставленными литералами.

    Нужен postgresql-dialect: фильтр по датам делает cast(str -> Date), у которого
    для дефолтного диалекта нет рендерера литералов.
    """
    query: Select = call_args[0]
    compiled = query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    return str(compiled)


class TestGetParticipantsProjectFilter:
    """Фильтр по проектам: ИЛИ-семантика по списку id"""

    @pytest.mark.asyncio
    async def test_should_filter_by_all_given_project_ids(self):
        """Несколько проектов должны попадать в один IN, а не схлопываться в один id"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, project_ids=[3, 4])

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "project_participation.project_id IN (3, 4)" in sql

    @pytest.mark.asyncio
    async def test_should_filter_by_single_project_id(self):
        """Один проект — регрессия: IN из одного элемента, а не пустой IN"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, project_ids=[3])

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "project_participation.project_id IN (3)" in sql
        assert "IN ()" not in sql

    @pytest.mark.asyncio
    async def test_should_not_filter_by_project_when_list_is_empty(self):
        """Пустой список — фильтр выключен (иначе «выбрать все» прятал бы участников без проектов)"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, project_ids=[])

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "project_participation.project_id IN" not in sql

    @pytest.mark.asyncio
    async def test_should_not_filter_by_project_when_omitted(self):
        """Без аргумента фильтра проектов в запросе нет"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1)

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "project_participation.project_id IN" not in sql

    @pytest.mark.asyncio
    async def test_should_apply_project_filter_to_count_query_too(self):
        """Фильтр должен попасть и в count, иначе пагинация насчитает не то"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, project_ids=[3, 4])

        # then
        count_sql = _sql_of(execute.await_args_list[0].args)
        assert "project_participation.project_id IN (3, 4)" in count_sql


class TestGetParticipantsRoleFilter:
    """Фильтр по ролям: role_id в workspace_participation"""

    @pytest.mark.asyncio
    async def test_should_filter_by_all_given_role_ids(self):
        """Несколько ролей — один IN по role_id"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, role_ids=[55, 57])

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "workspace_participation.role_id IN (55, 57)" in sql

    @pytest.mark.asyncio
    async def test_should_not_filter_by_role_when_list_is_empty(self):
        """Пустой список ролей — фильтр выключен"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, role_ids=[])

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "workspace_participation.role_id IN" not in sql

    @pytest.mark.asyncio
    async def test_should_apply_role_filter_to_count_query_too(self):
        """Фильтр по ролям должен попасть и в count"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, role_ids=[57])

        # then
        count_sql = _sql_of(execute.await_args_list[0].args)
        assert "workspace_participation.role_id IN (57)" in count_sql


class TestGetParticipantsFiltersCombined:
    """Совместная работа фильтров"""

    @pytest.mark.asyncio
    async def test_should_combine_project_and_role_filters_with_and(self):
        """Проекты и роли — одновременно, оба попадают в один SELECT"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, project_ids=[3], role_ids=[55, 56])

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "project_participation.project_id IN (3)" in sql
        assert "workspace_participation.role_id IN (55, 56)" in sql

    @pytest.mark.asyncio
    async def test_should_always_scope_project_filter_to_the_workspace(self):
        """Проект из чужого пространства не должен подтягивать участников"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, project_ids=[3])

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "project.workspace_id = 1" in sql


class TestGetParticipantsWithoutProjectFilter:
    """Фильтр «без проекта» — единственный способ найти людей без проектов"""

    @pytest.mark.asyncio
    async def test_should_exclude_participants_with_projects(self):
        """Ветка «без проекта» строит NOT по подзапросу участия в проектах"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, without_project=True)

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "NOT IN" in sql
        assert "project_participation.participant_id" in sql

    @pytest.mark.asyncio
    async def test_should_scope_without_project_to_the_workspace(self):
        """Проекты в других пространствах не считаются — иначе «без проекта» врёт"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, without_project=True)

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "project.workspace_id = 1" in sql

    @pytest.mark.asyncio
    async def test_should_not_filter_when_flag_is_false(self):
        """Выключенный флаг не должен добавлять условий"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, without_project=False)

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "NOT IN" not in sql

    @pytest.mark.asyncio
    async def test_should_not_filter_by_default(self):
        """Без аргумента фильтр выключен"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1)

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "NOT IN" not in sql

    @pytest.mark.asyncio
    async def test_should_combine_selected_projects_and_without_project_with_or(self):
        """Выбранные проекты и «без проекта» — две ветки ИЛИ, не И"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, project_ids=[3], without_project=True)

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "OR" in sql
        assert "project_participation.project_id IN (3)" in sql
        assert "NOT IN" in sql

    @pytest.mark.asyncio
    async def test_should_apply_without_project_to_count_query_too(self):
        """Фильтр должен попасть и в count, иначе пагинация врёт"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, without_project=True)

        # then
        count_sql = _sql_of(execute.await_args_list[0].args)
        assert "NOT IN" in count_sql


class TestGetParticipantsHasResumeFilter:
    """Фильтр по наличию резюме"""

    @pytest.mark.asyncio
    async def test_should_keep_only_with_resume(self):
        """has_resume=True оставляет только тех, у кого резюме есть"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, has_resume=True)

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "resume_id IS NOT NULL" in sql

    @pytest.mark.asyncio
    async def test_should_keep_only_without_resume(self):
        """has_resume=False оставляет только тех, у кого резюме нет"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, has_resume=False)

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "resume_id IS NULL" in sql

    @pytest.mark.asyncio
    async def test_should_not_filter_when_omitted(self):
        """None — фильтр выключен, в запросе нет условия на резюме"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1)

        # then
        sql = _sql_of(execute.await_args_list[-1].args)
        assert "resume_id IS NULL" not in sql
        assert "resume_id IS NOT NULL" not in sql

    @pytest.mark.asyncio
    async def test_should_apply_to_count_query_too(self):
        """Фильтр по резюме должен попасть и в count"""
        # given
        repository, execute = _make_repository()

        # when
        await repository.get_participants(workspace_id=1, has_resume=False)

        # then
        count_sql = _sql_of(execute.await_args_list[0].args)
        assert "resume_id IS NULL" in count_sql
