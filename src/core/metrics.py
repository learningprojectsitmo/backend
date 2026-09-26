"""Prometheus-метрики приложения: HTTP-RED и эндпоинт /metrics.

Метрики живут в дефолтном REGISTRY prometheus_client, поэтому в /metrics
попадают ещё и стандартные коллекторы процесса (`process_resident_memory_bytes`,
`process_cpu_seconds_total`, `python_gc_*`) — они нужны для дашборда «API».

Эндпоинт намеренно ВНЕ префикса `/v1` (роутеры API собираются с
`APIRouter(prefix="/v1")`): в проде edge проксирует в backend только `/v1/`,
поэтому `/metrics` доступен лишь из docker-сети, где его читает Prometheus.
"""

from __future__ import annotations

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client import (
    REGISTRY as DEFAULT_REGISTRY,
)

from src.core.logging_config import get_logger

#: Интервалы latency-гистограммы, секунды. Верхняя граница 10s с половиной
#: шага 0.5s даёт разумную точность p95/p99 на API с БД.
LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

#: Пути, которые не измеряем: иначе скрейп Prometheus'ом сам себя
#: засоряет счётчики, а /docs генерирует уникальные URL.
UNTRACKED_PATHS = frozenset(
    {
        "/metrics",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Всего HTTP-запросов к API",
    ("method", "path", "status"),
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "Длительность HTTP-запросов к API, секунды",
    ("method", "path"),
    buckets=LATENCY_BUCKETS,
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Количество HTTP-запросов в обработке прямо сейчас",
    ("method",),
)

#: Бизнес-алертам и дашбордам проще считать ошибки по одному счётчику
#: без разбора status-лейбла.
HTTP_ERRORS_TOTAL = Counter(
    "http_errors_total",
    "HTTP-запросы с кодом 4xx/5xx",
    ("method", "path", "status"),
)


def get_multiprocess_registry() -> CollectorRegistry | None:
    """Registry для multiprocess-режима uvicorn workers, если он включён.

    При нескольких worker-процессах каждый держит свой счётчик, и сводные
    значения будут неверными — тогда нужен общий файловый registry
    (`PROMETHEUS_MULTIPROC_DIR`). Возвращает None, если режим не задан.
    """

    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        return None

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return registry


def render_metrics() -> tuple[bytes, str]:
    """Тело /metrics в виде Prometheus exposition format.

    Returns:
        Кортеж (payload, content_type) — готовый ответ для HTTP.
    """

    registry = get_multiprocess_registry() or DEFAULT_REGISTRY
    return generate_latest(registry), CONTENT_TYPE_LATEST


def setup_metrics(app, *, route: str = "/metrics") -> None:
    """Подключает /metrics и HTTP-middleware к приложению.

    Args:
        app: FastAPI-приложение.
        route: Путь эндпоинта метрик вне префикса /v1.
    """

    from starlette.responses import Response  # noqa: PLC0415

    from src.core.middleware.metrics_middleware import MetricsMiddleware  # noqa: PLC0415 - против цикла импорта

    logger = get_logger(__name__)

    async def metrics_endpoint() -> Response:
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    app.add_api_route(
        route,
        metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
    )
    app.add_middleware(MetricsMiddleware)

    logger.info(f"Prometheus metrics enabled on {route} (labels: method, path, status)")
