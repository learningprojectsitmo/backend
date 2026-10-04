from __future__ import annotations

from src.model.push import PushPlatform
from src.repository.push_repository import PushOutboxRepository
from src.schema.push import PushSubscriptionRequest, PushSubscriptionResponse, PushUnregisterResponse


class PushSubscriptionService:
    """Регистрация и снятие устройств.

    Отдельно от NotificationService: здесь нет уведомлений, только учёт
    устройств, из которых потом рассылается push.
    """

    def __init__(self, push_repository: PushOutboxRepository) -> None:
        self._push = push_repository

    async def register(
        self,
        user_id: int,
        request: PushSubscriptionRequest,
    ) -> PushSubscriptionResponse:
        """Запомнить устройство пользователя.

        Токен уникален глобально, поэтому повторная регистрация того же
        устройства обновляет существующую строку, а залогиненный на чужом
        телефоне переносит токен себе. Именно это и убирает главный источник
        «уведомления просто перестали приходить» — FCM после переустановки
        приложения выдаёт новый токен, а реактивировать его, не записав заново,
        нечем.
        """
        row = await self._push.upsert_subscription(
            user_id=user_id,
            token=request.token,
            platform=PushPlatform(request.platform),
            device_id=request.device_id,
            app_version=request.app_version,
        )
        return PushSubscriptionResponse.model_validate(row)

    async def unregister(self, user_id: int, token: str) -> PushUnregisterResponse:
        """Снять одно устройство."""
        # Проверка владельца внутри upsert-логики не годится: токен глобально
        # уникален, и если бы мы искали строку только по (user_id, token),
        # чужой токен не нашёлся бы, а молча вернул бы 0.
        owned = await self._push.owns_token(user_id, token)
        if not owned:
            return PushUnregisterResponse(removed=0)
        await self._push.deactivate_token(token)
        return PushUnregisterResponse(removed=1)

    async def unregister_all(self, user_id: int) -> PushUnregisterResponse:
        """Снять все устройства — например, при выходе из аккаунта."""
        return PushUnregisterResponse(removed=await self._push.delete_tokens_of_user(user_id))
