from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.container import get_audit_service
from src.core.dependencies import get_current_user
from src.model.models import User
from src.schema.audit import AuditLogResponse
from src.services.audit_service import AuditService

audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("/{user_id}", response_model=list[AuditLogResponse])
async def get_user_audit_logs(
    user_id: int,
    audit_service: AuditService = Depends(get_audit_service),
    current_user: User = Depends(get_current_user),
) -> list[AuditLogResponse]:
    """Получить audit логи пользователя"""

    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )

    return await audit_service.get_user_audit_logs(user_id)
