from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

from src.model.project import ProjectParticipation
from src.repository.project_repository import ProjectRepository


def _scalars_result(*rows: object) -> Mock:
    """Заглушка результата execute для запросов вида select(Entity)."""
    result = Mock()
    result.scalars.return_value.first.return_value = rows[0] if rows else None
    result.scalars.return_value.all.return_value = list(rows)
    return result


def _make_repository(*results: Mock) -> tuple[ProjectRepository, Mock]:
    """Репозиторий с перехваченной сессией: execute/add/delete/flush — заглушки."""
    uow = Mock()
    uow.session = Mock()
    uow.session.execute = AsyncMock(side_effect=list(results))
    uow.session.add = Mock()
    uow.session.delete = AsyncMock()
    uow.session.flush = AsyncMock()
    return ProjectRepository(uow), uow.session


def _sql_of(query: Select) -> str:
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestAddParticipant:
    """Идемпотентное добавление участника.

    Регрессия: на проде у человека накопились четыре строки участия на пару
    (project_id, participant_id) — по одной на каждый клик по кнопке
    подтверждения. Репозиторий обязан вернуть существующую строку, а не вставить
    вторую.
    """

    @pytest.mark.asyncio
    async def test_should_return_existing_row_without_insert(self):
        # given: участие уже есть
        existing = ProjectParticipation(id=46, project_id=21, participant_id=36)
        repository, session = _make_repository(_scalars_result(existing))

        # when
        result = await repository.add_participant(21, 36)

        # then: вернули ту же строку, новую не вставляли
        assert result is existing
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_insert_when_no_row_exists(self):
        # given
        repository, session = _make_repository(_scalars_result())

        # when
        result = await repository.add_participant(21, 36)

        # then
        assert result.project_id == 21
        assert result.participant_id == 36
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_query_exact_pair_with_limit(self):
        # given: если не ограничить выборку, вернётся «какая-то» строка, а не
        # именно участие этой пары
        repository, session = _make_repository(_scalars_result())

        # when
        await repository.add_participant(21, 36)

        # then
        sql = _sql_of(session.execute.await_args.args[0])
        assert "project_participation.project_id = 21" in sql
        assert "project_participation.participant_id = 36" in sql
        assert "LIMIT" in sql


class TestRemoveParticipant:
    """Удаление снимает ВСЕ строки участия на пару.

    Удаление одной строки оставляло человека в команде: список участников
    строится по project_participation, а `scalar_one_or_none` на второй строке
    падал бы с MultipleResultsFound.
    """

    @pytest.mark.asyncio
    async def test_should_delete_every_duplicate_row(self):
        # given: исторические дубли
        repository, session = _make_repository(
            _scalars_result(
                ProjectParticipation(id=46, project_id=21, participant_id=36),
                ProjectParticipation(id=47, project_id=21, participant_id=36),
                ProjectParticipation(id=48, project_id=21, participant_id=36),
                ProjectParticipation(id=49, project_id=21, participant_id=36),
            )
        )

        # when
        result = await repository.remove_participant(21, 36)

        # then
        assert result is True
        assert session.delete.await_count == 4

    @pytest.mark.asyncio
    async def test_should_use_orm_delete_to_keep_audit_trail(self):
        # given: audit_listeners вешает before_delete на ORM-delete; на bulk
        # delete() он не срабатывает и запись о снятии участника теряется
        repository, session = _make_repository(
            _scalars_result(ProjectParticipation(id=46, project_id=21, participant_id=36))
        )

        # when
        await repository.remove_participant(21, 36)

        # then: session.delete у объекта, а не bulk-запрос
        deleted = session.delete.await_args.args[0]
        assert isinstance(deleted, ProjectParticipation)

    @pytest.mark.asyncio
    async def test_should_return_false_when_not_participant(self):
        # given
        repository, session = _make_repository(_scalars_result())

        # when
        result = await repository.remove_participant(21, 36)

        # then
        assert result is False
        session.delete.assert_not_called()
