from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.core.container import get_notification_service
from src.core.dependencies import get_current_user
from src.model.user import User
from src.schema.notification import NotificationListResponse, NotificationResponse
from src.services.notification_service import NotificationService

notification_router = APIRouter(prefix="/notifications", tags=["notification"])


@notification_router.get("/my", response_model=NotificationListResponse)
async def fetch_my_notifications(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(20, ge=1, le=50, description="Количество на странице"),
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationListResponse:
    """Получить уведомления текущего пользователя"""
    return await notification_service.get_my_notifications(current_user.id, page, limit)


@notification_router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: int,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    """Отметить уведомление как прочитанное"""
    return await notification_service.mark_read(notification_id, current_user.id)


@notification_router.post("/read-all")
async def mark_all_notifications_read(
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Отметить все уведомления как прочитанные"""
    count = await notification_service.mark_all_read(current_user.id)
    return {"message": f"{count} notifications marked as read", "count": count}
