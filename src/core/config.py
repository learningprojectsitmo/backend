from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    # NOTE: db url is correct, you should not change postgres to localhost
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost/backend_db"
    DEBUG: str = "false"

    # Environment
    ENVIRONMENT: str = "development"

    # JWT
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS_SHORT: int = 1

    # CORS - исправленные настройки для Docker
    FRONTEND_URL: str = "http://localhost:3000"

    # SMTP (maildev: web UI http://localhost:9000, SMTP localhost:2500)
    MAIL_SMTP_HOST: str = "localhost"
    MAIL_SMTP_PORT: int = 2500
    MAIL_SMTP_USER: str | None = None
    MAIL_SMTP_PASSWORD: str | None = None
    MAIL_FROM: str = "maildev@localhost"
    MAIL_FROM_NAME: str = "FPIN Projects"
    MAIL_TLS: bool = False

    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://localhost:8083",
        "http://localhost:80",
        "http://localhost",
        "http://backend:8000",
        "http://frontend:80",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://127.0.0.1:8083",
        "http://fpin-projects.ru",
        "https://fpin-projects.ru",
    ]

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: str = "app.log"
    ENABLE_FILE_LOGGING: bool = True
    ENABLE_CONSOLE_LOGGING: bool = True

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


settings = Settings()
