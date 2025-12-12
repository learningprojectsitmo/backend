from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.security import verify_password
from src.model.models import User
from src.repository.user_repository import UserRepository
from src.schemas import Token, UserCreate

from .base_service import BaseService


class AuthService(BaseService[User, UserCreate, dict]):  # Используем dict вместо UserUpdate
    def __init__(self, user_repository: UserRepository, db_session: Session):
        super().__init__(user_repository)
        self._user_repository = user_repository
        self._db_session = db_session

    def authenticate_user(self, email: str, password: str) -> User | None:
        """Аутентификация пользователя по email и паролю"""
        return self._user_repository.authenticate_user(email, password, verify_password)

    def get_current_user(self, token: str) -> User:
        """Получить текущего пользователя по JWT токену"""
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            import jwt
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            email: str = payload.get('sub')
            if not email:
                raise credentials_exception

        except Exception as e:
            print(f"JWT Error: {e}")
            raise credentials_exception from e

        user = self._user_repository.get_by_email(email)
        if not user:
            raise credentials_exception

        return user

    def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:
        """Создать JWT токен доступа"""
        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode = data.copy()
        to_encode.update({"exp": expire})

        import jwt
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    async def login_for_access_token(
        self,
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
    ) -> Token:
        """Аутентификация пользователя и создание токена доступа"""
        # OAuth2PasswordRequestForm использует поле 'username', но мы treating его как email
        user = self.authenticate_user(form_data.username, form_data.password)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = self.create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )

        return Token(access_token=access_token, token_type="bearer")

    def get_user_by_token(self, token: str) -> User:
        """Получить пользователя по токену (алиас для get_current_user)"""
        return self.get_current_user(token)
