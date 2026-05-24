from __future__ import annotations

from sqlalchemy import Sequence, desc, select

from src.core.logging_config import get_logger
from src.core.uow import IUnitOfWork
from src.model.audit import AuditLog


class AuditRepository:
    """Репозиторий для работы с audit логами"""

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow
        self._logger = get_logger(self.__class__.__name__)

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
