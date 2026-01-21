from contextvars import ContextVar
from dataclasses import dataclass

@dataclass
class AuditContext:
    """Контекст для аудита операций"""
    user_id: int | None = None       
    ip_address: str | None = None    
    user_agent: str | None = None    

audit_context_var: ContextVar[AuditContext | None] = ContextVar(
    'audit_context', 
    default=None
)

def set_audit_context(user_id: int | None, ip_address: str | None, user_agent: str | None) -> None:
    """Установить контекст аудита"""
    context = AuditContext(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent
    )
    audit_context_var.set(context)

def get_audit_context() -> AuditContext | None:
    """Получить текущий контекст аудита"""
    return audit_context_var.get()

def clear_audit_context() -> None:
    """Очистить контекст аудита"""
    audit_context_var.set(None)