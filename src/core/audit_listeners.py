from sqlalchemy import event, insert
from sqlalchemy.inspection import inspect as sqlalchemy_inspect

from datetime import datetime, timezone
from json import dumps

from src.model.models import User, Project, Resume, AuditLog
from src.core.audit_context import get_audit_context
from src.core.logging_config import get_logger

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
    
    old_values = {}
    
    for column in mapper.columns:
        attr_state = insp.attrs[column.name]
        old_value = attr_state.loaded_value
        
        if isinstance(old_value, datetime):
            old_value = old_value.isoformat()
        
        if old_value is not None:
            old_values[column.name] = old_value
    
    return old_values if old_values else None


@event.listens_for(User, "after_update")
def audit_user_update(mapper, connection, target: User) -> None:
    """Логирование UPDATE user"""
    context_data = get_audit_context()
    
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
            performed_at=datetime.now(timezone.utc),
        )
        connection.execute(stmt)

        logger.debug(
            f"Audit logged: INSERT user (id={target.id}) "
            f"by user_id={context_data.user_id if context_data else 'system'}"
        )
    except Exception as e:
        logger.error(f"Failed to log audit: {e}", exc_info=True)

@event.listens_for(Project, "after_update")
def audit_project_update(mapper, connection, target: Project) -> None:
    """Логирование UPDATE project"""
    context_data = get_audit_context()
    # TODO: add db query here in order to save user's actions in database (audit_logs table)

@event.listens_for(Project, "after_insert")
def audit_project_insert(mapper, connection, target: Project) -> None:
    """Логирование INSERT project"""
    # TODO: add db query here in order to save user's actions in database (audit_logs table)

@event.listens_for(Resume, "after_update")
def audit_project_insert(mapper, connection, target: Resume) -> None:
    """Логирование UPDATE resume"""
    # TODO: add db query here in order to save user's actions in database (audit_logs table)

@event.listens_for(Resume, "after_insert")
def audit_project_insert(mapper, connection, target: Resume) -> None:
    """Логирование INSERT resume"""
    # TODO: add db query here in order to save user's actions in database (audit_logs table)


def setup_audit_listeners() -> None:
    """
    Инициализирует все event listener'ы.
    """
