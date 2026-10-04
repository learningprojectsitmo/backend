"""Юнит-тесты воркера доставки.

БД нет: подменяется `SqlAlchemyUoW`, а проверяется логика разбора батча,
подстановки токена, реакции на ошибки и гашения мёртвых токенов.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.model.push import PushOutboxStatus
from src.services.push_client import SendResult
from src.services.push_payload import PushPayload
from src.services.push_worker import PushWorker, _age_seconds, _payload_from_row, build_worker


def _row(**overrides) -> Mock:
    payload = {
        "title": "Новый отклик",
        "body": "Анна откликнулась",
        "route": "/app/projects/3",
        "channel_id": "responses",
        "high_priority": True,
        "collapse_key": "7:response_received",
        "data": {"type": "response_received"},
    }
    defaults = {
        "id": 1,
        "user_id": 7,
        "payload": payload,
        # naive, как и отдаёт asyncpg для timestamptz
        "created_at": datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None),
    }
    return Mock(**defaults | overrides)


def _repo(*, tokens: list[str] | None = None) -> Mock:
    repo = Mock()
    repo.claim_batch = AsyncMock(return_value=[])
    repo.active_tokens = AsyncMock(return_value=tokens if tokens is not None else ["t1"])
    repo.mark_sent = AsyncMock()
    repo.mark_failed = AsyncMock(return_value=True)
    repo.deactivate_token = AsyncMock(return_value=True)
    repo.requeue_stale = AsyncMock(return_value=0)
    repo.count_pending = AsyncMock(return_value=0)
    return repo


def _worker(client: Mock | None = None, repo: Mock | None = None) -> PushWorker:
    client = client or Mock()
    client.send = AsyncMock(return_value=SendResult(accepted=True))
    client.aclose = AsyncMock()
    worker = PushWorker(client, poll_seconds=0.01, batch_size=50)
    worker._test_repo = repo or _repo()
    return worker


class TestPayloadFromRow:
    def test_should_restore_message(self):
        # given
        row = _row()

        # when
        payload = _payload_from_row(row)

        # then
        assert isinstance(payload, PushPayload)
        assert payload.title == "Новый отклик"
        assert payload.route == "/app/projects/3"
        assert payload.high_priority is True

    def test_should_tolerate_missing_data(self):
        # given — старая строка очереди без data
        row = _row()
        del row.payload["data"]

        # when / then
        assert _payload_from_row(row).data == {}

    @pytest.mark.asyncio
    async def test_should_build_message_per_token(self):
        # given
        payload = _payload_from_row(_row())

        # when
        a = payload.to_fcm_message("token-a")
        b = payload.to_fcm_message("token-b")

        # then — одно сообщение обслуживает все устройства пользователя
        assert a["message"]["token"] == "token-a"
        assert b["message"]["token"] == "token-b"
        assert a["message"]["data"] == b["message"]["data"]


class TestQueueAge:
    def test_should_measure_age(self):
        # given
        created = datetime.now(tz=UTC) - timedelta(seconds=90)

        # when
        age = _age_seconds(created)

        # then
        assert 85 <= age <= 95

    def test_should_handle_naive_datetime(self):
        # given — asyncpg отдаёт timestamptz без таймзоны, и наивное значение
        # нельзя вычитать из aware: иначе TypeError в самом воркере
        naive = datetime.now(tz=UTC).replace(tzinfo=None) - timedelta(seconds=30)

        # when
        age = _age_seconds(naive)

        # then
        assert 25 <= age <= 35

    def test_should_not_return_negative(self):
        # given — часы на сервере могут спешить
        future = datetime.now(tz=UTC) + timedelta(minutes=5)

        # when / then
        assert _age_seconds(future) == 0.0


class TestDeliver:
    @pytest.mark.asyncio
    async def test_should_send_to_every_device(self):
        # given
        client = Mock()
        client.send = AsyncMock(return_value=SendResult(accepted=True))
        worker = PushWorker(client, poll_seconds=0.01)
        repo = _repo(tokens=["t1", "t2"])

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            await worker._deliver(_row())

        # then
        assert client.send.await_count == 2
        repo.mark_sent.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_mark_sent_when_all_devices_accepted(self):
        # given
        worker = _worker()
        repo = worker._test_repo

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            await worker._deliver(_row())

        # then
        repo.mark_sent.assert_awaited_once()
        repo.mark_failed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_deactivate_unregistered_token(self):
        # given — FCM сообщил, что токена больше нет
        client = Mock()
        client.send = AsyncMock(return_value=SendResult(accepted=False, error="UNREGISTERED", token_invalid=True))
        worker = PushWorker(client, poll_seconds=0.01)
        repo = _repo(tokens=["dead", "alive"])
        client.send = AsyncMock(
            side_effect=[
                SendResult(accepted=False, error="UNREGISTERED", token_invalid=True),
                SendResult(accepted=True),
            ]
        )

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            await worker._deliver(_row())

        # then — мёртвый токен гасим, но доставку засчитываем: у человека
        # есть другое устройство, и уведомление он получил
        repo.deactivate_token.assert_awaited_once_with("dead")
        repo.mark_sent.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_retry_on_transient_error(self):
        # given
        client = Mock()
        worker = PushWorker(client, poll_seconds=0.01)
        repo = _repo(tokens=["t1"])
        client.send = AsyncMock(return_value=SendResult(accepted=False, error="UNAVAILABLE", retryable=True))

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            await worker._deliver(_row())

        # then
        repo.mark_failed.assert_awaited_once()
        repo.mark_sent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_fail_permanently_on_our_payload_bug(self):
        # given — FCM отверг сообщение, и это не мёртвый токен, а наша ошибка
        client = Mock()
        worker = PushWorker(client, poll_seconds=0.01)
        repo = _repo(tokens=["t1"])
        client.send = AsyncMock(return_value=SendResult(accepted=False, error="INVALID_ARGUMENT", token_invalid=False))

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            await worker._deliver(_row())

        # then — permanent=True, иначе сломанный payload вернётся в батч
        repo.mark_failed.assert_awaited_once()
        assert repo.mark_failed.await_args.kwargs == {"permanent": True}
        repo.mark_sent.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_not_deactivate_token_on_our_payload_bug(self):
        # given — иначе наша ошибка тихо сожжёт устройства пользователей
        client = Mock()
        worker = PushWorker(client, poll_seconds=0.01)
        repo = _repo(tokens=["t1"])
        client.send = AsyncMock(return_value=SendResult(accepted=False, error="INVALID_ARGUMENT", token_invalid=False))

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            await worker._deliver(_row())

        # then
        repo.deactivate_token.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_mark_sent_when_every_token_was_dead(self):
        # given — отправлять больше некому, повтор не поможет
        client = Mock()
        worker = PushWorker(client, poll_seconds=0.01)
        repo = _repo(tokens=["dead"])
        client.send = AsyncMock(return_value=SendResult(accepted=False, error="UNREGISTERED", token_invalid=True))

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            await worker._deliver(_row())

        # then
        repo.deactivate_token.assert_awaited_once_with("dead")
        repo.mark_sent.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_should_mark_sent_when_no_devices_left(self):
        # given — устройства сняли между постановкой в очередь и отправкой
        client = Mock()
        client.send = AsyncMock(return_value=SendResult(accepted=True))
        worker = PushWorker(client, poll_seconds=0.01)
        repo = _repo(tokens=[])

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            await worker._deliver(_row())

        # then — отправлять некому, но это не ошибка доставки
        client.send.assert_not_awaited()
        repo.mark_sent.assert_awaited_once()
        repo.mark_failed.assert_not_awaited()


class TestRunOnce:
    @pytest.mark.asyncio
    async def test_should_return_zero_on_empty_queue(self):
        # given
        worker = _worker()
        repo = worker._test_repo

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            processed = await worker.run_once()

        # then
        assert processed == 0

    @pytest.mark.asyncio
    async def test_should_count_claimed_rows(self):
        # given
        worker = _worker()
        repo = worker._test_repo
        repo.claim_batch = AsyncMock(return_value=[_row(), _row(id=2)])
        client = worker._client
        client.send = AsyncMock(return_value=SendResult(accepted=True))

        # when
        with patch("src.services.push_worker.PushOutboxRepository", return_value=repo):
            processed = await worker.run_once()

        # then
        assert processed == 2
        assert repo.claim_batch.await_args.args[0] == 50


class TestBuildWorker:
    def test_should_return_none_when_disabled(self):
        # given / when / then — без ключа приложение обязано подняться
        with patch("src.services.push_worker.settings") as fake:
            fake.PUSH_ENABLED = False
            assert build_worker() is None

    def test_should_return_none_without_credentials(self):
        # given — push включён, но ключа нет
        with patch("src.services.push_worker.settings") as fake:
            fake.PUSH_ENABLED = True
            fake.PUSH_WORKER_ENABLED = True
            fake.FIREBASE_CREDENTIALS_BASE64 = None
            fake.FIREBASE_CREDENTIALS_FILE = None
            fake.FIREBASE_PROJECT_ID = None
            fake.FCM_TIMEOUT_SECONDS = 10.0
            assert build_worker() is None


class TestStatusHelpers:
    def test_should_have_terminal_and_open_states(self):
        # given / when / then
        assert PushOutboxStatus.sent != PushOutboxStatus.failed
        assert PushOutboxStatus.pending.value == "pending"
