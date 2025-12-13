from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pwdlib import PasswordHash

from core.config import settings
from src.core.logging_config import get_logger, security_logger
from src.model.models import User
from src.repository.user_repository import UserRepository
from src.schema.auth import Token


class AuthService:
    def __init__(self, user_repository: UserRepository):
        self._user_repository = user_repository
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
            raise credentials_exception

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
