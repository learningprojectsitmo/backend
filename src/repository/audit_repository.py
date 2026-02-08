from __future__ import annotations

from sqlalchemy import Sequence, desc, select

from core.uow import IUnitOfWork
from src.model.models import AuditLog


class AuditRepository:
    """Репозиторий для работы с audit логами"""

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow

        # в будущем можно будет добавить больше фильтров

    async def get_logs_by_user_id(self, user_id: int) -> Sequence[AuditLog]:
        """Получить все логи пользователя, отсортированные по дате"""

        try:
            result = await self.uow.session.execute(
                select(AuditLog).where(AuditLog.performed_by == user_id).order_by(desc(AuditLog.performed_at))
            )
            logs = result.scalars().all()
        except Exception:
            self._logger.exception(f"Error getting audit logs for user {user_id}")
            raise
        else:
            return logs
