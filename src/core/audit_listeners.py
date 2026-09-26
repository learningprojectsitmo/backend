from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from json import dumps
from typing import Any

from sqlalchemy import event, insert, select
from sqlalchemy.inspection import inspect as sqlalchemy_inspect

from src.core.audit_context import get_audit_context
from src.core.logging_config import get_logger
from src.model.audit import AuditLog
from src.model.kanban_models import Column, Subtask, Task, TaskAssignee
from src.model.project import (
    Project,
    ProjectParticipation,
    ProjectSpecification,
    Response,
    SpecificationComment,
    StageTransition,
)
from src.model.resume import Resume
from src.model.user import User


def _safe_value(value):
    """Конвертация значений, не поддерживаемых JSON."""
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _safe_dumps(obj) -> str:
    """json.dumps с обработкой несериализуемых типов SQLAlchemy."""
    return dumps(obj, default=_safe_value)


logger = get_logger(__name__)


def _model_to_dict(obj) -> dict:
    """Конвертирование ORM объекта в словарь"""
    result = {}
    mapper = sqlalchemy_inspect(obj.__class__)

    for column in mapper.columns:
        value = getattr(obj, column.name, None)

        if isinstance(value, datetime):
            value = value.isoformat()
        result[column.name] = value
    return result


SERVICE_COLUMNS = {"id", "created_at", "updated_at"}


def _get_old_values(mapper, target) -> dict | None:
    """Получить cтарые значения для before_update listener'а.

    Возвращает None, если значимые (не служебные) колонки не изменились —
    например, при обновлении только `updated_at` (onupdate). Это отсекает
    дублирующие UPDATE-записи в журнале аудита.
    """
    insp = sqlalchemy_inspect(target)

    if not insp.has_identity:
        return None

    committed = insp.committed_state
    if not committed:
        return None

    old_values = {}
    for column in mapper.columns:
        if column.name not in committed:
            continue
        if column.name in SERVICE_COLUMNS:
            continue
        old_value = committed[column.name]

        if isinstance(old_value, datetime):
            old_value = old_value.isoformat()

        old_values[column.name] = old_value

    return old_values if old_values else None


class _SkipAudit(Exception):
    """Внутренний сигнал: родительская сущность уже удалена, писать нечего."""


ProjectId = int | None | Callable[[Any, Any], int | None]


def _project_id_via_task(connection, target) -> int | None:
    """project_id задачи для сущностей, ссылающихся только на task_id."""

    task_id = getattr(target, "task_id", None)
    if task_id is None:
        return None
    return connection.execute(select(Task.project_id).where(Task.id == task_id)).scalar_one_or_none()


def _project_id_via_specification(connection, target) -> int | None:
    """project_id для комментария к ТЗ: спецификация → проект."""

    specification_id = getattr(target, "specification_id", None)
    if specification_id is None:
        return None
    return connection.execute(
        select(ProjectSpecification.project_id).where(ProjectSpecification.id == specification_id)
    ).scalar_one_or_none()


def _resolve_project_id(connection, target, project_id: ProjectId) -> int | None:
    if project_id is None:
        return None
    if callable(project_id):
        resolved = project_id(connection, target)
        if resolved is None:
            # Запись относится к уже удалённому родителю (каскадное удаление
            # колонки/проекта). В ленте проекта ей не место, иначе она окажется
            # в ленте пользователя без привязки к проекту.
            raise _SkipAudit
        return resolved
    return project_id


def _insert_log(
    connection,
    *,
    entity_type: str,
    entity_id: int,
    action: str,
    project_id: int | None,
    old_values: dict | None,
    new_values: dict | None,
) -> None:
    """Записать одну строку журнала аудита на соединении текущей транзакции."""

    context_data = get_audit_context()
    connection.execute(
        insert(AuditLog).values(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_values=_safe_dumps(old_values) if old_values else None,
            new_values=_safe_dumps(new_values) if new_values else None,
            performed_by=context_data.user_id if context_data else None,
            ip_address=context_data.ip_address if context_data else None,
            user_agent=context_data.user_agent if context_data else None,
            performed_at=datetime.now(UTC),
            project_id=project_id,
        )
    )


