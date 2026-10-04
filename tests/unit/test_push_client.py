"""Юнит-тесты FCM-клиента: авторизация, разбор ошибок, кэш токена."""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.services.push_client import (
    FcmClient,
    FcmError,
    ServiceAccount,
    build_client,
)

_PROJECT = "demo-project"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()


def _service_account_json(**overrides) -> str:
    data = {
        "project_id": _PROJECT,
        "client_email": "sender@demo.iam.gserviceaccount.com",
        "private_key": _PRIVATE_PEM,
    }
    data.update(overrides)
    return json.dumps(data)


def _account(**overrides) -> ServiceAccount:
    return ServiceAccount.from_json(_service_account_json(**overrides))


def _client(handler, **kwargs) -> FcmClient:
    """Клиент с подставным транспортом: сеть в тестах не нужна."""
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return FcmClient(_account(), client=http, **kwargs)


def _ok_token(request: httpx.Request) -> httpx.Response:
    """Ответ на попытку обменять assertion на access token."""
    assert request.url.path == "/token"
    return httpx.Response(200, json={"access_token": "ya29.fake", "expires_in": 3600})


def _send_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"name": "projects/demo/messages/1"})


def _handler(token: httpx.Response | None = None):
    """Маршрутизатор: /token всегда обменивается, остальное — как скажут тесты."""

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return token if token is not None else _ok_token(request)
        return _send_ok(request)

    return route


class TestServiceAccount:
    def test_should_read_fields(self):
        # given / when
        account = _account()

        # then
        assert account.project_id == _PROJECT
        assert account.client_email == "sender@demo.iam.gserviceaccount.com"

    def test_should_load_from_base64(self):
        # given
        encoded = base64.b64encode(_service_account_json().encode()).decode()

        # when
        account = ServiceAccount.load(encoded, None)

        # then
        assert account.project_id == _PROJECT

    def test_should_prefer_base64_over_file(self):
        # given — в .env это основной способ, файл не должен мешать
        encoded = base64.b64encode(_service_account_json().encode()).decode()

        # when
        account = ServiceAccount.load(encoded, "/nonexistent/key.json")

        # then
        assert account.project_id == _PROJECT

    def test_should_reject_missing_key(self):
        # given — понятная ошибка важнее KeyError
        with pytest.raises(ValueError, match="FIREBASE_CREDENTIALS_BASE64"):
            # when
            ServiceAccount.load(None, None)

    def test_should_reject_incomplete_json(self):
        # given — если положить в base64 сам ключ, а не JSON
        encoded = base64.b64encode(b"-----BEGIN PRIVATE KEY-----").decode()

        # with
        with pytest.raises(ValueError):
            # when
            ServiceAccount.load(encoded, None)

    def test_should_name_missing_fields(self):
        # given
        with pytest.raises(ValueError, match="project_id"):
            # when
            _account(project_id="")


