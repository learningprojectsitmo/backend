from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost/backend_db"
    DEBUG: str = "false"

    # Environment
    ENVIRONMENT: str = "development"

    # JWT
    SECRET_KEY: str = "your-secret-key-here"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200

    # CORS - исправленные настройки для Docker
    CORS_ORIGINS: list = [
        "http://localhost:5173/",
        "http://localhost:8000",
        "http://localhost:5173",
        "http://backend:8000",
        "http://localhost",
        "http://localhost:8083",
        "http://frontend:80",
        "fpin-projects.ru",
        "http://fpin-projects.ru:1268/",
        "http://fpin-projects.ru:12683/",
    ]

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: str = "app.log"
    ENABLE_FILE_LOGGING: bool = True
    ENABLE_CONSOLE_LOGGING: bool = True

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


settings = Settings()
