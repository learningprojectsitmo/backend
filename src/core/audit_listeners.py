from __future__ import annotations

from datetime import UTC, datetime
from json import dumps

from sqlalchemy import event, insert
from sqlalchemy.inspection import inspect as sqlalchemy_inspect

from src.core.audit_context import get_audit_context
from src.core.logging_config import get_logger
from src.model.models import AuditLog, Project, Resume, User

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


def _get_old_values(mapper, target) -> dict | None:
    """Получить cтарые значения для before_update listener'а"""
    insp = sqlalchemy_inspect(target)

    if not insp.has_identity:
        return None

    committed = insp.committed_state
    if not committed:
        return None

    old_values = {}
    for column in mapper.columns:
        old_value = committed.get(column.name)

        if isinstance(old_value, datetime):
            old_value = old_value.isoformat()

        if old_value is not None:
            old_values[column.name] = old_value

    return old_values if old_values else None


@event.listens_for(User, "before_update")
def audit_user_update(mapper, connection, target: User) -> None:
    """Логирование UPDATE user"""
    context_data = get_audit_context()

    try:
        old_values = _get_old_values(mapper, target)
        new_values = _model_to_dict(target)
        stmt = insert(AuditLog).values(
            entity_type="user",
            entity_id=target.id,
            action="UPDATE",
            old_values=dumps(old_values) if old_values else None,
            new_values=dumps(new_values),
            performed_by=context_data.user_id if context_data else None,
            ip_address=context_data.ip_address if context_data else None,
            user_agent=context_data.user_agent if context_data else None,
            performed_at=datetime.now(UTC),
        )
        connection.execute(stmt)

        logger.debug(
            f"Audit logged: UPDATE user (id={target.id}) "
            f"by user_id={context_data.user_id if context_data else 'system'}"
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)


@event.listens_for(User, "after_insert")
def audit_user_insert(mapper, connection, target: User) -> None:
    """Логирование INSERT user"""
    context_data = get_audit_context()

    try:
        new_values = _model_to_dict(target)
        stmt = insert(AuditLog).values(
            entity_type="user",
            entity_id=target.id,
            action="INSERT",
            old_values=None,
            new_values=dumps(new_values),
            performed_by=context_data.user_id,
            ip_address=context_data.ip_address,
            user_agent=context_data.user_agent,
            performed_at=datetime.now(UTC),
        )
        connection.execute(stmt)

        logger.debug(
            f"Audit logged: INSERT user (id={target.id}) "
            f"by user_id={context_data.user_id if context_data else 'system'}"
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)


@event.listens_for(Project, "before_update")
def audit_project_update(mapper, connection, target: Project) -> None:
    """Логирование UPDATE project"""
    context_data = get_audit_context()

    try:
        old_values = _get_old_values(mapper, target)
        new_values = _model_to_dict(target)
        stmt = insert(AuditLog).values(
            entity_type="project",
            entity_id=target.id,
            action="UPDATE",
            old_values=dumps(old_values) if old_values else None,
            new_values=dumps(new_values),
            performed_by=context_data.user_id if context_data else None,
            ip_address=context_data.ip_address if context_data else None,
            user_agent=context_data.user_agent if context_data else None,
            performed_at=datetime.now(UTC),
        )
        connection.execute(stmt)

        logger.debug(
            f"Audit logged: UPDATE project (id={target.id}) "
            f"by user_id={context_data.user_id if context_data else 'system'}"
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)


@event.listens_for(Project, "after_insert")
def audit_project_insert(mapper, connection, target: Project) -> None:
    """Логирование INSERT project"""
    context_data = get_audit_context()
    try:
        new_values = _model_to_dict(target)
        stmt = insert(AuditLog).values(
            entity_type="project",
            entity_id=target.id,
            action="INSERT",
            old_values=None,
            new_values=dumps(new_values),
            performed_by=context_data.user_id if context_data else None,
            ip_address=context_data.ip_address if context_data else None,
            user_agent=context_data.user_agent if context_data else None,
            performed_at=datetime.now(UTC),
        )
        connection.execute(stmt)

        logger.debug(
            f"Audit logged: INSERT project (id={target.id}) "
            f"by user_id={context_data.user_id if context_data else 'system'}"
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)


@event.listens_for(Resume, "before_update")
def audit_resume_update(mapper, connection, target: Resume) -> None:
    """Логирование UPDATE resume"""
    context_data = get_audit_context()

    try:
        old_values = _get_old_values(mapper, target)
        new_values = _model_to_dict(target)
        stmt = insert(AuditLog).values(
            entity_type="resume",
            entity_id=target.id,
            action="UPDATE",
            old_values=dumps(old_values) if old_values else None,
            new_values=dumps(new_values),
            performed_by=context_data.user_id if context_data else None,
            ip_address=context_data.ip_address if context_data else None,
            user_agent=context_data.user_agent if context_data else None,
            performed_at=datetime.now(UTC),
        )
        connection.execute(stmt)

        logger.debug(
            f"Audit logged: UPDATE resume (id={target.id}) "
            f"by user_id={context_data.user_id if context_data else 'system'}"
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)


@event.listens_for(Resume, "after_insert")
def audit_resume_insert(mapper, connection, target: Resume) -> None:
    """Логирование INSERT resume"""
    context_data = get_audit_context()

    try:
        new_values = _model_to_dict(target)
        stmt = insert(AuditLog).values(
            entity_type="resume",
            entity_id=target.id,
            action="INSERT",
            old_values=None,
            new_values=dumps(new_values),
            performed_by=context_data.user_id if context_data else None,
            ip_address=context_data.ip_address if context_data else None,
            user_agent=context_data.user_agent if context_data else None,
            performed_at=datetime.now(UTC),
        )
        connection.execute(stmt)

        logger.debug(
            f"Audit logged: INSERT resume (id={target.id}) "
            f"by user_id={context_data.user_id if context_data else 'system'}"
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)


def setup_audit_listeners() -> None:
    """
    Инициализирует все event listener'ы.
    """