class TestSend:
    @pytest.mark.asyncio
    async def test_should_accept_message(self):
        # given
        client = _client(_handler())

        # when
        result = await client.send({"message": {"token": "t"}})

        # then
        assert result.accepted
        assert not result.retryable
        assert not result.token_invalid
        assert bool(result) is True
        await client.aclose()

    @pytest.mark.asyncio
    async def test_should_sign_jwt_for_fcm_scope(self):
        # given
        seen: dict = {}

        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                form = parse_qs(request.content.decode())
                seen["assertion"] = form["assertion"][0]
                return _ok_token(request)
            return _send_ok(request)

        client = _client(route)

        # when
        await client.send({"message": {"token": "t"}})

        # then — access token подписан приватным ключом сервис-аккаунта
        claims = jwt.decode(
            seen["assertion"],
            _KEY.public_key(),
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        assert claims["iss"] == "sender@demo.iam.gserviceaccount.com"
        assert claims["scope"] == "https://www.googleapis.com/auth/firebase.messaging"
        assert claims["exp"] - claims["iat"] <= 3600
        await client.aclose()

    @pytest.mark.asyncio
    async def test_should_reuse_access_token(self):
        # given
        calls: list[str] = []

        def route(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path == "/token":
                return _ok_token(request)
            return _send_ok(request)

        client = _client(route)

        # when
        for _ in range(5):
            await client.send({"message": {"token": "t"}})

        # then — один обмен на пять сообщений, а не пять
        assert calls.count("/token") == 1
        await client.aclose()

    @pytest.mark.asyncio
    async def test_should_post_to_project_endpoint(self):
        # given
        urls: list[str] = []

        def route(request: httpx.Request) -> httpx.Response:
            urls.append(str(request.url))
            return _ok_token(request) if request.url.path == "/token" else _send_ok(request)

        client = _client(route)

        # when
        await client.send({"message": {"token": "t"}})

        # then
        assert f"/v1/projects/{_PROJECT}/messages:send" in urls[-1]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_should_honour_explicit_project_id(self):
        # given — ключ может лежать отдельно от нужного проекта
        urls: list[str] = []

        def route(request: httpx.Request) -> httpx.Response:
            urls.append(str(request.url))
            return _ok_token(request) if request.url.path == "/token" else _send_ok(request)

        client = _client(route, project_id="other-project")

        # when
        await client.send({"message": {"token": "t"}})

        # then
        assert "/v1/projects/other-project/messages:send" in urls[-1]
        await client.aclose()


class TestErrorClassification:
    @pytest.mark.asyncio
    async def test_should_flag_unregistered_token(self):
        # given
        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                return _ok_token(request)
            return httpx.Response(
                404,
                json={"error": {"status": FcmError.UNREGISTERED, "message": "token gone"}},
            )

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then — токен надо деактивировать, повтор бессмыслен
        assert result.token_invalid
        assert not result.retryable

    @pytest.mark.asyncio
    async def test_should_never_retry_invalid_argument(self):
        # given — что бы ни было виновато, повтор тут не поможет
        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                return _ok_token(request)
            return httpx.Response(
                400,
                json={"error": {"status": FcmError.INVALID, "message": "bad payload"}},
            )

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then
        assert not result.accepted
        assert not result.retryable

    @pytest.mark.parametrize("status", [500, 503, 429])
    @pytest.mark.asyncio
    async def test_should_retry_server_errors(self, status: int):
        # given
        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                return _ok_token(request)
            return httpx.Response(status, json={"error": {"status": "UNAVAILABLE"}})

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then
        assert not result.accepted
        assert result.retryable
        assert not result.token_invalid

    @pytest.mark.asyncio
    async def test_should_retry_network_error(self):
        # given
        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                return _ok_token(request)
            raise httpx.ConnectError("connection refused")

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then — единственный класс, где повтор честно помогает
        assert result.retryable

    @pytest.mark.asyncio
    async def test_should_not_retry_on_auth_failure(self):
        # given — неверный ключ не чинится повтором
        def route(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"error": "invalid_grant"})

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then
        assert not result.accepted
        assert not result.retryable

    @pytest.mark.asyncio
    async def test_should_keep_token_when_payload_is_at_fault(self):
        # given — INVALID_ARGUMENT на поле notification: это наша ошибка,
        # токен тут ни при чём, и гасить его нельзя
        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                return _ok_token(request)
            return httpx.Response(
                400,
                json={
                    "error": {
                        "status": FcmError.INVALID,
                        "message": "invalid notification",
                        "details": [{"field": "notification.title"}],
                    }
                },
            )

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then
        assert not result.token_invalid
        assert not result.retryable

    @pytest.mark.asyncio
    async def test_should_flag_token_when_fcm_blames_token_field(self):
        # given — тот же код, но FCM прямо указал на token
        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                return _ok_token(request)
            return httpx.Response(
                400,
                json={
                    "error": {
                        "status": FcmError.INVALID,
                        "message": "invalid token",
                        "details": [{"field": "message.token"}],
                    }
                },
            )

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then
        assert result.token_invalid

    @pytest.mark.asyncio
    async def test_should_not_guess_when_fcm_omits_details(self):
        # given — нет details, доказательств нет: оставляем токен в работе
        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                return _ok_token(request)
            return httpx.Response(400, json={"error": {"status": FcmError.INVALID, "message": "invalid argument"}})

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then — лишний запрос к устройству дешевле тихо сожжённого токена
        assert not result.token_invalid

    @pytest.mark.asyncio
    async def test_should_flag_third_party_auth_as_token_problem(self):
        # given — APNs отверг: сертификат, а не токен, но и не наш payload
        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                return _ok_token(request)
            return httpx.Response(401, json={"error": {"status": FcmError.PAYLOAD, "message": "APNs auth failed"}})

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then
        assert result.token_invalid
        assert not result.retryable

    @pytest.mark.asyncio
    async def test_should_survive_non_json_error_body(self):
        # given — прокси может вернуть HTML
        def route(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/token":
                return _ok_token(request)
            return httpx.Response(400, text="<html>bad gateway</html>")

        # when
        result = await _client(route).send({"message": {"token": "t"}})

        # then — не должно быть исключения
        assert not result.accepted


class TestBuildClient:
    def test_should_build_from_base64(self):
        # given
        encoded = base64.b64encode(_service_account_json().encode()).decode()

        # when
        client = build_client(credentials_base64=encoded, credentials_file=None)

        # then
        assert isinstance(client, FcmClient)
