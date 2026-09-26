from __future__ import annotations

import inspect
import json
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import Mock

import pytest
from sqlalchemy.sql.dml import Insert

from src.core import audit_listeners as al
from src.core.audit_context import clear_audit_context, set_audit_context
from src.model.audit import AuditLog

RESOLVERS = (
    al._self_project_id,
    al._project_id_via_task,
    al._project_id_via_specification,
)


class FakeConnection:
    """Минимальная заглушка соединения: пишет insert(AuditLog) в память."""

    def __init__(self, scalar: object = None) -> None:
        self.inserted: list[dict] = []
        self._scalar = scalar

    def execute(self, statement, *_args, **_kwargs):
        # select(...) → возвращаем заранее заданный скаляр
        if isinstance(statement, Insert):
            self.inserted.append(dict(statement.compile().params))
        return SimpleNamespace(scalar_one_or_none=lambda: self._scalar)


class TestResolverContract:
    """Контракт резолверов project_id.

    Регрессия: `_self_project_id` когда-то принимал один аргумент, а
    `_resolve_project_id` вызывал его как `resolver(connection, target)`.
    TypeError попадал в широкой `except Exception` внутри `_audit_*`, и запись
    аудита молча не создавалась — без единого падения в тестах.
    """

    @pytest.mark.parametrize("resolver", RESOLVERS)
    def test_should_accept_connection_and_target(self, resolver) -> None:
        # given
        signature = inspect.signature(resolver)

        # then
        assert list(signature.parameters) == ["connection", "target"]

    @pytest.mark.parametrize("resolver", RESOLVERS)
    def test_should_be_callable_by_resolve_project_id(self, resolver) -> None:
        # given
        connection = FakeConnection(scalar=7)
        target = SimpleNamespace(project_id=7, task_id=1, specification_id=1)

        # when / then
        assert al._resolve_project_id(connection, target, resolver) == 7

    def test_should_pass_int_through_without_calling(self) -> None:
        # given
        connection = FakeConnection()

        # when
        result = al._resolve_project_id(connection, SimpleNamespace(), 42)

        # then
        assert result == 42
        assert connection.inserted == []

    def test_should_return_none_for_missing_resolver(self) -> None:
        # given
        connection = FakeConnection()

        # when
        result = al._resolve_project_id(connection, SimpleNamespace(), None)

        # then
        assert result is None

    def test_should_skip_when_parent_already_removed(self) -> None:
        # given
        connection = FakeConnection(scalar=None)

        # when / then
        with pytest.raises(al._SkipAudit):
            al._resolve_project_id(connection, SimpleNamespace(task_id=9), al._project_id_via_task)


class TestInsertLog:
    """Запись строки журнала на соединении текущей транзакции."""

    def test_should_write_row_with_project_id_and_context(self) -> None:
        # given
        connection = FakeConnection()
        set_audit_context(4, "10.0.0.1", "pytest")

        try:
            # when
            al._insert_log(
                connection,
                entity_type="task",
                entity_id=3,
                action="INSERT",
                project_id=7,
                old_values=None,
                new_values={"title": "Дизайн"},
            )
        finally:
            clear_audit_context()

        # then
        assert len(connection.inserted) == 1
        row = connection.inserted[0]
        assert row["entity_type"] == "task"
        assert row["entity_id"] == 3
        assert row["action"] == "INSERT"
        assert row["project_id"] == 7
        assert row["performed_by"] == 4
        assert row["ip_address"] == "10.0.0.1"
        assert row["user_agent"] == "pytest"
        assert json.loads(row["new_values"]) == {"title": "Дизайн"}
        assert row["old_values"] is None

    def test_should_write_null_actor_without_context(self) -> None:
        # given
        connection = FakeConnection()
        clear_audit_context()

        # when
        al._insert_log(
            connection,
            entity_type="project",
            entity_id=1,
            action="INSERT",
            project_id=1,
            old_values=None,
            new_values={"name": "Expedition"},
        )

        # then
        row = connection.inserted[0]
        assert row["performed_by"] is None
        assert row["ip_address"] is None


