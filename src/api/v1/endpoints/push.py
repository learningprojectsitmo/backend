from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from src.core.container import get_push_subscription_service
from src.core.dependencies import get_current_user
from src.model.user import User
from src.schema.push import PushSubscriptionRequest, PushSubscriptionResponse, PushUnregisterResponse
from src.services.push_subscription_service import PushSubscriptionService

push_router = APIRouter(prefix="/notifications/push", tags=["push"])


@push_router.post("/tokens", response_model=PushSubscriptionResponse)
async def register_push_token(
    payload: PushSubscriptionRequest,
    push_service: PushSubscriptionService = Depends(get_push_subscription_service),
    current_user: User = Depends(get_current_user),
) -> PushSubscriptionResponse:
    """Зарегистрировать устройство для получения push.

    Клиент вызывает это при каждом запуске приложения и при каждом
    `onTokenRefresh`. Идемпотентно: повторная отправка того же токена
    обновляет устройство и возвращает его в активные, поэтому клиенту не
    нужно хранить, регистрировал ли он токен раньше.
    """
    return await push_service.register(current_user.id, payload)


@push_router.delete("/tokens", response_model=PushUnregisterResponse)
async def unregister_all_push_tokens(
    push_service: PushSubscriptionService = Depends(get_push_subscription_service),
    current_user: User = Depends(get_current_user),
) -> PushUnregisterResponse:
    """Снять все свои устройства — вызывается при выходе из аккаунта.

    Без отдельного маршрута клиенту пришлось бы обходить все токены, которых
    у него нет: он знает только свой текущий.
    """
    return await push_service.unregister_all(current_user.id)


@push_router.delete("/tokens/{token}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def unregister_push_token(
    token: str,
    push_service: PushSubscriptionService = Depends(get_push_subscription_service),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Снять одно устройство.

    204 даже если токен не найден или уже погашен: клиент не может на это
    повлиять, и ошибка заставила бы его писать обработчик несуществующей
    ситуации.
    """
    await push_service.unregister(current_user.id, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
