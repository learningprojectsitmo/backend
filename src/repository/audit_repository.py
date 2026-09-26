from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.core.logging_config import get_logger
from src.core.uow import IUnitOfWork
from src.model.audit import AuditLog
from src.model.kanban_models import Column, Task
from src.model.project import Project, ProjectStage
from src.model.resume import Resume
from src.model.user import User


class AuditRepository:
    """Репозиторий для работы с audit логами"""

    def __init__(self, uow: IUnitOfWork) -> None:
        self.uow = uow
        self._logger = get_logger(self.__class__.__name__)

    async def get_logs_by_user_id(
        self, user_id: int, since: datetime | None = None, *, day: date | None = None
    ) -> Sequence[AuditLog]:
        """Получить логи пользователя начиная с `since`, отсортированные по дате.

        `day` сужает выборку до одного дня — по нему лента показывает действия
        выбранного в графике дня.
        """

        try:
            query = select(AuditLog).where(AuditLog.performed_by == user_id)
            if since is not None:
                query = query.where(AuditLog.performed_at >= since)
            if day is not None:
                query = query.where(_day_filter(day))
            result = await self.uow.session.execute(query.order_by(desc(AuditLog.performed_at)))
            logs = result.scalars().all()
        except Exception:
            self._logger.exception(f"Error getting audit logs for user {user_id}")
            raise
        else:
            return logs

    async def get_logs_by_project_id(
        self, project_id: int, skip: int = 0, limit: int = 50, *, day: date | None = None
    ) -> tuple[Sequence[AuditLog], int]:
        """Получить страницу логов проекта и их общее количество.

        `day` сужает выборку до одного дня — по нему лента показывает действия
        выбранного в графике дня.
        """

        try:
            total = await self.count_by_project_id(project_id, day=day)
            query = select(AuditLog).where(AuditLog.project_id == project_id)
            if day is not None:
                query = query.where(_day_filter(day))
            result = await self.uow.session.execute(
                query.order_by(desc(AuditLog.performed_at)).offset(skip).limit(limit)
            )
            logs = result.scalars().all()
        except Exception:
            self._logger.exception(f"Error getting audit logs for project {project_id}")
            raise
        else:
            return logs, total

    async def count_by_project_id(self, project_id: int, *, day: date | None = None) -> int:
        """Посчитать количество audit записей проекта"""

        try:
            query = select(func.count()).select_from(AuditLog).where(AuditLog.project_id == project_id)
            if day is not None:
                query = query.where(_day_filter(day))
            result = await self.uow.session.execute(query)
            count = result.scalar_one()
        except Exception:
            self._logger.exception(f"Error counting audit logs for project {project_id}")
            raise
        else:
            return count

    async def get_performed_at_by_project_id(
        self, project_id: int, since: datetime | None = None
    ) -> Sequence[datetime]:
        """Только временные метки логов проекта — для агрегации по дням"""

        try:
            query = select(AuditLog.performed_at).where(AuditLog.project_id == project_id)
            if since is not None:
                query = query.where(AuditLog.performed_at >= since)
            result = await self.uow.session.execute(query)
            stamps = result.scalars().all()
        except Exception:
            self._logger.exception(f"Error getting activity timestamps for project {project_id}")
            raise
        else:
            return stamps

    async def create_log(
        self,
        *,
        entity_type: str,
        entity_id: int,
        action: str,
        project_id: int | None = None,
        old_values: dict | None = None,
        new_values: dict | None = None,
        performed_by: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Записать действие вручную (для изменений, которые ORM-слушатели не видят)"""

        self.uow.session.add(
            AuditLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                old_values=old_values,
                new_values=new_values,
                project_id=project_id,
                performed_by=performed_by,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
        await self.uow.session.flush()

    async def get_user_registered_at(self, user_id: int) -> date | None:
        """Дата регистрации пользователя — начало окна активности"""

        try:
            result = await self.uow.session.execute(select(User.created_at).where(User.id == user_id))
            created_at = result.scalar_one_or_none()
        except Exception:
            self._logger.exception(f"Error getting registration date for user {user_id}")
            raise
        else:
            return created_at.date() if created_at else None

    async def get_project_created_at(self, project_id: int) -> date | None:
        """Дата создания проекта — начало окна активности проекта"""

        try:
            result = await self.uow.session.execute(select(Project.created_at).where(Project.id == project_id))
            created_at = result.scalar_one_or_none()
        except Exception:
            self._logger.exception(f"Error getting creation date for project {project_id}")
            raise
        else:
            return created_at.date() if created_at else None

    async def get_first_activity_at_by_project_id(self, project_id: int) -> date | None:
        """Дата первого действия в проекте — начало окна активности проекта.

        Берётся из самих логов, а не из ``Project.created_at``: проект можно
        создать заранее, а работа начаться заметно позже, и график в таком
        случае не должен начинаться с пустых недель.
        """

        try:
            result = await self.uow.session.execute(
                select(func.min(AuditLog.performed_at)).where(AuditLog.project_id == project_id)
            )
            first_at = result.scalar_one_or_none()
        except Exception:
            self._logger.exception(f"Error getting first activity date for project {project_id}")
            raise
        else:
            return first_at.date() if first_at else None

    async def get_actor_names(self, user_ids: set[int]) -> dict[int, str]:
        """Получить отображаемые имена пользователей по ID (для ленты активности)"""

        return await self._names_by_id(user_ids, User, (User.last_name, User.first_name, User.middle_name))

    async def get_task_titles(self, task_ids: set[int]) -> dict[int, str]:
        """Получить названия задач по ID (для ленты активности)"""

        if not task_ids:
            return {}
        try:
            result = await self.uow.session.execute(select(Task.id, Task.title).where(Task.id.in_(task_ids)))
            return {row[0]: row[1] for row in result.all()}
        except Exception:
            self._logger.exception("Error getting task titles for audit enrichment")
            raise

    async def get_column_names(self, column_ids: set[int]) -> dict[int, str]:
        """Получить названия колонок по ID (для ленты активности)"""

        if not column_ids:
            return {}
        try:
            result = await self.uow.session.execute(select(Column.id, Column.name).where(Column.id.in_(column_ids)))
            return {row[0]: row[1] for row in result.all()}
        except Exception:
            self._logger.exception("Error getting column names for audit enrichment")
            raise

    async def get_stage_names(self, stage_ids: set[int]) -> dict[int, str]:
        """Получить названия этапов по ID (для ленты активности)"""

        if not stage_ids:
            return {}
        try:
            result = await self.uow.session.execute(
                select(ProjectStage.id, ProjectStage.name).where(ProjectStage.id.in_(stage_ids))
            )
            return {row[0]: row[1] for row in result.all()}
        except Exception:
            self._logger.exception("Error getting stage names for audit enrichment")
            raise

    async def get_project_names(self, project_ids: set[int]) -> dict[int, str]:
        """Получить названия проектов по ID (для обогащения ленты)"""

        if not project_ids:
            return {}
        try:
            result = await self.uow.session.execute(select(Project.id, Project.name).where(Project.id.in_(project_ids)))
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

    async def _names_by_id(self, ids: set[int], model, columns: tuple) -> dict[int, str]:
        """Собрать отображаемые имена сущности по ID, пропуская удалённых"""

        if not ids:
            return {}
        try:
            result = await self.uow.session.execute(select(model.id, *columns).where(model.id.in_(ids)))
            return {row[0]: " ".join(part for part in row[1:] if part).strip() for row in result.all()}
        except Exception:
            self._logger.exception(f"Error getting names for {model.__name__}")
            raise

    async def get_all_logs(self, skip: int = 0, limit: int = 100) -> Sequence[AuditLog]:
        """Получить audit логи всех пользователей с пагинацией (для админ-панели)"""

        try:
            result = await self.uow.session.execute(
                select(AuditLog)
                .options(selectinload(AuditLog.user))
                .order_by(desc(AuditLog.performed_at))
                .offset(skip)
                .limit(limit)
            )
            logs = result.scalars().all()
        except Exception:
            self._logger.exception("Error getting all audit logs for admin")
            raise
        else:
            return logs

    async def count_all(self) -> int:
        """Подсчитать количество всех audit записей"""

        try:
            result = await self.uow.session.execute(select(func.count()).select_from(AuditLog))
            count = result.scalar_one()
        except Exception:
            self._logger.exception("Error counting audit logs")
            raise
        else:
            return count


def _day_filter(day: date) -> ColumnElement[bool]:
    """Критерий «этот UTC-день»: [полночь, полночь следующего дня).

    Агрегация в `summary` идёт по `performed_at.date()` на tz-aware колонке,
    поэтому границы обязаны быть в UTC — иначе день «по местному» разъезжается
    с тем, что бэкенд уже отдал в графике.
    """

    start = datetime.combine(day, time.min, tzinfo=UTC)
    return and_(AuditLog.performed_at >= start, AuditLog.performed_at < start + timedelta(days=1))
