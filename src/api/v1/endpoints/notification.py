from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from src.core.container import get_notification_service, get_notification_settings_service
from src.core.dependencies import get_current_user
from src.model.models import User
from src.schema.notification import (
    NotificationListResponse,
    NotificationMarkAllReadRequest,
    NotificationReadUpdateRequest,
    NotificationResponse,
    NotificationSendToProjectRequest,
    NotificationSendToUserRequest,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
)
from src.notifications.templates import build_notification_examples
from src.services.notification_service import NotificationService
from src.services.notification_settings_service import NotificationSettingsService

notification_router = APIRouter(tags=["notification"])


@notification_router.get("/notifications", response_model=NotificationListResponse)
async def fetch_my_notifications(
    page: int = Query(1, ge=1, description="Номер страницы"),
    limit: int = Query(10, ge=1, le=100, description="Количество уведомлений на странице"),
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationListResponse:
    """Возвращает список уведомлений текущего пользователя с пагинацией"""
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


@notification_router.post(
    "/users/{user_id}/notifications",
    response_model=NotificationResponse,
    responses={
        400: {
            "description": "Invalid template or missing payload fields",
            "content": {"application/json": {"example": {"detail": "Missing payload fields"}}},
        },
        401: {"description": "Unauthorized"},
        422: {"description": "Validation error"},
    },
)
async def send_notification_to_user(
    user_id: int,
    request_data: NotificationSendToUserRequest = Body(
        ...,  # required
        examples=build_notification_examples(include_project_id=True, include_author=False),
    ),
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    """Отправляет уведомление одному пользователю"""
    notification = await notification_service.send_to_user(
        recipient_id=user_id,
        sender_id=current_user.id,
        template_key=request_data.template_key.value,
        payload=request_data.payload,
        project_id=request_data.project_id,
    )
    return NotificationResponse.model_validate(notification)


@notification_router.post(
    "/projects/{project_id}/notifications",
    response_model=list[NotificationResponse],
    responses={
        400: {
            "description": "Invalid template or missing payload fields",
            "content": {"application/json": {"example": {"detail": "Missing payload fields"}}},
        },
        401: {"description": "Unauthorized"},
        404: {"description": "Project not found"},
        422: {"description": "Validation error"},
    },
)
async def send_notification_to_project(
    project_id: int,
    request_data: NotificationSendToProjectRequest = Body(
        ...,  # required
        examples=build_notification_examples(include_project_id=False, include_author=True),
    ),
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> list[NotificationResponse]:
    """Отправляет уведомления участникам проекта"""
    notifications = await notification_service.send_to_project_participants(
        project_id=project_id,
        sender_id=current_user.id,
        template_key=request_data.template_key.value,
        payload=request_data.payload,
        include_author=request_data.include_author,
    )
    return [NotificationResponse.model_validate(notification) for notification in notifications]


@notification_router.patch("/notifications/{notification_id}", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: str,
    request_data: NotificationReadUpdateRequest,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationResponse:
    """Помечает уведомление как прочитанное"""
    if not request_data.is_read:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only is_read=true is supported",
        )
    notification = await notification_service.mark_read(current_user.id, notification_id)
    return NotificationResponse.model_validate(notification)


@notification_router.patch("/notifications")
async def mark_all_notifications_read(
    request_data: NotificationMarkAllReadRequest,
    notification_service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Помечает все уведомления пользователя как прочитанные"""
    if not request_data.mark_all_read:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only mark_all_read=true is supported",
        )
    updated = await notification_service.mark_all_read(current_user.id)
    return {"updated": updated}


@notification_router.get("/notifications/templates")
async def get_notification_templates(
    notification_service: NotificationService = Depends(get_notification_service),
    _current_user: User = Depends(get_current_user),
) -> dict:
    """Возвращает список обязательных полей шаблонов"""
    return notification_service.list_templates()


@notification_router.get("/notifications/settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    notification_settings_service: NotificationSettingsService = Depends(get_notification_settings_service),
    current_user: User = Depends(get_current_user),
) -> NotificationSettingsResponse:
    """Возвращает настройки уведомлений текущего пользователя"""
    settings = await notification_settings_service.get_settings(current_user.id)
    return NotificationSettingsResponse.model_validate(settings)


@notification_router.patch("/notifications/settings", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    request_data: NotificationSettingsUpdate,
    notification_settings_service: NotificationSettingsService = Depends(get_notification_settings_service),
    current_user: User = Depends(get_current_user),
) -> NotificationSettingsResponse:
    """Обновляет настройки уведомлений текущего пользователя"""
    settings = await notification_settings_service.update_settings(current_user.id, request_data)
    return NotificationSettingsResponse.model_validate(settings)
