from __future__ import annotations

from unittest.mock import Mock, patch

from fastapi.security import OAuth2PasswordRequestForm

from src.model.models import User
from src.repository.user_repository import UserRepository
from src.schema import Token
from src.services.auth_service import AuthService


class TestAuthService:
    async def test_should_authenticate_user_with_valid_credentials(self):
        """Тест должен проверить аутентификацию пользователя с корректными данными"""
        # given
        mock_repository = Mock(spec=UserRepository)
        # Используем правильный bcrypt хеш для пароля "password"
        mock_user = User(
            id=1,
            email="test@example.com",
            password_hashed="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj8jJLx1V1e.",
            first_name="Test",
            middle_name="User",
        )
        mock_repository.get_by_email.return_value = mock_user

        auth_service = AuthService(mock_repository, Mock(), Mock())

        with patch.object(auth_service, "verify_password", return_value=True):
            # when
            result = await auth_service.authenticate_user("test@example.com", "password")

            # then
            assert result.id == mock_user.id
            assert result.email == mock_user.email
            assert result.first_name == mock_user.first_name
            assert result.middle_name == mock_user.middle_name
            mock_repository.get_by_email.assert_called_once_with("test@example.com")

    async def test_should_return_none_for_invalid_credentials(self):
        """Тест должен вернуть None при некорректных учетных данных"""
        # given
        mock_repository = Mock(spec=UserRepository)
        mock_repository.get_by_email.return_value = None

        auth_service = AuthService(mock_repository, Mock(), Mock())

        # when
        result = await auth_service.authenticate_user("test@example.com", "wrong_password")

        # then
        assert result is None
        mock_repository.get_by_email.assert_called_once_with("test@example.com")

    async def test_should_get_current_user_by_valid_token(self):
        """Тест должен получить текущего пользователя по валидному токену"""
        # given
        mock_repository = Mock(spec=UserRepository)
        mock_user = User(id=1, email="test@example.com")
        mock_repository.get_by_email.return_value = mock_user

        auth_service = AuthService(mock_repository, Mock(), Mock())

        with patch("src.services.auth_service.jwt.decode") as mock_decode:
            mock_decode.return_value = {"sub": "test@example.com"}

            # when
            result = await auth_service.get_current_user("valid_token")

            # then
            assert result == mock_user
            mock_repository.get_by_email.assert_called_once_with("test@example.com")

    async def test_should_login_for_access_token_successfully(self):
        """Тест должен успешно выполнить вход для получения токена доступа"""
        # given
        mock_repository = Mock(spec=UserRepository)
        # Используем правильный bcrypt хеш для пароля "password"
        mock_user = User(
            id=1,
            email="test@example.com",
            password_hashed="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj8jJLx1V1e.",
            first_name="Test",
            middle_name="User",
        )
        mock_repository.get_by_email.return_value = mock_user

        auth_service = AuthService(mock_repository, Mock(), Mock())

        form_data = OAuth2PasswordRequestForm(username="test@example.com", password="password")

        with (
            patch.object(auth_service, "verify_password", return_value=True),
            patch.object(auth_service, "create_access_token") as mock_create_token,
        ):
            mock_create_token.return_value = "fake_jwt_token"

            # when
            result = await auth_service.login_for_access_token(form_data)

            # then
            assert isinstance(result, Token)
            assert result.access_token == "fake_jwt_token"
            assert result.token_type == "bearer"
            mock_repository.get_by_email.assert_called_once_with("test@example.com")
