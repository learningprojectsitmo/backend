from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.core.container import get_notification_service
from src.core.dependencies import get_current_user
from src.model.models import User
from src.schema.notification import (
    NotificationListResponse,
    NotificationResponse,
    NotificationSendToProjectRequest,
    NotificationSendToUserRequest,
)
from src.services.notification_service import NotificationService

notification_router = APIRouter(prefix="/notifications", tags=["notification"])


@notification_router.get("/me", response_model=NotificationListResponse)
async def fetch_my_notifications(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество уведомлений на странице"),
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationListResponse:
    """Возвращает список уведомлений текущего пользователя"""
    notifications, total = await notification_service.list_user_notifications(current_user.id, page, limit)
    total_pages = (total + limit - 1) // limit if total > 0 else 0
    items = [NotificationResponse.model_validate(notification) for notification in notifications]

    return NotificationListResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@notification_router.post("/send/user", response_model=NotificationResponse)
async def send_notification_to_user(
    request_data: NotificationSendToUserRequest,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    """Отправляет уведомление одному пользователю"""
    notification = await notification_service.send_to_user(
        recipient_id=request_data.user_id,
        sender_id=current_user.id,
        template_key=request_data.template_key.value,
        payload=request_data.payload,
        project_id=request_data.project_id,
    )
    return NotificationResponse.model_validate(notification)


@notification_router.post("/send/project", response_model=list[NotificationResponse])
async def send_notification_to_project(
    request_data: NotificationSendToProjectRequest,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> list[NotificationResponse]:
    """Отправляет уведомления участникам проекта"""
    notifications = await notification_service.send_to_project_participants(
        project_id=request_data.project_id,
        sender_id=current_user.id,
        template_key=request_data.template_key.value,
        payload=request_data.payload,
        include_author=request_data.include_author,
    )
    return [NotificationResponse.model_validate(notification) for notification in notifications]


@notification_router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    """Помечает уведомление как прочитанное"""
    notification = await notification_service.mark_read(current_user.id, notification_id)
    return NotificationResponse.model_validate(notification)


@notification_router.post("/read-all")
async def mark_all_notifications_read(
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Помечает все уведомления пользователя как прочитанные"""
    updated = await notification_service.mark_all_read(current_user.id)
    return {"updated": updated}


@notification_router.get("/templates")
async def get_notification_templates(
    notification_service: NotificationService = Depends(get_notification_service),
    _current_user: User = Depends(get_current_user),
) -> dict:
    """Возвращает список обязательных полей шаблонов"""
    return notification_service.list_templates()
