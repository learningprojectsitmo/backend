from __future__ import annotations

from math import ceil

from loguru import logger

from src.core.exceptions import NotFoundError
from src.model.notification import Notification, NotificationType
from src.repository.notification_repository import NotificationRepository
from src.repository.push_repository import PushOutboxRepository
from src.schema.notification import NotificationListResponse, NotificationResponse
from src.services.push_payload import PushPayload, build_push


def _to_payload(payload: PushPayload) -> dict:
    """Подготовить сообщение к сохранению в JSON-колонку.

    Токена в нём нет по построению (см. PushPayload), поэтому строка очереди
    переживает смену устройства и годится для повторной отправки.
    """
    return {
        "title": payload.title,
        "body": payload.body,
        "route": payload.route,
        "channel_id": payload.channel_id,
        "high_priority": payload.high_priority,
        "collapse_key": payload.collapse_key,
        "data": payload.data,
    }


class NotificationService:
    def __init__(
        self,
        notification_repository: NotificationRepository,
        push_repository: PushOutboxRepository | None = None,
    ) -> None:
        self._repository = notification_repository
        # Опционально: в тестах на уведомления push не нужен, а требовать его
        # везде заставило бы поднимать лишнюю зависимость.
        self._push = push_repository

    async def get_my_notifications(self, user_id: int, page: int = 1, limit: int = 20) -> NotificationListResponse:
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
        *,
        actor_name: str,
        project_id: int,
        project_name: str,
        vacancy_title: str | None = None,
        actor_id: int | None = None,
        invitation_id: int | None = None,
        response_id: int | None = None,
        stage_name: str | None = None,
        task_title: str | None = None,
        column_name: str | None = None,
        subtask_title: str | None = None,
    ) -> Notification:
        data = {
            "actor_id": actor_id,
            "actor_name": actor_name,
            "project_id": project_id,
            "project_name": project_name,
            "vacancy_title": vacancy_title,
            "invitation_id": invitation_id,
            "response_id": response_id,
            "stage_name": stage_name,
            "task_title": task_title,
            "column_name": column_name,
            "subtask_title": subtask_title,
        }
        notification = await self._repository.create_notification(user_id, type, data)
        await self._enqueue_push(user_id=user_id, notification=notification, type=type, data=data)
        return notification

    async def _enqueue_push(
        self,
        *,
        user_id: int,
        notification: Notification,
        type: NotificationType,
        data: dict,
    ) -> None:
        """Класть push в очередь вместе с уведомлением.

        Здесь нет сетевых вызовов намеренно: строка очереди пишется в той же
        транзакции, что и само уведомление, поэтому откат бизнес-операции
        откатывает и push. Отправкой занимается отдельный воркер.

        Ошибка не должна ломать бизнес-операцию: пользователь не сможет
        откликнуться на проект из-за того, что у него нет FCM-токена.
        """
        if self._push is None:
            return
        try:
            payload = build_push(
                type=type,
                data=data,
                user_id=user_id,
                notification_id=notification.id,
            )
            await self._push.enqueue(
                user_id=user_id,
                notification_id=notification.id,
                type=type,
                payload=_to_payload(payload),
            )
        except Exception as exc:
            logger.warning(f"Не удалось поставить push в очередь для user={user_id}: {exc}")

    async def mark_read(self, notification_id: int, user_id: int) -> NotificationResponse:
        notification = await self._repository.mark_read(notification_id, user_id)
        if not notification:
            raise NotFoundError("Notification not found or not yours")
        return NotificationResponse.model_validate(notification)

    async def mark_all_read(self, user_id: int) -> int:
        count = await self._repository.mark_all_read(user_id)
        return count
