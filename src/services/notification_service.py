from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.core.exceptions import NotFoundError, ValidationError
from src.model.models import Notification
from src.notifications.templates import list_notification_required_fields, list_notification_templates
from src.repository.notification_repository import NotificationRepository
from src.repository.project_participation_repository import ProjectParticipationRepository
from src.repository.project_repository import ProjectRepository


class NotificationService:
    """Сервис работы с уведомлениями"""

    def __init__(
        self,
        notification_repository: NotificationRepository,
        project_repository: ProjectRepository,
        project_participation_repository: ProjectParticipationRepository,
    ) -> None:
        """Инициализирует сервис с репозиториями"""
        self._notification_repository = notification_repository
        self._project_repository = project_repository
        self._project_participation_repository = project_participation_repository

    @staticmethod
    def _templates() -> dict[str, dict[str, Any]]:
        """Возвращает словарь шаблонов уведомлений"""
        return list_notification_templates()

    @classmethod
    def _render_template(cls, template_key: str, payload: dict[str, Any]) -> tuple[str, str]:
        """Рендерит заголовок и тело по ключу шаблона"""
        templates = cls._templates()
        template = templates.get(template_key)
        if not template:
            raise ValidationError(f"Unknown template key: {template_key}")

        required_fields = template.get("required", [])
        missing = [field for field in required_fields if field not in payload]
        if missing:
            raise ValidationError(f"Missing payload fields for template '{template_key}': {', '.join(missing)}")

        title = template["title"].format(**payload)
        body = template["body"].format(**payload)
        return title, body

    async def list_user_notifications(self, user_id: int, page: int, limit: int) -> tuple[list[Notification], int]:
        """Возвращает список уведомлений пользователя и общее число"""
        skip = (page - 1) * limit
        notifications = await self._notification_repository.get_by_user_id(user_id, skip=skip, limit=limit)
        total = await self._notification_repository.count_by_user_id(user_id)
        return notifications, total

    async def send_to_user(
        self,
        recipient_id: int,
        sender_id: int | None,
        template_key: str,
        payload: dict[str, Any],
        project_id: int | None = None,
    ) -> Notification:
        """Создаёт уведомление для одного пользователя"""
        title, body = self._render_template(template_key, payload)
        data = {
            "id": str(uuid4()),
            "recipient_id": recipient_id,
            "sender_id": sender_id,
            "project_id": project_id,
            "type": template_key,
            "status": "pending",
            "title": title,
            "body": body,
        }
        return await self._notification_repository.create(data)

    async def send_to_project_participants(
        self,
        project_id: int,
        sender_id: int | None,
        template_key: str,
        payload: dict[str, Any],
        include_author: bool = True,
    ) -> list[Notification]:
        """Создаёт уведомления участникам проекта"""
        project = await self._project_repository.get_by_id(project_id)
        if not project:
            raise NotFoundError("Project not found")

        participant_ids = await self._project_participation_repository.get_participant_ids_by_project_id(project_id)
        recipients = set(participant_ids)
        if include_author:
            recipients.add(project.author_id)

        if not recipients:
            return []

        title, body = self._render_template(template_key, payload)

        notifications_data = [
            {
                "id": str(uuid4()),
                "recipient_id": recipient_id,
                "sender_id": sender_id,
                "project_id": project_id,
                "type": template_key,
                "status": "pending",
                "title": title,
                "body": body,
            }
            for recipient_id in recipients
        ]
        return await self._notification_repository.create_many(notifications_data)

    async def mark_read(self, user_id: int, notification_id: str) -> Notification:
        """Помечает уведомление как прочитанное"""
        notification = await self._notification_repository.mark_read(user_id, notification_id)
        if not notification:
            raise NotFoundError("Notification not found")
        return notification

    async def mark_all_read(self, user_id: int) -> int:
        """Помечает все уведомления пользователя как прочитанные"""
        return await self._notification_repository.mark_all_read(user_id)

    @classmethod
    def list_templates(cls) -> dict[str, dict[str, Any]]:
        """Возвращает список обязательных полей шаблонов"""
        return list_notification_required_fields()