class TestAuditHelpers:
    """Логирование событий верхнего уровня."""

    def test_should_log_insert_for_project_scoped_entity(self) -> None:
        # given
        connection = FakeConnection(scalar=7)
        target = SimpleNamespace(id=1, project_id=7, name="Expedition")
        mapper = Mock(columns=[])

        # when
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(al, "_model_to_dict", lambda _obj: {"name": "Expedition"})
            al._audit_insert(mapper, connection, target, "project", al._self_project_id)

        # then
        assert connection.inserted[0]["project_id"] == 7
        assert connection.inserted[0]["entity_type"] == "project"
        assert connection.inserted[0]["action"] == "INSERT"

    def test_should_not_write_when_cascade_removes_parent(self) -> None:
        # given
        connection = FakeConnection(scalar=None)
        target = SimpleNamespace(id=1, task_id=9, title="Подзадача")
        mapper = Mock(columns=[])

        # when
        al._audit_delete(mapper, connection, target, "subtask", al._project_id_via_task)

        # then
        assert connection.inserted == []

    def test_should_skip_update_without_loaded_identity(self) -> None:
        # given — эмулируем before_update для ещё не сохранённого объекта
        connection = FakeConnection(scalar=7)
        target = SimpleNamespace(id=1, project_id=7)
        mapper = Mock(columns=[])

        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(al, "_get_old_values", lambda *_: None)
            monkeypatch.setattr(al, "_model_to_dict", lambda _obj: {})

            # when
            al._audit_update(mapper, connection, target, "task", al._self_project_id)

        # then
        assert connection.inserted == []

    def test_should_survive_broken_resolver_without_raising(self) -> None:
        # given — регрессия: ошибка аудита не должна ломать бизнес-операцию
        connection = FakeConnection(scalar=7)
        target = SimpleNamespace(id=1, project_id=7)
        mapper = Mock(columns=[])

        def broken(*_args):
            raise TypeError("broken resolver")

        # when / then — исключение не пробрасывается
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(al, "_model_to_dict", lambda _obj: {})
            al._audit_insert(mapper, connection, target, "project", broken)
        assert connection.inserted == []


class TestRegisteredListeners:
    """Все проектные сущности должны иметь зарегистрированные listeners."""

    EXPECTED: ClassVar[dict[str, set[str]]] = {
        "user": {"before_update", "after_insert"},
        "resume": {"before_update", "after_insert", "after_delete"},
        "project": {"after_insert", "before_update", "after_delete"},
        "response": {"after_insert", "before_update", "after_delete"},
        "project_participation": {"after_insert", "after_delete"},
        "stage_transition": {"after_insert"},
        "specification": {"after_insert", "before_update"},
        "specification_comment": {"after_insert", "after_delete"},
        "column": {"after_insert", "before_update", "after_delete"},
        "task": {"after_insert", "before_update", "after_delete"},
        "subtask": {"after_insert", "before_update", "after_delete"},
        "task_assignee": {"after_insert", "after_delete"},
    }

    def test_should_cover_every_expected_entity_and_event(self) -> None:
        # given
        found: dict[str, set[str]] = {}
        for name, func in vars(al).items():
            if not name.startswith("audit_") or not callable(func):
                continue
            entity_type, event = _parse_listener_name(name)
            if entity_type in self.EXPECTED:
                found.setdefault(entity_type, set()).add(event)

        # then
        assert found == self.EXPECTED

    def test_should_keep_project_scoped_resolver_arity(self) -> None:
        # given
        checked = 0

        # then — каждый listener, передающий резолвер, использует совместимый
        for name, func in vars(al).items():
            if not name.startswith("audit_") or not callable(func):
                continue
            for call in _iter_calls(func):
                if call in RESOLVERS:
                    inspect.signature(call).bind(None, None)
                    checked += 1

        assert checked > 0

    def test_should_reference_existing_audit_log_columns(self) -> None:
        # given
        columns = {c.name for c in AuditLog.__table__.columns}

        # then
        assert {"entity_type", "entity_id", "action", "old_values", "new_values", "project_id"} <= columns


def _parse_listener_name(name: str) -> tuple[str, str]:
    """`audit_task_assignee_insert` → ("task_assignee", "after_insert")."""
    body = name.removeprefix("audit_")
    for suffix, event in (("insert", "after_insert"), ("update", "before_update"), ("delete", "after_delete")):
        if body.endswith(f"_{suffix}"):
            return body.removesuffix(f"_{suffix}"), event
    raise AssertionError(f"Не распознано имя listener: {name}")


def _iter_calls(func) -> list[object]:
    """Аргумент-резолверы, переданные в вызовы `_audit_*` внутри функции."""
    found: list[object] = []
    try:
        source = inspect.getsource(func)
    except (OSError, TypeError):
        return found
    for resolver in RESOLVERS:
        if resolver.__name__ in source:
            found.append(resolver)
    return found