def _audit_insert(mapper, connection, target, entity_type: str, project_id: ProjectId = None) -> None:
    """Логирование INSERT для сущности."""

    try:
        _insert_log(
            connection,
            entity_type=entity_type,
            entity_id=target.id,
            action="INSERT",
            project_id=_resolve_project_id(connection, target, project_id),
            old_values=None,
            new_values=_model_to_dict(target),
        )
    except _SkipAudit:
        logger.debug(f"Audit skipped: INSERT {entity_type} (id={target.id}) — parent already removed")
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)


def _audit_update(mapper, connection, target, entity_type: str, project_id: ProjectId = None) -> None:
    """Логирование UPDATE для сущности (только если что-то значимое изменилось)."""

    try:
        old_values = _get_old_values(mapper, target)
        if old_values is None:
            return
        _insert_log(
            connection,
            entity_type=entity_type,
            entity_id=target.id,
            action="UPDATE",
            project_id=_resolve_project_id(connection, target, project_id),
            old_values=old_values,
            new_values=_model_to_dict(target),
        )
    except _SkipAudit:
        logger.debug(f"Audit skipped: UPDATE {entity_type} (id={target.id}) — parent already removed")
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)


def _audit_delete(mapper, connection, target, entity_type: str, project_id: ProjectId = None) -> None:
    """Логирование DELETE для сущности."""

    try:
        _insert_log(
            connection,
            entity_type=entity_type,
            entity_id=target.id,
            action="DELETE",
            project_id=_resolve_project_id(connection, target, project_id),
            old_values=_model_to_dict(target),
            new_values=None,
        )
    except _SkipAudit:
        logger.debug(f"Audit skipped: DELETE {entity_type} (id={target.id}) — parent already removed")
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)


def _self_project_id(connection, target) -> int:
    """project_id из одноимённой колонки сущности.

    Сигнатура совпадает с `ProjectId`-резолверами: `_resolve_project_id` всегда
    вызывает их как `resolver(connection, target)`.
    """
    return target.project_id


# ─── Пользователь, резюме ───────────────────────────────────────────────────


@event.listens_for(User, "before_update")
def audit_user_update(mapper, connection, target: User) -> None:
    _audit_update(mapper, connection, target, "user")


@event.listens_for(User, "after_insert")
def audit_user_insert(mapper, connection, target: User) -> None:
    _audit_insert(mapper, connection, target, "user")


@event.listens_for(Resume, "before_update")
def audit_resume_update(mapper, connection, target: Resume) -> None:
    _audit_update(mapper, connection, target, "resume")


@event.listens_for(Resume, "after_insert")
def audit_resume_insert(mapper, connection, target: Resume) -> None:
    _audit_insert(mapper, connection, target, "resume")


@event.listens_for(Resume, "after_delete")
def audit_resume_delete(mapper, connection, target: Resume) -> None:
    _audit_delete(mapper, connection, target, "resume")


# ─── Проект и отклики ───────────────────────────────────────────────────────


@event.listens_for(Project, "after_insert")
def audit_project_insert(mapper, connection, target: Project) -> None:
    _audit_insert(mapper, connection, target, "project", _self_project_id)


@event.listens_for(Project, "before_update")
def audit_project_update(mapper, connection, target: Project) -> None:
    _audit_update(mapper, connection, target, "project", _self_project_id)


@event.listens_for(Project, "after_delete")
def audit_project_delete(mapper, connection, target: Project) -> None:
    _audit_delete(mapper, connection, target, "project", _self_project_id)


@event.listens_for(Response, "after_insert")
def audit_response_insert(mapper, connection, target: Response) -> None:
    _audit_insert(mapper, connection, target, "response", _self_project_id)


@event.listens_for(Response, "before_update")
def audit_response_update(mapper, connection, target: Response) -> None:
    _audit_update(mapper, connection, target, "response", _self_project_id)


@event.listens_for(Response, "after_delete")
def audit_response_delete(mapper, connection, target: Response) -> None:
    _audit_delete(mapper, connection, target, "response", _self_project_id)


