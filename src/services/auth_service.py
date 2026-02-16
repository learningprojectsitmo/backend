from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pwdlib import PasswordHash

from core.config import settings
from src.core.logging_config import get_logger, security_logger
from src.model.models import User
from src.repository.password_reset_repository import PasswordResetRepository
from src.repository.user_repository import UserRepository
from src.schema.auth import Token
from src.schema.session import SessionCreate, SessionTerminateRequest
from src.services.session_service import SessionService


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        session_service: SessionService,
        password_reset_repository: PasswordResetRepository,
    ):
        self._user_repository = user_repository
        self._session_service = session_service
        self._password_reset_repository = password_reset_repository
        self._pwd_context = PasswordHash.recommended()
        self._secret_key = settings.SECRET_KEY
        self._algorithm = settings.ALGORITHM
        self._access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self._logger = get_logger(self.__class__.__name__)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Проверить пароль"""
        return self._pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Хешировать пароль"""
        return self._pwd_context.hash(password)

    async def authenticate_user(self, email: str, password: str) -> User | None:
        """Аутентификация пользователя"""
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

    async def get_current_user(self, token: str) -> User:
        """Получить текущего пользователя из токена"""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
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

        self._logger.debug(f"Successfully validated token for user: {email} (ID: {user.id})")
        return user

    def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:
        """Создать токен доступа"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(minutes=self._access_token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self._secret_key, algorithm=self._algorithm)

        self._logger.debug(f"Access token created for user: {data.get('sub', 'unknown')}")
        return encoded_jwt

    async def login_for_access_token(
        self,
        form_data: OAuth2PasswordRequestForm,
        request: Request | None = None,
    ) -> Token:
        """Вход в систему и получение токена"""
        email = form_data.username
        self._logger.info(f"Login attempt for email: {email}")

        user = await self.authenticate_user(email, form_data.password)
        if not user:
            # Логируем неудачную попытку входа через security_logger
            ip_address = request.client.host if request and request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown") if request else "unknown"
            security_logger.log_authentication_failure(email=email, reason="Invalid credentials", ip_address=ip_address)

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Успешный вход
        access_token_expires = timedelta(minutes=self._access_token_expire_minutes)
        access_token = self.create_access_token(
            data={"sub": user.email},
            expires_delta=access_token_expires,
        )

        # Создаем сессию при входе (если есть request)
        if request:
            try:
                # Извлекаем информацию об устройстве и браузере
                user_agent = request.headers.get("user-agent", "")
                ip_address = request.client.host if request.client else "unknown"

                # Парсим user_agent для получения информации о браузере и ОС
                browser_name, browser_version = self._parse_user_agent(user_agent)
                device_name = self._get_device_name(user_agent)
                operating_system = self._get_os_name(user_agent)
                device_type = self._get_device_type(user_agent)

                # Создаем сессию
                session_data = SessionCreate(
                    user_id=user.id,
                    device_name=device_name,
                    browser_name=browser_name,
                    browser_version=browser_version,
                    operating_system=operating_system,
                    device_type=device_type,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    expires_at=datetime.now(UTC) + access_token_expires,
                )

                # Создаем сессию и устанавливаем как текущую
                session = await self._session_service.create_session(session_data)
                await self._session_service.set_current_session(user.id, session.id)

                self._logger.info(f"Session created for user {user.id} with ID: {session.id}")

            except Exception:
                self._logger.exception("Failed to create session for user %s", user.id)

        # Логируем успешный вход
        if request:
            ip_address = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "unknown")
            security_logger.log_login_attempt(email=email, ip_address=ip_address, user_agent=user_agent, success=True)

        self._logger.info(f"Successful login for user: {email} (ID: {user.id})")

        return Token(access_token=access_token, token_type="bearer")

    async def get_user_by_token(self, token: str) -> User:
        """Получить пользователя по токену"""
        return await self.get_current_user(token)

    def _parse_user_agent(self, user_agent: str) -> tuple[str | None, str | None]:
        """Парсить User-Agent для получения информации о браузере"""
        if not user_agent:
            return None, None

        user_agent = user_agent.lower()

        # Определяем браузер с максимальной оптимизацией
        if "chrome" in user_agent:
            if "edg" in user_agent and (version := self._extract_version(user_agent, "edg/")):
                return "Edge", version
            elif version := self._extract_version(user_agent, "chrome/"):
                return "Chrome", version
        elif "firefox" in user_agent and (version := self._extract_version(user_agent, "firefox/")):
            return "Firefox", version
        elif ("opera" in user_agent or "opr" in user_agent) and (version := self._extract_version(user_agent, "opr/")):
            return "Opera", version
        elif (
            "safari" in user_agent
            and "chrome" not in user_agent
            and (version := self._extract_version(user_agent, "version/"))
        ):
            return "Safari", version

        return "Unknown Browser", None

    def _extract_version(self, user_agent: str, pattern: str) -> str | None:
        """Извлечь версию из User-Agent"""
        try:
            index = user_agent.find(pattern)
            if index == -1:
                return None
            version_start = index + len(pattern)
            version_end = user_agent.find(" ", version_start)
            if version_end == -1:
                version_end = len(user_agent)
            return user_agent[version_start:version_end]
        except Exception:
            return None

    def _get_device_name(self, user_agent: str) -> str | None:
        """Определить имя устройства из User-Agent"""
        if not user_agent:
            return None

        user_agent = user_agent.lower()

        # Определяем устройство в порядке приоритета
        if "iphone" in user_agent:
            return "iPhone"
        elif "ipad" in user_agent:
            return "iPad"
        elif "android" in user_agent:
            return "Android Phone" if "mobile" in user_agent else "Android Device"
        elif "mobile" in user_agent or "tablet" in user_agent:
            return "Mobile Device" if "mobile" in user_agent else "Tablet"
        return "Desktop"

    def _get_os_name(self, user_agent: str) -> str | None:
        """Определить операционную систему из User-Agent"""
        if not user_agent:
            return None

        user_agent = user_agent.lower()

        # Определяем ОС в порядке приоритета
        if "windows nt" in user_agent or ("mac os x" in user_agent or "macintosh" in user_agent):
            return "Windows" if "windows nt" in user_agent else "macOS"
        elif "android" in user_agent:
            return "Android"
        elif "iphone" in user_agent or "ipad" in user_agent or "ios" in user_agent:
            return "iOS"
        elif "linux" in user_agent or "cros" in user_agent:
            return "Linux" if "linux" in user_agent else "Chrome OS"
        return "Unknown OS"

    def _get_device_type(self, user_agent: str) -> str | None:
        """Определить тип устройства из User-Agent"""
        if not user_agent:
            return None

        user_agent = user_agent.lower()

        if "mobile" in user_agent or "android" in user_agent or "iphone" in user_agent:
            return "mobile"
        elif "tablet" in user_agent or "ipad" in user_agent:
            return "tablet"
        else:
            return "desktop"

    async def logout(self, token: str, request: Request | None = None) -> bool:
        """Выход из системы - завершить текущую сессию"""
        try:
            # Получаем пользователя по токену
            user = await self.get_current_user(token)

            # Завершаем все сессии пользователя
            sessions = await self._session_service.get_user_sessions(user.id)
            if sessions.sessions:
                session_ids = [session.id for session in sessions.sessions]

                terminate_request = SessionTerminateRequest(session_ids=session_ids)
                await self._session_service.terminate_sessions(terminate_request)

                self._logger.info(f"Terminated {len(session_ids)} sessions for user {user.id}")

            # Логируем выход
            if request:
                ip_address = request.client.host if request.client else "unknown"
                user_agent = request.headers.get("user-agent", "unknown")
                security_logger.log_logout_attempt(email=user.email, ip_address=ip_address, user_agent=user_agent)

        except Exception:
            self._logger.exception("Error during logout")
            return False
        else:
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
