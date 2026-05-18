from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, status
from jose import JWTError, jwt
from pwdlib import PasswordHash

from src.core.config import settings
from src.core.logging_config import get_logger, security_logger
from src.model.user import User
from src.repository.password_reset_repository import PasswordResetRepository

if TYPE_CHECKING:
    from src.repository.role_repository import UserPermissionRepository
    from src.repository.user_repository import RolePermissionRepository, UserRepository

from src.schema.auth import Token
from src.schema.session import SessionCreate, SessionTerminateRequest
from src.services.session_service import SessionService


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        session_service: SessionService,
        password_reset_repository: PasswordResetRepository,
        user_permission_repository: UserPermissionRepository,
        role_permission_repository: RolePermissionRepository,
    ):
        self._user_repository = user_repository
        self._session_service = session_service
        self._user_permission_repository = user_permission_repository
        self._role_permission_repository = role_permission_repository
        self._password_reset_repository = password_reset_repository
        self._pwd_context = PasswordHash.recommended()
        self._secret_key = settings.SECRET_KEY
        self._algorithm = settings.ALGORITHM
        self._access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self._refresh_token_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
        self._refresh_token_expire_days_short = settings.REFRESH_TOKEN_EXPIRE_DAYS_SHORT
        self._logger = get_logger(self.__class__.__name__)

    # ───────── helpers ─────────

    @staticmethod
    def _hash_token(raw: str) -> str:
        """SHA-256 хеш refresh-токена (сырой токен никогда не хранится в БД)"""
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _generate_refresh_token() -> tuple[str, str]:
        """Сгенерировать opaque refresh-токен. Возвращает (raw, hash)"""
        raw = secrets.token_urlsafe(32)
        return raw, AuthService._hash_token(raw)

    # ───────── password ─────────

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self._pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return self._pwd_context.hash(password)

    async def authenticate_user(self, email: str, password: str) -> User | None:
        self._logger.debug(f"Authentication attempt for email: {email}")

        user = await self._user_repository.get_by_email(email)
        if not user:
            self._logger.warning(f"User not found with email: {email}")
            return None

        if not self.verify_password(password, user.password_hashed):
            self._logger.warning(f"Invalid password for user: {email}")
            return None

        self._logger.info(f"Successful authentication for user: {email} (ID: {user.id})")
        return user

    # ───────── access token (JWT) ─────────

    def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:
        to_encode = data.copy()
        to_encode.update({"type": "access"})
        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(minutes=self._access_token_expire_minutes)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, self._secret_key, algorithm=self._algorithm)

    async def get_current_user(self, token: str) -> User:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
            if payload.get("type") != "access":
                self._logger.warning("Token validation failed: not an access token")
                raise credentials_exception
            email: str = payload.get("sub")
            if email is None:
                self._logger.warning("Token validation failed: no email in payload")
                raise credentials_exception
        except JWTError as e:
            self._logger.warning(f"Token validation failed: JWT error - {e!s}")
            raise credentials_exception from e

        user = await self._user_repository.get_by_email(email)
        if user is None:
            self._logger.warning(f"Token validation failed: user not found for email {email}")
            raise credentials_exception
        return user

    # ───────── login ─────────

    async def login_for_access_token(
        self,
        email: str,
        password: str,
        remember_me: bool = True,
        request: Request | None = None,
    ) -> tuple[Token, str]:
        """Вход в систему. Возвращает (Token, raw_refresh_token)."""
        self._logger.info(f"Login attempt for email: {email}")

        user = await self.authenticate_user(email, password)
        if not user:
            ip_address = request.client.host if request and request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown") if request else "unknown"
            security_logger.log_authentication_failure(email=email, reason="Invalid credentials", ip_address=ip_address)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        refresh_expire_days = self._refresh_token_expire_days if remember_me else self._refresh_token_expire_days_short
        access_ttl = timedelta(minutes=self._access_token_expire_minutes)
        refresh_ttl = timedelta(days=refresh_expire_days)

        access_token = self.create_access_token(
            data={"sub": user.email, "user_id": user.id},
            expires_delta=access_ttl,
        )

        raw_refresh, refresh_hash = self._generate_refresh_token()
        token_family = str(uuid.uuid4())

        if request:
            try:
                user_agent = request.headers.get("user-agent", "")
                ip_address = request.client.host if request.client else "unknown"

                session_data = SessionCreate(
                    user_id=user.id,
                    device_name=self._get_device_name(user_agent),
                    browser_name=self._parse_user_agent(user_agent)[0],
                    browser_version=self._parse_user_agent(user_agent)[1],
                    operating_system=self._get_os_name(user_agent),
                    device_type=self._get_device_type(user_agent),
                    ip_address=ip_address,
                    user_agent=user_agent,
                    expires_at=datetime.now(UTC) + refresh_ttl,
                )

                session = await self._session_service.create_session_with_refresh_token(
                    session_data, refresh_hash, token_family
                )
                await self._session_service.set_current_session(user.id, session.id)
                self._logger.info(f"Session created for user {user.id} with ID: {session.id}")

            except Exception:
                self._logger.exception("Failed to create session for user %s", user.id)

        if request:
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            security_logger.log_login_attempt(email=email, ip_address=ip_address, user_agent=user_agent, success=True)

        self._logger.info(f"Successful login for user: {email} (ID: {user.id})")

        return (
            Token(access_token=access_token, expires_in=self._access_token_expire_minutes * 60),
            raw_refresh,
        )

    # ───────── refresh (opaque token + rotation + reuse detection) ─────────

    async def refresh_access_token(self, raw_refresh_token: str) -> tuple[Token, str, int]:
        """Обновить access-токен. Возвращает (Token, новый_raw_refresh_token, max_age_секунд)."""
        exc = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

        token_hash = self._hash_token(raw_refresh_token)
        session = await self._session_service.get_session_by_refresh_hash(token_hash)

        if not session:
            self._logger.warning("Refresh failed: session not found by token hash")
            raise exc

        new_raw, new_hash = self._generate_refresh_token()
        rotated = await self._session_service.rotate_refresh_token_in_session(session.id, token_hash, new_hash)

        if not rotated:
            revoked = await self._session_service.revoke_token_family(session.token_family)
            self._logger.warning(
                "Refresh token reuse detected! Revoked %d sessions in family %s",
                revoked,
                session.token_family,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token reuse detected; all sessions in this family revoked",
            )

        user = await self._user_repository.get_by_id(session.user_id)
        if not user:
            raise exc

        access_token = self.create_access_token(
            data={"sub": user.email, "user_id": user.id},
            expires_delta=timedelta(minutes=self._access_token_expire_minutes),
        )

        self._logger.info(f"Access token refreshed for user: {user.email} (ID: {user.id})")

        max_age = max(0, int((session.expires_at - datetime.now(UTC)).total_seconds())) if session.expires_at else 0

        return (
            Token(access_token=access_token, expires_in=self._access_token_expire_minutes * 60),
            new_raw,
            max_age,
        )

    async def get_user_by_token(self, token: str) -> User:
        return await self.get_current_user(token)

    # ───────── logout ─────────

    async def logout(self, token: str, request: Request | None = None) -> bool:
        """Выход из системы — завершить сессию по access-токену"""
        try:
            user = await self.get_current_user(token)

            sessions = await self._session_service.get_user_sessions(user.id)
            if sessions.sessions:
                session_ids = [session.id for session in sessions.sessions]
                terminate_request = SessionTerminateRequest(session_ids=session_ids)
                await self._session_service.terminate_sessions(terminate_request)
                self._logger.info(f"Terminated {len(session_ids)} sessions for user {user.id}")

            if request:
                ip_address = request.client.host if request.client else "unknown"
                user_agent = request.headers.get("user-agent", "unknown")
                security_logger.log_logout_attempt(email=user.email, ip_address=ip_address, user_agent=user_agent)

        except Exception:
            self._logger.exception("Error during logout")
            return False
        else:
            return True

    async def logout_by_refresh_token(self, raw_refresh_token: str) -> bool:
        """Выход из системы — завершить сессию по refresh-токену (из cookie)"""
        token_hash = self._hash_token(raw_refresh_token)
        session = await self._session_service.get_session_by_refresh_hash(token_hash)
        if not session:
            return False
        await self._session_service.terminate_session(session.id)
        self._logger.info(f"Session {session.id} terminated via refresh token logout")
        return True

    async def terminate_all_other_sessions(self, token: str, current_session_id: str | None = None) -> dict:
        """Завершить все сессии кроме текущей"""
        try:
            user = await self.get_current_user(token)

            if current_session_id:
                # Завершаем все сессии кроме указанной
                sessions = await self._session_service.get_user_sessions(user.id)
                other_sessions = [s.id for s in sessions.sessions if s.id != current_session_id]

                if other_sessions:
                    terminate_request = SessionTerminateRequest(session_ids=other_sessions)
                    result = await self._session_service.terminate_sessions(terminate_request)

                    self._logger.info(f"Terminated {len(other_sessions)} sessions for user {user.id} except current")
                    return {"terminated_count": len(result.terminated_sessions), "message": result.message}

        except Exception:
            self._logger.exception("Error terminating other sessions")
            raise
        else:
            return {"terminated_count": 0, "message": "No other sessions found"}

    async def get_user_sessions_info(self, token: str) -> dict:
        """Получить информацию о сессиях пользователя"""
        try:
            user = await self.get_current_user(token)
            sessions_summary = await self._session_service.get_sessions_summary(user.id)
            sessions_stats = await self._session_service.get_session_stats(user.id)

            return {"summary": sessions_summary, "stats": sessions_stats.model_dump()}

        except Exception:
            self._logger.exception("Error getting user sessions info")
            raise

    async def refresh_session_activity(self, token: str, session_id: str | None = None) -> bool:
        """Обновить активность сессии для продления срока действия"""
        try:
            user = await self.get_current_user(token)

            # Если session_id не указан, получаем текущую сессию
            if not session_id:
                sessions = await self._session_service.get_user_sessions(user.id)
                if sessions.current_session_id:
                    session_id = sessions.current_session_id
                else:
                    self._logger.warning(f"No current session found for user {user.id}")
                    return False

            # Обновляем активность сессии
            await self._session_service.update_session_activity(session_id)
        except Exception:
            self._logger.exception("Error refreshing session activity")
            return False
        else:
            self._logger.debug(f"Refreshed activity for session {session_id}")
            return True

    async def request_password_reset(self, email: str) -> bool:
        """Запрос сброса пароля"""

        user = await self._user_repository.get_by_email(email)

        if not user:
            self._logger.warning(f"Password reset request for non-existent email: {email}")
            return False

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        reset_data = {"user_id": user.id, "token": token, "expires_at": expires_at}

        await self._password_reset_repository.create(reset_data)

        # TODO: добавить генерацию и отправку ссылки через email-клиент, сейчас токен для сброса доступен в БД
        self._logger.info(f"Password reset requested for user {user.id}")
        return True

    async def confirm_password_reset(self, token: str, new_password: str) -> bool:
        """Подтвердить сброс пароля"""

        reset = await self._password_reset_repository.get_by_token(token)

        if not reset:
            self._logger.warning("Password reset attempted with invalid token")
            return False

        if datetime.now(UTC) > reset.expires_at:
            self._logger.warning(f"Password reset attempted with expired token for user {reset.user_id}")
            await self._password_reset_repository.delete(reset.id)
            return False

        hashed_password = self.get_password_hash(new_password)
        await self._user_repository.update(reset.user_id, {"password_hashed": hashed_password})
        await self._password_reset_repository.delete(reset.id)

        self._logger.info(f"Password reset successful for user {reset.user_id}")
        return True

    async def get_all_user_permissions(
        self,
        current_user: User,
    ) -> list[str]:
        """Получить список всех разрешений, которые есть у пользователя и его роли"""

        user_permissions = await self._user_permission_repository.get_user_permissions(current_user.id)
        user_role_permissions = await self._role_permission_repository.get_role_permissions(current_user.role_id)

        return list(set(user_permissions + user_role_permissions))
