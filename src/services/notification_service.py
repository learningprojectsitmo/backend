from __future__ import annotations

from math import ceil

from src.core.exceptions import NotFoundError, PermissionError
from src.model.notification import Notification, NotificationType
from src.repository.notification_repository import NotificationRepository
from src.schema.notification import NotificationListResponse, NotificationResponse


class NotificationService:
    def __init__(self, notification_repository: NotificationRepository) -> None:
        self._repository = notification_repository

    async def get_my_notifications(
        self, user_id: int, page: int = 1, limit: int = 20
    ) -> NotificationListResponse:
        items, total, unread_count = await self._repository.get_by_user_id(user_id, page, limit)
        total_pages = ceil(total / limit) if total > 0 else 0
        return NotificationListResponse(
            items=[NotificationResponse.model_validate(n) for n in items],
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
            unread_count=unread_count,
        )

    async def create_notification(
        self,
        user_id: int,
        type: NotificationType,
        actor_name: str,
        project_id: int,
        project_name: str,
        vacancy_title: str | None = None,
        actor_id: int | None = None,
        invitation_id: int | None = None,
        response_id: int | None = None,
    ) -> Notification:
        data = {
            "actor_id": actor_id,
            "actor_name": actor_name,
            "project_id": project_id,
            "project_name": project_name,
            "vacancy_title": vacancy_title,
            "invitation_id": invitation_id,
            "response_id": response_id,
        }
        return await self._repository.create_notification(user_id, type, data)

    async def mark_read(self, notification_id: int, user_id: int) -> NotificationResponse:
        notification = await self._repository.mark_read(notification_id, user_id)
        if not notification:
            raise NotFoundError("Notification not found or not yours")
        return NotificationResponse.model_validate(notification)

    async def mark_all_read(self, user_id: int) -> int:
        count = await self._repository.mark_all_read(user_id)
        return count