@event.listens_for(ProjectParticipation, "after_insert")
def audit_project_participation_insert(mapper, connection, target: ProjectParticipation) -> None:
    _audit_insert(mapper, connection, target, "project_participation", _self_project_id)


@event.listens_for(ProjectParticipation, "after_delete")
def audit_project_participation_delete(mapper, connection, target: ProjectParticipation) -> None:
    _audit_delete(mapper, connection, target, "project_participation", _self_project_id)


# ─── Этапы проекта ──────────────────────────────────────────────────────────


@event.listens_for(StageTransition, "after_insert")
def audit_stage_transition_insert(mapper, connection, target: StageTransition) -> None:
    _audit_insert(mapper, connection, target, "stage_transition", _self_project_id)


# ─── Техническое задание ───────────────────────────────────────────────────


@event.listens_for(ProjectSpecification, "after_insert")
def audit_specification_insert(mapper, connection, target: ProjectSpecification) -> None:
    _audit_insert(mapper, connection, target, "specification", _self_project_id)


@event.listens_for(ProjectSpecification, "before_update")
def audit_specification_update(mapper, connection, target: ProjectSpecification) -> None:
    _audit_update(mapper, connection, target, "specification", _self_project_id)


@event.listens_for(SpecificationComment, "after_insert")
def audit_specification_comment_insert(mapper, connection, target: SpecificationComment) -> None:
    _audit_insert(mapper, connection, target, "specification_comment", _project_id_via_specification)


@event.listens_for(SpecificationComment, "after_delete")
def audit_specification_comment_delete(mapper, connection, target: SpecificationComment) -> None:
    _audit_delete(mapper, connection, target, "specification_comment", _project_id_via_specification)


# ─── Канбан-доска ───────────────────────────────────────────────────────────


@event.listens_for(Column, "after_insert")
def audit_column_insert(mapper, connection, target: Column) -> None:
    _audit_insert(mapper, connection, target, "column", _self_project_id)


@event.listens_for(Column, "before_update")
def audit_column_update(mapper, connection, target: Column) -> None:
    _audit_update(mapper, connection, target, "column", _self_project_id)


@event.listens_for(Column, "after_delete")
def audit_column_delete(mapper, connection, target: Column) -> None:
    _audit_delete(mapper, connection, target, "column", _self_project_id)


@event.listens_for(Task, "after_insert")
def audit_task_insert(mapper, connection, target: Task) -> None:
    _audit_insert(mapper, connection, target, "task", _self_project_id)


@event.listens_for(Task, "before_update")
def audit_task_update(mapper, connection, target: Task) -> None:
    _audit_update(mapper, connection, target, "task", _self_project_id)


@event.listens_for(Task, "after_delete")
def audit_task_delete(mapper, connection, target: Task) -> None:
    _audit_delete(mapper, connection, target, "task", _self_project_id)


@event.listens_for(Subtask, "after_insert")
def audit_subtask_insert(mapper, connection, target: Subtask) -> None:
    _audit_insert(mapper, connection, target, "subtask", _project_id_via_task)


@event.listens_for(Subtask, "before_update")
def audit_subtask_update(mapper, connection, target: Subtask) -> None:
    _audit_update(mapper, connection, target, "subtask", _project_id_via_task)


@event.listens_for(Subtask, "after_delete")
def audit_subtask_delete(mapper, connection, target: Subtask) -> None:
    _audit_delete(mapper, connection, target, "subtask", _project_id_via_task)


@event.listens_for(TaskAssignee, "after_insert")
def audit_task_assignee_insert(mapper, connection, target: TaskAssignee) -> None:
    _audit_insert(mapper, connection, target, "task_assignee", _project_id_via_task)


@event.listens_for(TaskAssignee, "after_delete")
def audit_task_assignee_delete(mapper, connection, target: TaskAssignee) -> None:
    _audit_delete(mapper, connection, target, "task_assignee", _project_id_via_task)


def setup_audit_listeners() -> None:
    """
    Инициализирует все event listener'ы.
    Листенеры регистрируются декораторами @event.listens_for при импорте модуля.
    """
    logger.debug("Audit event listeners are enabled")
