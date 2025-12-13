"""Конфигурация логирования для приложения"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

from src.core.config import settings


def setup_logging() -> None:
    """Настройка системы логирования"""

    # Создаем директорию для логов если её нет
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Очищаем существующие обработчики
    root_logger.handlers.clear()

    # Форматтер для логов
    detailed_formatter = logging.Formatter(fmt=settings.LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    simple_formatter = logging.Formatter(fmt="%(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # Консольный обработчик
    if settings.ENABLE_CONSOLE_LOGGING:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
        console_handler.setFormatter(simple_formatter)
        root_logger.addHandler(console_handler)

    # Файловый обработчик с ротацией
    if settings.ENABLE_FILE_LOGGING:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_dir / settings.LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)

        # Отдельный файл для ошибок
        error_handler = logging.handlers.RotatingFileHandler(
            filename=log_dir / "errors.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(error_handler)


def get_logger(name: str) -> logging.Logger:
    """Получить логгер с указанным именем"""
    return logging.getLogger(name)


class SecurityLogger:
    """Специальный логгер для событий безопасности"""

    def __init__(self) -> None:
        self.logger = get_logger("security")

    def log_login_attempt(self, email: str, ip_address: str, user_agent: str, success: bool) -> None:
        """Логирование попытки входа"""
        status = "SUCCESS" if success else "FAILED"
        message = f"Login attempt - Email: {email}, IP: {ip_address}, User-Agent: {user_agent}, Status: {status}"

        if success:
            self.logger.info(message)
        else:
            self.logger.warning(message)

    def log_authentication_failure(self, email: str, reason: str, ip_address: str) -> None:
        """Логирование ошибок аутентификации"""
        self.logger.warning(f"Authentication failed - Email: {email}, Reason: {reason}, IP: {ip_address}")

    def log_permission_denied(self, user_id: int, action: str, resource: str, ip_address: str) -> None:
        """Логирование отказов в доступе"""
        self.logger.warning(
            f"Permission denied - User ID: {user_id}, Action: {action}, Resource: {resource}, IP: {ip_address}"
        )

    def log_suspicious_activity(self, user_id: int, activity: str, details: dict[str, Any]) -> None:
        """Логирование подозрительной активности"""
        self.logger.error(f"Suspicious activity - User ID: {user_id}, Activity: {activity}, Details: {details}")


class APILogger:
    """Логгер для API запросов"""

    def __init__(self) -> None:
        self.logger = get_logger("api")

    def log_request(
        self, method: str, path: str, user_id: int | None, ip_address: str, status_code: int, response_time: float
    ) -> None:
        """Логирование API запросов"""
        user_info = f"User: {user_id}" if user_id else "Anonymous"
        self.logger.info(
            f"API Request - {method} {path} - {user_info} - IP: {ip_address} - "
            f"Status: {status_code} - Time: {response_time:.3f}s"
        )

    def log_error(self, method: str, path: str, error: Exception, user_id: int | None) -> None:
        """Логирование ошибок API"""
        user_info = f"User: {user_id}" if user_id else "Anonymous"
        self.logger.error(f"API Error - {method} {path} - {user_info} - Error: {error!s}")


# Глобальные экземпляры логгеров
security_logger = SecurityLogger()
api_logger = APILogger()
