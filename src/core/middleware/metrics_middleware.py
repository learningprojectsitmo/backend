"""Middleware для сбора HTTP-метрик Prometheus (RPS, latency, ошибки).

Лейбл `path` берётся из шаблона маршрута FastAPI (`/v1/users/{user_id}`),
а не из сырого URL запроса: иначе каждый UUID/ID создавал бы новую серию и
счётчики быстро раздувались бы (кардинальность = число уникальных ID).
"""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.metrics import (
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    UNTRACKED_PATHS,
)

#: Фолбэк-нормализация, если маршрут не найден (404) или это не FastAPI-роут.
#: UUID, числа, hex-хэши и ObjectId приводим к плейсхолдерам.
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_HEX_RE = re.compile(r"\b[0-9a-fA-F]{24,}\b")
_NUM_RE = re.compile(r"/\d+(?=/|$)")

#: Статусы, которые считаем ошибками.
ERROR_STATUSES = frozenset({400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504})


def normalize_path(path: str) -> str:
    """Приводит URL к шаблону с плейсхолдерами для неизвестных маршрутов.

    Args:
        path: Сырой путь запроса.

    Returns:
        Путь, безопасный для лейбла (без ID, но с сохранением структуры).
    """

    normalized = _UUID_RE.sub("{id}", path)
    normalized = _HEX_RE.sub("{id}", normalized)
    return _NUM_RE.sub("/{id}", normalized)


def resolve_path(request: Request) -> str:
    """Определяет путь для лейбла: шаблон маршрута, иначе нормализованный URL.

    Args:
        request: Starlette-запрос (уже прошедший через call_next, поэтому
            в scope есть ``route``, выставленный FastAPI при маршрутизации).

    Returns:
        Значение лейбла ``path``.
    """

    route_path = getattr(request.scope.get("route"), "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path
    return normalize_path(request.url.path)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Считает RPS/latency/ошибки по каждому HTTP-запросу."""

    def __init__(self, app, exclude_paths: frozenset[str] | None = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths if exclude_paths is not None else UNTRACKED_PATHS

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if path in self.exclude_paths or request.scope.get("type") != "http":
            return await call_next(request)

        method = request.method
        in_progress = HTTP_REQUESTS_IN_PROGRESS.labels(method=method)
        in_progress.inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            in_progress.dec()
            duration = time.perf_counter() - start_time
            path_label = resolve_path(request)
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path_label).observe(duration)
            HTTP_REQUESTS_TOTAL.labels(method=method, path=path_label, status="500").inc()
            HTTP_ERRORS_TOTAL.labels(method=method, path=path_label, status="500").inc()
            raise

        in_progress.dec()
        duration = time.perf_counter() - start_time
        path_label = resolve_path(request)
        status = response.status_code

        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path_label).observe(duration)
        HTTP_REQUESTS_TOTAL.labels(method=method, path=path_label, status=str(status)).inc()
        if status in ERROR_STATUSES:
            HTTP_ERRORS_TOTAL.labels(method=method, path=path_label, status=str(status)).inc()

        return response


__all__ = [
    "ERROR_STATUSES",
    "MetricsMiddleware",
    "normalize_path",
    "resolve_path",
]
