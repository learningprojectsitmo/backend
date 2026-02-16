from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.model.models import User
from src.repository.user_repository import UserRepository
from src.schema import UserCreate, UserListResponse, UserUpdate
from src.services.user_service import UserService

# Константы для тестов
EXPECTED_USERS_COUNT = 2
EXPECTED_PAGE_LIMIT = 10


class TestUserService:
    """Тесты для UserService"""

    @pytest.mark.asyncio
    async def test_should_create_user_with_valid_data(self):
        """Тест должен создать пользователя с корректными данными"""
        # given
        mock_repository = Mock(spec=UserRepository)
        mock_auth_service = Mock()
        mock_auth_service.get_password_hash.return_value = "hashed_password"

        mock_user = User(
            id=1,
            email="test@example.com",
            first_name="Test",
            middle_name="User",
            password_hashed="hashed_password",
            role_id=1,
        )
        mock_repository.create.return_value = mock_user

        user_service = UserService(mock_repository, mock_auth_service)

        user_data = UserCreate(
            email="test@example.com",
            first_name="Test",
            middle_name="User",
            password_string="plain_password",
            role_id=1,
        )

        # when
        result = await user_service.create_user(user_data)

        # then
        assert result == mock_user
        mock_auth_service.get_password_hash.assert_called_once_with("plain_password")
        mock_repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_get_user_by_id(self):
        """Тест должен получить пользователя по ID"""
        # given
        mock_repository = Mock(spec=UserRepository)
        mock_user = User(id=1, email="test@example.com", first_name="Test", middle_name="User")
        mock_repository.get_by_id.return_value = mock_user

        user_service = UserService(mock_repository, Mock())

        # when
        result = await user_service.get_user_by_id(1)

        # then
        assert result == mock_user
        mock_repository.get_by_id.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_return_none_for_nonexistent_user(self):
        """Тест должен вернуть None для несуществующего пользователя"""
        # given
        mock_repository = Mock(spec=UserRepository)
        mock_repository.get_by_id.return_value = None

        user_service = UserService(mock_repository, Mock())

        # when
        result = await user_service.get_user_by_id(999)

        # then
        assert result is None
        mock_repository.get_by_id.assert_called_once_with(999)

    @pytest.mark.asyncio
    async def test_should_update_user_with_valid_data(self):
        """Тест должен обновить пользователя с корректными данными"""
        # given
        mock_repository = Mock(spec=UserRepository)
        updated_user = User(id=1, email="updated@example.com", first_name="Updated", middle_name="User")
        mock_repository.update.return_value = updated_user

        user_service = UserService(mock_repository, Mock())

        update_data = UserUpdate(email="updated@example.com", first_name="Updated")

        # when
        result = await user_service.update_user(1, update_data)

        # then
        assert result == updated_user
        mock_repository.update.assert_called_once_with(1, update_data)

    @pytest.mark.asyncio
    async def test_should_delete_user_successfully(self):
        """Тест должен успешно удалить пользователя"""
        # given
        mock_repository = Mock(spec=UserRepository)
        mock_repository.delete.return_value = True

        user_service = UserService(mock_repository, Mock())

        # when
        result = await user_service.delete_user(1)

        # then
        assert result is True
        mock_repository.delete.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_should_return_false_for_nonexistent_user_deletion(self):
        """Тест должен вернуть False при попытке удалить несуществующего пользователя"""
        # given
        mock_repository = Mock(spec=UserRepository)
        mock_repository.delete.return_value = False

        user_service = UserService(mock_repository, Mock())

        # when
        result = await user_service.delete_user(999)

        # then
        assert result is False
        mock_repository.delete.assert_called_once_with(999)

    @pytest.mark.asyncio
    async def test_should_get_users_paginated(self):
        """Тест должен получить пользователей с пагинацией"""
        # given
        mock_repository = Mock(spec=UserRepository)
        mock_users = [
            User(id=1, email="user1@example.com", first_name="User", middle_name="One"),
            User(id=2, email="user2@example.com", first_name="User", middle_name="Two"),
        ]

        mock_repository.get_multi.return_value = mock_users
        mock_repository.count.return_value = 2

        user_service = UserService(mock_repository, Mock())

        # when
        result = await user_service.get_users_paginated(page=1, limit=10)

        # then
        assert isinstance(result, UserListResponse)
        assert result.total == EXPECTED_USERS_COUNT
        assert len(result.items) == EXPECTED_USERS_COUNT
        assert result.page == 1
        assert result.limit == EXPECTED_PAGE_LIMIT
        assert result.total_pages == 1
        mock_repository.get_multi.assert_called_once_with(skip=0, limit=10)
        mock_repository.count.assert_called_once()
