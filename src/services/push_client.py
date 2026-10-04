"""Клиент FCM HTTP v1.

firebase-admin не берём: он тянет grpc и синхронный `send()` в потоке, а у
проекта весь I/O асинхронный. Здесь те же ~100 строк на httpx, без
блокировки event loop и без лишней зависимости.

Протокол: подписка OAuth2 access token (RS256, из private_key сервис-аккаунта)
живёт максимум час, поэтому токен кэшируется и обновляется заранее. FCM не
показывает, кому именно доставлено, — «доставлено» здесь означает «FCM
принял», что и отражено в имени `SendResult.accepted`.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import httpx
import jwt
from loguru import logger

_SCOPE: Final = "https://www.googleapis.com/auth/firebase.messaging"
#: FCM отвергает access token с временем жизни больше часа, поэтому берём час
#: с запасом и обновляем заранее — иначе половина запросов падала бы на
#: границе с 401.
_TOKEN_TTL_SECONDS: Final = 3600
_TOKEN_REFRESH_MARGIN: Final = 300


class FcmError(StrEnum):
    """Что именно сказал FCM."""

    NONE = ""
    #: Токен больше не существует: приложение удалено, или токен отозван
    #: после восстановления бэкапа. Подписку надо деактивировать.
    UNREGISTERED = "UNREGISTERED"
    #: Ошибка в самом сообщении или в токене — и FCM не различает их в коде:
    #: `INVALID_ARGUMENT` прилетает и на битое поле `notification`, и на
    #: невалидный токен. Токеном это считаться не может: иначе наша ошибка
    #: в payload тихо сжигала бы токены пользователей, а уведомления просто
    #: переставали бы приходить без единой ошибки в логах. Разбор идёт по
    #: `details[].field`, и если там не token — это наша ошибка.
    INVALID = "INVALID_ARGUMENT"
    #: APNs отверг сообщение: сертификат или ключ не настроен. Токен тут ни
    #: при чём, лечится на стороне проекта.
    PAYLOAD = "THIRD_PARTY_AUTH_ERROR"
    #: Сетевая ошибка, 5xx, 429 — есть смысл повторить позже.
    TRANSIENT = "UNAVAILABLE"


@dataclass(frozen=True)
class SendResult:
    """Итог одной попытки отправки."""

    accepted: bool
    error: str = ""
    #: Токен нужно деактивировать — повторно слать в него бессмысленно.
    token_invalid: bool = False
    #: Стоит ли повторить позже.
    retryable: bool = False

    def __bool__(self) -> bool:
        return self.accepted


_RETRYABLE_STATUSES: Final = frozenset({408, 429, 500, 502, 503, 504})
_HTTP_OK: Final = 200


def _blames_token(payload: dict[str, Any]) -> bool:
    """В ошибке FCM указано именно поле `token`?

    FCM возвращает `details[].field` вида "token" или
    "notification.title"; по нему единственно можно отличить сломанный нами
    payload от мёртвого токена устройства.
    """
    details = (payload.get("error") or {}).get("details") or []
    fields = {str(d.get("field", "")).lower() for d in details if isinstance(d, dict)}
    if not fields:
        # FCM не всегда присылает details. Признавать токен мёртвым без
        # доказательств опаснее, чем оставить его в работе: лишнее устройство
        # обойдётся одним лишним запросом, а тихо сожжённый токен — это
        # «уведомления перестали приходить» без диагностики.
        return False
    return any(f == "token" or f.endswith(".token") for f in fields)


@dataclass(frozen=True)
class ServiceAccount:
    """Ключи сервис-аккаунта, нужные для подписи access token."""

    project_id: str
    client_email: str
    private_key: str

    @classmethod
    def from_json(cls, raw: str) -> ServiceAccount:
        data = json.loads(raw)
        missing = [k for k in ("project_id", "client_email", "private_key") if not data.get(k)]
        if missing:
            raise ValueError(
                f"В service account нет обязательных полей {missing}. "
                "Проверь, что в base64 лежит именно JSON ключа, а не сам ключ."
            )
        return cls(
            project_id=data["project_id"],
            client_email=data["client_email"],
            private_key=data["private_key"],
        )

    @classmethod
    def load(cls, credentials_base64: str | None, credentials_file: str | None) -> ServiceAccount:
        """Прочитать ключ из base64 или из файла.

        Сначала base64: в .env это единственный нормальный способ положить
        многострочный приватный ключ, файл в контейнере — лишний объём.
        """
        if credentials_base64:
            return cls.from_json(base64.b64decode(credentials_base64).decode("utf-8"))
        if credentials_file:
            return cls.from_json(Path(credentials_file).read_text(encoding="utf-8"))
        raise ValueError(
            "Не заданы FIREBASE_CREDENTIALS_BASE64 или FIREBASE_CREDENTIALS_FILE. "
            "Положи service account в .env, чтобы включить push."
        )


class FcmClient:
    """Асинхронная отправка одиночных сообщений в FCM HTTP v1."""

    def __init__(
        self,
        account: ServiceAccount,
        *,
        client: httpx.AsyncClient | None = None,
        project_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._account = account
        # Явный project_id в настройках перекрывает ключ: нужно, когда ключ
        # лежит отдельно от проекта, с которым работает приложение.
        self._project_id = project_id or account.project_id
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._access_token: str | None = None
        self._access_token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _token(self) -> str:
        """Access token, при необходимости обновлённый.

        Блокировка нужна при первом обращении: воркер шлёт пачку сообщений
        конкурентно, и без неё все задачи разом подписывают свой токен.
        """
        now = time.time()
        if self._access_token and now < self._access_token_expires_at - _TOKEN_REFRESH_MARGIN:
            return self._access_token

        async with self._token_lock:
            # Пока ждали блокировку, токен мог обновить другой task.
            now = time.time()
            if self._access_token and now < self._access_token_expires_at - _TOKEN_REFRESH_MARGIN:
                return self._access_token

            assertion = {
                "iss": self._account.client_email,
                "scope": _SCOPE,
                "iat": int(now),
                "exp": int(now) + _TOKEN_TTL_SECONDS,
            }
            encoded = jwt.encode(assertion, self._account.private_key, algorithm="RS256")

            response = await self._client.post(
                "https://oauth2.googleapis.com/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": encoded},
            )
            response.raise_for_status()
            body = response.json()
            self._access_token = body["access_token"]
            # expires_in приходит в секундах; минус запас сверху уже учтён в
            # проверке выше, но и в поле кладём реальный срок, иначе токен
            # будет считаться валидным после истечения.
            self._access_token_expires_at = now + float(body.get("expires_in", _TOKEN_TTL_SECONDS))
            return self._access_token

    async def send(self, message: dict[str, Any]) -> SendResult:
        """Отправить одно сообщение. Никогда не бросает на ошибках FCM."""
        try:
            access_token = await self._token()
        except Exception as exc:
            # Не получилось авторизоваться — это проблема конфигурации, а не
            # токена устройства: повтором не лечится, но и outbox не должен
            # залипать в бесконечных попытках.
            logger.error(f"FCM: не удалось получить access token: {exc}")
            return SendResult(accepted=False, error=f"auth: {exc}", retryable=False)

        url = f"https://fcm.googleapis.com/v1/projects/{self._project_id}/messages:send"
        try:
            response = await self._client.post(
                url,
                json=message,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            # Сеть или таймаут: единственный класс ошибок, где повтор честно
            # помогает.
            logger.warning(f"FCM: сетевая ошибка отправки: {exc}")
            return SendResult(accepted=False, error=str(exc), retryable=True)

        if response.status_code == _HTTP_OK:
            return SendResult(accepted=True)

        return self._classify(response)

    def _classify(self, response: httpx.Response) -> SendResult:
        """Разобрать ошибочный ответ FCM.

        Различение важно для двух вещей: `UNREGISTERED` и `INVALID_ARGUMENT`
            требуют деактивации токена (иначе воркер долбится в мёртвый токен
            и сам себе устраивает thundering herd), а 5xx — повтора.
        """
        if response.status_code in _RETRYABLE_STATUSES:
            return SendResult(
                accepted=False,
                error=f"HTTP {response.status_code}",
                retryable=True,
            )

        reason = ""
        payload: dict[str, Any] = {}
        try:
            payload = response.json()
            detail = payload.get("error", {})
            # В FCM код ошибки лежит в status, человекочитаемое объяснение —
            # в message.
            reason = detail.get("status") or detail.get("message") or payload.get("error") or ""
        except (ValueError, AttributeError):
            reason = response.text[:200]

        # Токен объявляется мёртвым только когда FCM сказал про сам токен:
        # либо прямо (UNREGISTERED), либо через APNs-ошибку. INVALID_ARGUMENT
        # с полем не-token — это наш баг, и его видно в ошибке, а не в
        # деактивации чужого устройства.
        token_invalid = reason in {FcmError.UNREGISTERED, FcmError.PAYLOAD} or (
            reason == FcmError.INVALID and _blames_token(payload)
        )
        logger.warning(
            f"FCM: сообщение отклонено (HTTP {response.status_code}, {reason}), токен невалиден={token_invalid}"
        )
        return SendResult(accepted=False, error=f"{reason} (HTTP {response.status_code})", token_invalid=token_invalid)


def build_client(
    *,
    credentials_base64: str | None,
    credentials_file: str | None,
    project_id: str | None = None,
    timeout: float = 10.0,
) -> FcmClient:
    """Собрать клиента из настроек. Бросает, если ключа нет."""
    return FcmClient(
        ServiceAccount.load(credentials_base64, credentials_file),
        project_id=project_id,
        timeout=timeout,
    )
