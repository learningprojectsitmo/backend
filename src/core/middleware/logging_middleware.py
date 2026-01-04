"""Middleware для логирования HTTP запросов и ответов"""

from __future__ import annotations

import time
from collections.abc import Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logging_config import get_logger

HTTP_STATUS_ERROR_THRESHOLD = 400


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования HTTP запросов"""

    def __init__(self, app: FastAPI, exclude_paths: list[str] | None = None):
        super().__init__(app)
        self.logger = get_logger(self.__class__.__name__)
        self.exclude_paths = exclude_paths or ["/docs", "/redoc", "/openapi.json", "/health", "/favicon.ico"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        # Проверяем, нужно ли логировать этот путь
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Получаем информацию о запросе
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        method = request.method
        path = request.url.path

        # Логируем начало запроса
        self.logger.debug(f"Request started - {method} {path} - IP: {client_ip} - User-Agent: {user_agent}")

        try:
            # Выполняем запрос
            response = await call_next(request)

            # Вычисляем время выполнения
            process_time = time.time() - start_time

            # Получаем статус код и информацию об аутентификации
            status_code = response.status_code
            user_id = getattr(request.state, "user_id", None)

            # Логируем завершение запроса
            if status_code >= HTTP_STATUS_ERROR_THRESHOLD:  # HTTP error status codes
                self.logger.warning(
                    f"Request completed with error - {method} {path} - "
                    f"Status: {status_code} - Time: {process_time:.3f}s - "
                    f"IP: {client_ip} - User: {user_id or 'Anonymous'}"
                )
            else:
                self.logger.info(
                    f"Request completed - {method} {path} - "
                    f"Status: {status_code} - Time: {process_time:.3f}s - "
                    f"IP: {client_ip} - User: {user_id or 'Anonymous'}"
                )

            # Добавляем заголовок с временем выполнения
            response.headers["X-Process-Time"] = str(process_time)

        except Exception:
            # Логируем ошибки
            process_time = time.time() - start_time
            self.logger.exception(f"Request failed - {method} {path} - Time: {process_time:.3f}s - IP: {client_ip}")
            raise
        else:
            return response

    def _get_client_ip(self, request: Request) -> str:
        """Получить IP адрес клиента"""
        # Проверяем различные источники IP адреса
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        if request.client and request.client.host:
            return request.client.host

        return "unknown"


def setup_logging_middleware(app: FastAPI) -> None:
    """Настройка middleware для логирования"""
    app.add_middleware(LoggingMiddleware)
