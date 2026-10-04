"""Юнит-тесты регистрации и снятия устройств."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.model.push import PushPlatform
from src.schema.push import PushSubscriptionRequest
from src.services.push_subscription_service import PushSubscriptionService

#: Реальные FCM-токены длинные; схема режет всё короче 8 символов.
TOKEN = "cVe4Xy0zTokenExample123456789"


def _row(**overrides):
    defaults = {
        "id": 5,
        "platform": PushPlatform.android,
        "device_id": "SM-S918B",
        "app_version": "1.0.0",
        "is_active": True,
        "last_seen_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return Mock(**defaults | overrides)


def _service(**stub: AsyncMock) -> tuple[PushSubscriptionService, Mock]:
    repo = Mock()
    for name, behaviour in stub.items():
        setattr(repo, name, behaviour)
    return PushSubscriptionService(repo), repo


class TestRegister:
    @pytest.mark.asyncio
    async def test_should_persist_registration(self):
        # given
        service, repo = _service(upsert_subscription=AsyncMock(return_value=_row()))

        # when
        result = await service.register(
            7,
            PushSubscriptionRequest(
                token=TOKEN,
                platform=PushPlatform.ios,
                device_id="iPhone 15 Pro",
                app_version="1.2.3",
            ),
        )

        # then
        kwargs = repo.upsert_subscription.await_args.kwargs
        assert kwargs["user_id"] == 7
        assert kwargs["token"] == TOKEN
        assert kwargs["platform"] == PushPlatform.ios
        assert kwargs["app_version"] == "1.2.3"
        assert result.id == 5
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_should_accept_minimal_request(self):
        # given — клиент может не знать device_id и app_version
        service, repo = _service(upsert_subscription=AsyncMock(return_value=_row()))

        # when
        await service.register(7, PushSubscriptionRequest(token=TOKEN, platform=PushPlatform.android))

        # then
        kwargs = repo.upsert_subscription.await_args.kwargs
        assert kwargs["device_id"] is None
        assert kwargs["app_version"] is None

    @pytest.mark.asyncio
    async def test_should_reject_short_token(self):
        # given — слишком короткий токен гарантированно мусор
        with pytest.raises(ValueError):
            # when
            PushSubscriptionRequest(token="x", platform=PushPlatform.android)


class TestUnregister:
    @pytest.mark.asyncio
    async def test_should_deactivate_owned_token(self):
        # given
        service, repo = _service(owns_token=AsyncMock(return_value=True), deactivate_token=AsyncMock(return_value=True))

        # when
        result = await service.unregister(7, TOKEN)

        # then
        assert result.removed == 1
        repo.deactivate_token.assert_awaited_once_with(TOKEN)

    @pytest.mark.asyncio
    async def test_should_ignore_foreign_token(self):
        # given — токен глобально уникален, гасить чужой нельзя
        service, repo = _service(owns_token=AsyncMock(return_value=False), deactivate_token=AsyncMock())

        # when
        result = await service.unregister(7, TOKEN)

        # then — 0, а не ошибка: клиент не может повлиять на ситуацию
        assert result.removed == 0
        repo.deactivate_token.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_check_owner_before_deactivating(self):
        # given — иначе любой пользователь гасил бы чужие устройства
        service, repo = _service(owns_token=AsyncMock(return_value=False), deactivate_token=AsyncMock())

        # when
        await service.unregister(7, TOKEN)

        # then
        repo.owns_token.assert_awaited_once_with(7, TOKEN)


class TestUnregisterAll:
    @pytest.mark.asyncio
    async def test_should_remove_every_device(self):
        # given
        service, repo = _service(delete_tokens_of_user=AsyncMock(return_value=3))

        # when
        result = await service.unregister_all(7)

        # then
        assert result.removed == 3
        repo.delete_tokens_of_user.assert_awaited_once_with(7)

    @pytest.mark.asyncio
    async def test_should_tolerate_zero_devices(self):
        # given — выход с устройства, где push и не был настроен
        service, _repo = _service(delete_tokens_of_user=AsyncMock(return_value=0))

        # when / then
        assert (await service.unregister_all(7)).removed == 0
