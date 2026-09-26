from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.core.metrics import (
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    render_metrics,
    setup_metrics,
)
from src.core.middleware.metrics_middleware import normalize_path


@pytest.fixture
def metrics_app() -> FastAPI:
    """Минимальное приложение с метриками и предсказуемыми маршрутами."""

    app = FastAPI()

    @app.get("/v1/users/{user_id}")
    async def get_user(user_id: int) -> dict[str, int]:
        return {"id": user_id}

    @app.get("/v1/boom")
    async def boom() -> None:
        raise HTTPException(status_code=503, detail="unavailable")

    @app.get("/v1/crash")
    async def crash() -> None:
        raise RuntimeError("boom")

    setup_metrics(app)
    return app


@pytest.fixture
def client(metrics_app: FastAPI) -> TestClient:
    return TestClient(metrics_app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_metrics() -> None:
    """Счётчики живут в глобальном REGISTRY — чистим между тестами."""

    for metric in (HTTP_REQUESTS_TOTAL, HTTP_ERRORS_TOTAL, HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_IN_PROGRESS):
        metric.clear()
    yield


def _value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


class TestNormalizePath:
    def test_should_replace_uuid(self):
        # given
        path = "/v1/files/9f8e7d6c-5b4a-3210-9876-0a1b2c3d4e5f"

        # when / then
        assert normalize_path(path) == "/v1/files/{id}"

    def test_should_replace_numeric_ids(self):
        # given
        path = "/v1/users/42"

        # when / then
        assert normalize_path(path) == "/v1/users/{id}"

    def test_should_keep_path_without_ids(self):
        # given / when / then
        assert normalize_path("/v1/users") == "/v1/users"

    def test_should_keep_health_and_metrics_paths(self):
        # given / when / then
        assert normalize_path("/healthz") == "/healthz"
        assert normalize_path("/metrics") == "/metrics"


class TestMetricsEndpoint:
    def test_should_serve_prometheus_exposition_format(self, client: TestClient):
        # given
        client.get("/v1/users/1")

        # when
        response = client.get("/metrics")

        # then
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert 'http_requests_total{method="GET",path="/v1/users/{user_id}",status="200"} 1.0' in response.text

    def test_should_expose_process_collectors(self, client: TestClient):
        # given / when
        body = client.get("/metrics").text

        # then
        assert "process_resident_memory_bytes" in body
        assert "python_info" in body

    def test_should_not_track_itself(self, client: TestClient):
        # given
        client.get("/metrics")
        client.get("/metrics")

        # when
        body = client.get("/metrics").text

        # then
        assert 'path="/metrics"' not in body


class TestRequestCounting:
    def test_should_count_request_with_route_template_path(self, client: TestClient):
        # given
        client.get("/v1/users/1")

        # when
        client.get("/v1/users/2")

        # then: обе серии схлопнулись в одну, кардинальность не растёт
        assert _value(HTTP_REQUESTS_TOTAL, method="GET", path="/v1/users/{user_id}", status="200") == 2.0

    def test_should_split_series_by_status_code(self, client: TestClient):
        # given
        client.get("/v1/boom")
        client.get("/v1/users/1")

        # when
        body = client.get("/metrics").text

        # then
        assert 'path="/v1/boom",status="503"' in body
        assert 'path="/v1/users/{user_id}",status="200"' in body

    def test_should_count_unhandled_exception_as_500(self, client: TestClient):
        # given
        client.get("/v1/crash")

        # when / then
        assert _value(HTTP_REQUESTS_TOTAL, method="GET", path="/v1/crash", status="500") == 1.0
        assert _value(HTTP_ERRORS_TOTAL, method="GET", path="/v1/crash", status="500") == 1.0

    def test_should_count_error_status_in_error_counter(self, client: TestClient):
        # given
        client.get("/v1/boom")

        # when / then
        assert _value(HTTP_ERRORS_TOTAL, method="GET", path="/v1/boom", status="503") == 1.0

    def test_should_not_count_success_in_error_counter(self, client: TestClient):
        # given
        client.get("/v1/users/1")

        # when
        error_series = HTTP_ERRORS_TOTAL.collect()[0].samples

        # then
        assert all('status="200"' not in sample.labels.get("status", "") for sample in error_series)

    def test_should_normalize_path_for_unmatched_route(self, client: TestClient):
        # given
        client.get("/v1/unknown/9f8e7d6c-5b4a-3210-9876-0a1b2c3d4e5f")

        # when
        body = client.get("/metrics").text

        # then: 404 без сырого UUID в лейбле
        assert 'path="/v1/unknown/{id}",status="404"' in body

    def test_should_reset_in_progress_gauge(self, client: TestClient):
        # given
        client.get("/v1/users/1")
        client.get("/v1/crash")

        # when / then
        assert _value(HTTP_REQUESTS_IN_PROGRESS, method="GET") == 0.0


class TestDurationHistogram:
    def test_should_observe_duration(self, client: TestClient):
        # given
        client.get("/v1/users/1")

        # when
        payload, _ = render_metrics()

        # then
        assert b'http_request_duration_seconds_bucket{le="0.005"' in payload
        assert b'http_request_duration_seconds_count{method="GET",path="/v1/users/{user_id}"} 1.0' in payload

    def test_should_track_even_when_request_fails(self, client: TestClient):
        # given
        client.get("/v1/crash")

        # when
        payload, _ = render_metrics()

        # then
        assert b'http_request_duration_seconds_count{method="GET",path="/v1/crash"} 1.0' in payload
