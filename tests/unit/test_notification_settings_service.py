from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.model.models import NotificationSettings
from src.repository.notification_settings_repository import NotificationSettingsRepository
from src.schema.notification import NotificationSettingsUpdate
from src.services.notification_settings_service import NotificationSettingsService


class TestNotificationSettingsService:
    """Тесты для NotificationSettingsService"""

    @pytest.mark.asyncio
    async def test_should_get_notification_settings(self):
        """Тест должен получить настройки уведомлений пользователя"""
        # given
        mock_repository = Mock(spec=NotificationSettingsRepository)
        mock_settings = NotificationSettings(
            user_id=1,
            email_enabled=True,
            telegram_enabled=True,
            in_app_enabled=True,
            project_invitation_enabled=True,
            join_request_enabled=True,
            join_response_enabled=True,
            project_announcement_enabled=True,
            system_alert_enabled=True,
        )
        mock_repository.get_or_create.return_value = mock_settings

        service = NotificationSettingsService(mock_repository)

        # when
        result = await service.get_settings(1)

        # then
        assert result == mock_settings
        mock_repository.get_or_create.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_update_notification_settings(self):
        """Тест должен обновить настройки уведомлений пользователя"""
        # given
        mock_repository = Mock(spec=NotificationSettingsRepository)
        mock_settings = NotificationSettings(
            user_id=1,
            email_enabled=False,
            telegram_enabled=True,
            in_app_enabled=True,
            project_invitation_enabled=True,
            join_request_enabled=True,
            join_response_enabled=True,
            project_announcement_enabled=True,
            system_alert_enabled=True,
        )
        mock_repository.update_by_user_id.return_value = mock_settings

        service = NotificationSettingsService(mock_repository)
        update_data = NotificationSettingsUpdate(email_enabled=False)

        # when
        result = await service.update_settings(1, update_data)

        # then
        assert result == mock_settings
        mock_repository.update_by_user_id.assert_called_once_with(1, {"email_enabled": False})
