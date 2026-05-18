from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, status

from src.model.user import User
from src.repository.user_repository import UserRepository
from src.schema.auth import Token
from src.services.auth_service import AuthService

ACCESS_TOKEN_EXPIRE_SECONDS = 1800


class TestAuthService:
    async def test_should_authenticate_user_with_valid_credentials(self):
        mock_repository = Mock(spec=UserRepository)
        mock_user = User(
            id=1,
            email="test@example.com",
            password_hashed="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj8jJLx1V1e.",
            first_name="Test",
            middle_name="User",
        )
        mock_repository.get_by_email.return_value = mock_user
        auth_service = AuthService(mock_repository, Mock(), Mock(), Mock(), Mock())

        with patch.object(auth_service, "verify_password", return_value=True):
            result = await auth_service.authenticate_user("test@example.com", "password")

        assert result.id == mock_user.id
        assert result.email == mock_user.email
        mock_repository.get_by_email.assert_called_once_with("test@example.com")

    async def test_should_return_none_for_invalid_credentials(self):
        mock_repository = Mock(spec=UserRepository)
        mock_repository.get_by_email.return_value = None
        auth_service = AuthService(mock_repository, Mock(), Mock(), Mock(), Mock())

        result = await auth_service.authenticate_user("test@example.com", "wrong_password")

        assert result is None
        mock_repository.get_by_email.assert_called_once_with("test@example.com")

    async def test_should_get_current_user_by_valid_access_token(self):
        mock_repository = Mock(spec=UserRepository)
        mock_user = User(id=1, email="test@example.com")
        mock_repository.get_by_email.return_value = mock_user
        auth_service = AuthService(mock_repository, Mock(), Mock(), Mock(), Mock())

        with patch("src.services.auth_service.jwt.decode") as mock_decode:
            mock_decode.return_value = {"sub": "test@example.com", "type": "access"}
            result = await auth_service.get_current_user("valid_token")

        assert result == mock_user
        mock_repository.get_by_email.assert_called_once_with("test@example.com")

    async def test_should_reject_refresh_token_in_get_current_user(self):
        mock_repository = Mock(spec=UserRepository)
        auth_service = AuthService(mock_repository, Mock(), Mock(), Mock(), Mock())

        with patch("src.services.auth_service.jwt.decode") as mock_decode:
            mock_decode.return_value = {"sub": "test@example.com", "type": "refresh"}
            with pytest.raises(HTTPException) as exc:
                await auth_service.get_current_user("refresh_token")
            assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_should_login_and_return_token_with_raw_refresh(self):
        mock_repository = Mock(spec=UserRepository)
        mock_user = User(
            id=1,
            email="test@example.com",
            password_hashed="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj8jJLx1V1e.",
            first_name="Test",
            middle_name="User",
        )
        mock_repository.get_by_email.return_value = mock_user

        mock_session_svc = Mock()
        mock_session_svc.create_session_with_refresh_token = AsyncMock()
        mock_session_svc.set_current_session = AsyncMock()

        auth_service = AuthService(mock_repository, mock_session_svc, Mock(), Mock(), Mock())

        with (
            patch.object(auth_service, "verify_password", return_value=True),
            patch.object(auth_service, "_generate_refresh_token", return_value=("raw_refresh", "hash")),
            patch.object(auth_service, "create_access_token", return_value="fake_access_token"),
        ):
            token, raw_refresh = await auth_service.login_for_access_token(
                email="test@example.com",
                password="password",
                remember_me=True,
            )

        assert isinstance(token, Token)
        assert token.access_token == "fake_access_token"
        assert token.token_type == "bearer"
        assert token.expires_in == ACCESS_TOKEN_EXPIRE_SECONDS
        assert raw_refresh == "raw_refresh"

    async def test_should_refresh_token_successfully(self):
        mock_repository = Mock(spec=UserRepository)
        mock_user = User(id=1, email="test@example.com")
        mock_repository.get_by_id.return_value = mock_user

        mock_session_svc = Mock()
        mock_session = Mock()
        mock_session.id = "session-1"
        mock_session.user_id = 1
        mock_session.token_family = "family-1"
        mock_session.expires_at = datetime.now(UTC) + timedelta(days=30)
        mock_session_svc.get_session_by_refresh_hash = AsyncMock(return_value=mock_session)
        mock_session_svc.rotate_refresh_token_in_session = AsyncMock(return_value=True)

        auth_service = AuthService(mock_repository, mock_session_svc, Mock(), Mock(), Mock())

        with (
            patch.object(auth_service, "_hash_token", return_value="some_hash"),
            patch.object(auth_service, "_generate_refresh_token", return_value=("new_raw", "new_hash")),
            patch.object(auth_service, "create_access_token", return_value="new_access_token"),
        ):
            token, new_raw, max_age = await auth_service.refresh_access_token("some_raw_token")

        assert token.access_token == "new_access_token"
        assert token.expires_in == ACCESS_TOKEN_EXPIRE_SECONDS
        assert new_raw == "new_raw"
        assert max_age > 0
        mock_session_svc.rotate_refresh_token_in_session.assert_called_once_with("session-1", "some_hash", "new_hash")

    async def test_should_detect_refresh_token_reuse(self):
        mock_repository = Mock(spec=UserRepository)
        mock_session_svc = Mock()
        mock_session = Mock()
        mock_session.id = "session-1"
        mock_session.user_id = 1
        mock_session.token_family = "family-1"
        mock_session_svc.get_session_by_refresh_hash = AsyncMock(return_value=mock_session)
        mock_session_svc.rotate_refresh_token_in_session = AsyncMock(return_value=False)  # reuse!
        mock_session_svc.revoke_token_family = AsyncMock(return_value=2)

        auth_service = AuthService(mock_repository, mock_session_svc, Mock(), Mock(), Mock())

        with (
            patch.object(auth_service, "_hash_token", return_value="stale_hash"),
            patch.object(auth_service, "_generate_refresh_token", return_value=("new_raw", "new_hash")),
        ):
            with pytest.raises(HTTPException) as exc:
                await auth_service.refresh_access_token("stale_token")
            assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
            assert "reuse" in exc.value.detail

        mock_session_svc.revoke_token_family.assert_called_once_with("family-1")
