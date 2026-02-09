from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest

from src.core.exceptions import NotFoundError, ValidationError
from src.model.models import Notification, Project
from src.repository.notification_repository import NotificationRepository
from src.repository.project_participation_repository import ProjectParticipationRepository
from src.repository.project_repository import ProjectRepository
from src.services.notification_service import NotificationService


class TestNotificationService:
    """Тесты для NotificationService"""

    @pytest.mark.asyncio
    async def test_should_send_notification_to_user(self):
        """Тест должен отправить уведомление пользователю"""
        # given
        mock_notification_repository = Mock(spec=NotificationRepository)
        mock_project_repository = Mock(spec=ProjectRepository)
        mock_participation_repository = Mock(spec=ProjectParticipationRepository)

        mock_notification = Notification(
            id="test-id",
            recipient_id=1,
            sender_id=2,
            project_id=None,
            type="system_alert",
            status="pending",
            title="Системное уведомление",
            body="Test message",
            channels=[],
            created_at=datetime.now(),
        )
        mock_notification_repository.create.return_value = mock_notification

        service = NotificationService(
            mock_notification_repository,
            mock_project_repository,
            mock_participation_repository,
        )

        # when
        result = await service.send_to_user(
            recipient_id=1,
            sender_id=2,
            template_key="system_alert",
            payload={"message": "Test message"},
        )

        # then
        assert result == mock_notification
        mock_notification_repository.create.assert_called_once()

        created_data = mock_notification_repository.create.call_args[0][0]
        assert created_data["recipient_id"] == 1
        assert created_data["sender_id"] == 2
        assert created_data["type"] == "system_alert"
        assert created_data["status"] == "pending"
        assert created_data["title"] == "Системное уведомление"
        assert created_data["body"] == "Test message"
        assert isinstance(created_data["id"], str)

    @pytest.mark.asyncio
    async def test_should_send_notifications_to_project_participants(self):
        """Тест должен отправить уведомления участникам проекта"""
        # given
        mock_notification_repository = Mock(spec=NotificationRepository)
        mock_project_repository = Mock(spec=ProjectRepository)
        mock_participation_repository = Mock(spec=ProjectParticipationRepository)

        mock_project_repository.get_by_id.return_value = Project(id=1, name="Test Project", author_id=10)
        mock_participation_repository.get_participant_ids_by_project_id.return_value = [10, 11, 12]
        mock_notification_repository.create_many.return_value = []

        service = NotificationService(
            mock_notification_repository,
            mock_project_repository,
            mock_participation_repository,
        )

        # when
        result = await service.send_to_project_participants(
            project_id=1,
            sender_id=2,
            template_key="project_announcement",
            payload={"project_name": "Test Project", "message": "Hello"},
        )

        # then
        assert result == []
        mock_project_repository.get_by_id.assert_called_once_with(1)
        mock_participation_repository.get_participant_ids_by_project_id.assert_called_once_with(1)
        mock_notification_repository.create_many.assert_called_once()

        data_list = mock_notification_repository.create_many.call_args[0][0]
        assert len(data_list) == 3
        assert {item["recipient_id"] for item in data_list} == {10, 11, 12}

    @pytest.mark.asyncio
    async def test_should_raise_not_found_for_missing_project(self):
        """Тест должен выбросить ошибку при отсутствии проекта"""
        # given
        mock_notification_repository = Mock(spec=NotificationRepository)
        mock_project_repository = Mock(spec=ProjectRepository)
        mock_participation_repository = Mock(spec=ProjectParticipationRepository)

        mock_project_repository.get_by_id.return_value = None

        service = NotificationService(
            mock_notification_repository,
            mock_project_repository,
            mock_participation_repository,
        )

        # when & then
        with pytest.raises(NotFoundError, match="Project not found"):
            await service.send_to_project_participants(
                project_id=999,
                sender_id=1,
                template_key="project_announcement",
                payload={"project_name": "Test Project", "message": "Hello"},
            )

    def test_should_raise_validation_error_for_missing_payload(self):
        """Тест должен выбросить ошибку при отсутствии обязательных полей"""
        # when & then
        with pytest.raises(ValidationError, match="Missing payload fields"):
            NotificationService._render_template("project_announcement", {"project_name": "Test Project"})
