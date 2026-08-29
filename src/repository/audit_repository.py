from __future__ import annotations

from sqlalchemy import Sequence, desc, select

from src.core.logging_config import get_logger
from src.core.uow import IUnitOfWork
from src.model.audit import AuditLog
from src.model.project import Project
from src.model.resume import Resume


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

    async def get_project_names(self, project_ids: set[int]) -> dict[int, str]:
        """Получить названия проектов по ID (для обогащения ленты)"""

        if not project_ids:
            return {}
        try:
            result = await self.uow.session.execute(
                select(Project.id, Project.name).where(Project.id.in_(project_ids))
            )
            return {row[0]: row[1] for row in result.all()}
        except Exception:
            self._logger.exception("Error getting project names for audit enrichment")
            raise

    async def get_resume_names(self, resume_ids: set[int]) -> dict[int, str]:
        """Получить заголовки резюме по ID (для обогащения ленты)"""

        if not resume_ids:
            return {}
        try:
            result = await self.uow.session.execute(select(Resume.id, Resume.header).where(Resume.id.in_(resume_ids)))
            return {row[0]: row[1] for row in result.all()}
        except Exception:
            self._logger.exception("Error getting resume names for audit enrichment")
            raise
