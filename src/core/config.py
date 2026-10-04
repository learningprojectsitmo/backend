from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # Database
    # NOTE: db url is correct, you should not change postgres to localhost
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost/backend_db"
    DEBUG: str = "false"

    # Environment
    ENVIRONMENT: str = "development"

    # Схема БД. В development базу поднимает Base.metadata.create_all — это
    # удобно, пока разработчик гоняет фичи без миграций. В production схемой
    # владеет только Alembic: create_all не умеет ALTERить существующие
    # таблицы и молча пропускает новые колонки, поэтому флаг обязан быть
    # выключен (deploy/docker-compose.yml ставит "false").
    AUTO_CREATE_TABLES: bool = True

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

    # Sentry / GlitchTip
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 1.0

    # FCM (Firebase Cloud Messaging), HTTP v1
    # Выключено по умолчанию: без ключа сервис-аккаунта воркер не должен
    # ни стартовать, ни сыпать ошибками в логи на каждом уведомлении.
    PUSH_ENABLED: bool = False
    # JSON сервис-аккаунта целиком в base64 — в .env многострочные значения
    # неудобны, а путь к файлу в контейнере лишний. Путь тоже поддерживается
    # для локальной отладки.
    FIREBASE_CREDENTIALS_BASE64: str | None = None
    FIREBASE_CREDENTIALS_FILE: str | None = None
    # Берётся из самого service account, отдельная настройка — только если
    # ключ лежит в другом месте и project_id надо задать руками.
    FIREBASE_PROJECT_ID: str | None = None
    FCM_TIMEOUT_SECONDS: float = 10.0
    # Пауза между опросами outbox, когда он пуст. Чаще поллить смысла нет:
    # запросы к FCM платные, а задержка в несколько секунд на доставке
    # уведомления не видна человеку.
    PUSH_WORKER_POLL_SECONDS: float = 5.0
    PUSH_WORKER_BATCH_SIZE: int = 50
    PUSH_WORKER_ENABLED: bool = True

    model_config = SettingsConfigDict(env_file=_BACKEND_DIR / ".env", extra="ignore")


settings = Settings()
