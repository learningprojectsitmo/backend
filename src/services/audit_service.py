from __future__ import annotations

import json

from src.repository.audit_repository import AuditRepository
from src.schema.audit import AuditLogResponse


class AuditService:
    """Сервис для работы с audit логами"""

    def __init__(self, audit_repository: AuditRepository):
        self._audit_repository = audit_repository

    async def get_user_audit_logs(self, user_id: int) -> list[AuditLogResponse]:
        """Получить audit логи пользователя"""

        logs = await self._audit_repository.get_logs_by_user_id(user_id)
        result = []
        for log in logs:
            log_dict = {
                "id": log.id,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "action": log.action,
                "old_values": json.loads(log.old_values) if isinstance(log.old_values, str) else log.old_values,
                "new_values": json.loads(log.new_values) if isinstance(log.new_values, str) else log.new_values,
                "performed_by": log.performed_by,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "performed_at": log.performed_at,
            }
            result.append(AuditLogResponse(**log_dict))

        return result
