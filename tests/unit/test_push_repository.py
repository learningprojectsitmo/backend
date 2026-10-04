"""Юнит-тесты очереди доставки и хука в NotificationService.

БД здесь нет: сессия — заглушка, а проверяется то, что реально ломается —
SQL-фильтры, backoff и то, что outbox пишется только при живом устройстве.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import Select, Update
from sqlalchemy.dialects import postgresql

from src.model.notification import NotificationType
from src.model.push import PushOutboxStatus, PushPlatform, PushSubscription
from src.repository.push_repository import (
    BACKOFF_MAX_SECONDS,
    MAX_ATTEMPTS,
    PushOutboxRepository,
    retry_delay,
)
from src.services.notification_service import NotificationService


def _result(
    *,
    scalar: int | None = 0,
    scalars: list | None = None,
    one: object = None,
) -> Mock:
    result = Mock()
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = scalars if scalars is not None else []
    result.scalar_one_or_none.return_value = one
    result.rowcount = scalar or 0
    return result


def _repository(*results: Mock) -> tuple[PushOutboxRepository, AsyncMock, Mock]:
    uow = Mock()
    uow.session = Mock()
    uow.session.execute = AsyncMock(side_effect=list(results) if results else [_result()])
    uow.session.flush = AsyncMock()
    uow.session.add = Mock()
    uow.session.refresh = AsyncMock()
    return PushOutboxRepository(uow), uow.session.execute, uow.session


def _sql(call_args: tuple) -> str:
    query: Select | Update = call_args[0]
    return str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestRetryDelay:
    def test_should_grow_exponentially(self):
        # given / when / then
        assert retry_delay(1) == timedelta(seconds=60)
        assert retry_delay(2) == timedelta(seconds=120)
        assert retry_delay(3) == timedelta(seconds=240)

    def test_should_cap_at_max(self):
        # given — без потолка строка стучалась бы в FCM раз в неделю вечно
        assert retry_delay(30) == timedelta(seconds=BACKOFF_MAX_SECONDS)

    def test_should_not_go_backwards(self):
        # given / when / then
        assert retry_delay(0) == retry_delay(1)


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_should_skip_user_without_devices(self):
        # given — у пользователя нет ни одного активного токена
        repo, _execute, session = _repository(_result(scalar=0))

        # when
        row = await repo.enqueue(
            user_id=1,
            notification_id=2,
            type=NotificationType.response_received,
            payload={"title": "t"},
        )

        # then — пустая очередь лучше строки, которую воркер обязан отправлять в никуда
        assert row is None
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_add_row_for_subscribed_user(self):
        # given
        repo, _execute, session = _repository(_result(scalar=1))

        # when
        row = await repo.enqueue(
            user_id=1,
            notification_id=2,
            type=NotificationType.task_moved,
            payload={"title": "t"},
        )

        # then
        assert row is not None
        assert row.status == PushOutboxStatus.pending
        assert row.user_id == 1
        assert row.notification_id == 2
        assert session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_should_check_only_active_subscriptions(self):
        # given
        repo, execute, _session = _repository(_result(scalar=1))

        # when
        await repo.has_active_subscription(7)

        # then
        sql = _sql(execute.await_args_list[0].args)
        assert "is_active IS true" in sql
        assert "user_id = 7" in sql


class TestClaimBatch:
    @pytest.mark.asyncio
    async def test_should_return_empty_without_work(self):
        # given
        repo, _execute, _session = _repository(_result(scalars=[]))

        # when
        rows = await repo.claim_batch(50)

        # then
        assert rows == []

    @pytest.mark.asyncio
    async def test_should_lock_rows_skip_locked(self):
        # given
        repo, execute, _session = _repository(_result(scalars=[]))

        # when
        await repo.claim_batch(50)

        # then — иначе два воркера заблокируют друг друга или продублируют отправку
        sql = _sql(execute.await_args_list[0].args)
        assert "SKIP LOCKED" in sql
        assert "LIMIT 50" in sql

    @pytest.mark.asyncio
    async def test_should_only_take_retryable_rows(self):
        # given
        repo, execute, _session = _repository(_result(scalars=[]))

        # when
        await repo.claim_batch(10)

        # then — сравниваем значения перечисления, а не подстроку: иначе
        # проверка ловит колонку sent_at и всегда падает
        sql = _sql(execute.await_args_list[0].args)
        assert "status IN ('pending', 'failed')" in sql
        assert "'sent'" not in sql

    @pytest.mark.asyncio
    async def test_should_skip_exhausted_rows(self):
        # given
        repo, execute, _session = _repository(_result(scalars=[]))

        # when
        await repo.claim_batch(10)

        # then — failed остаётся открытым статусом (в нём же ждут повторы),
        # поэтому единственный признак «больше не пробовать» — attempts.
        # Без этого фильтра исчерпанные и permanent-строки воркер забирал бы
        # бесконечно и заваливал бы логи и метрику failed_permanent.
        sql = _sql(execute.await_args_list[0].args)
        assert f"attempts < {MAX_ATTEMPTS}" in sql


class TestFailure:
    @pytest.mark.asyncio
    async def test_should_reschedule_before_limit(self):
        # given
        repo, _execute, _session = _repository()
        row = Mock(attempts=1, available_at=None, status=None, last_error=None)

        # when
        will_retry = await repo.mark_failed(row, "UNAVAILABLE")

        # then
        assert will_retry is True
        assert row.status == PushOutboxStatus.failed
        assert row.last_error == "UNAVAILABLE"
        assert row.available_at is not None

    @pytest.mark.asyncio
    async def test_should_exhaust_attempts_on_permanent_error(self):
        # given
        repo, _execute, _session = _repository()
        row = Mock(attempts=1, available_at=None, status=None, last_error=None)

        # when
        will_retry = await repo.mark_failed(row, "INVALID_ARGUMENT", permanent=True)

        # then — повтор тут не поможет, поэтому строка обязана перестать
        # попадать в батч, а не ждать MAX_ATTEMPTS заведомо бесполезных
        # попыток и портить статистику отправок
        assert will_retry is False
        assert row.attempts == MAX_ATTEMPTS
        assert row.available_at is None

    @pytest.mark.asyncio
    async def test_should_stop_at_attempt_limit(self):
        # given — иначе повреждённый payload гонялся бы по кругу вечно
        repo, _execute, _session = _repository()
        row = Mock(attempts=MAX_ATTEMPTS, available_at=None, status=None, last_error=None)

        # when
        will_retry = await repo.mark_failed(row, "INVALID_ARGUMENT")

        # then
        assert will_retry is False

    @pytest.mark.asyncio
    async def test_should_truncate_long_error(self):
        # given
        repo, _execute, _session = _repository()
        row = Mock(attempts=1, available_at=None, status=None, last_error=None)

        # when
        await repo.mark_failed(row, "x" * 5000)

        # then
        assert len(row.last_error) <= 1000


class TestRequeueStale:
    @pytest.mark.asyncio
    async def test_should_only_release_sending(self):
        # given
        repo, execute, _session = _repository(_result(scalar=2))

        # when
        released = await repo.requeue_stale(timedelta(minutes=10))

        # then — без этого перезапуска доставка встала бы навсегда
        assert released == 2
        sql = _sql(execute.await_args_list[0].args)
        assert "status = 'sending'" in sql
        assert "pending" in sql

    @pytest.mark.asyncio
    async def test_should_not_revive_exhausted_rows(self):
        # given
        repo, execute, _session = _repository(_result(scalar=1))

        # when
        await repo.requeue_stale(timedelta(minutes=10))

        # then — вернуть в pending строку, у которой попытки кончились,
        # бессмысленно: её не забьёт ни один батч, и она навсегда осталась бы
        # висеть в очереди, обманывая и счётчик, и алерт на застой
        sql = _sql(execute.await_args_list[0].args)
        assert "CASE" in sql
        assert f"attempts < {MAX_ATTEMPTS}" in sql


class TestCountPending:
    @pytest.mark.asyncio
    async def test_should_count_only_actionable_work(self):
        # given
        repo, execute, _session = _repository(_result(scalar=7))

        # when
        pending = await repo.count_pending()

        # then — иначе метрика пустой очереди росла бы от мёртвых строк
        assert pending == 7
        sql = _sql(execute.await_args_list[0].args)
        assert f"attempts < {MAX_ATTEMPTS}" in sql


class TestSubscriptions:
    @pytest.mark.asyncio
    async def test_should_reactivate_existing_token(self):
        # given — после переустановки приложения FCM выдаёт новый токен, и без
        # реактивации уведомления молча пропадали бы навсегда
        existing = Mock(is_active=False, user_id=99, platform=PushPlatform.android)
        repo, _execute, session = _repository(_result(one=existing))

        # when
        row = await repo.upsert_subscription(
            user_id=1,
            token="t",
            platform=PushPlatform.ios,
            app_version="1.2.3",
        )

        # then
        assert row.is_active is True
        assert row.user_id == 1
        assert row.platform == PushPlatform.ios
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_insert_unknown_token(self):
        # given
        repo, _execute, session = _repository(_result(scalars=[]))

        # when
        row = await repo.upsert_subscription(
            user_id=1,
            token="t",
            platform=PushPlatform.android,
        )

        # then
        assert row.token == "t"
        assert session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_should_refresh_row_before_returning_it(self):
        # given
        repo, _execute, session = _repository(_result(one=None))
        # when
        await repo.upsert_subscription(user_id=1, token="tok", platform=PushPlatform.android)

        # then — last_seen_at и created_at заполняет сама БД, и после INSERT
        # SQLAlchemy считает их непрочитанными. Слой схем читает их из
        # ORM-объекта уже вне awaits, а ленивая догрузка в async-сессии падает
        # с MissingGreenlet. Refresh — обязателен, а не оптимизация.
        assert session.refresh.await_count == 1
        refreshed = session.refresh.await_args.args[0]
        assert isinstance(refreshed, PushSubscription)

    @pytest.mark.asyncio
    async def test_should_lock_row_on_reregistration(self):
        # given — два устройства шлют один токен, гонки быть не должно
        repo, execute, _session = _repository(_result(scalars=[]))

        # when
        await repo.upsert_subscription(user_id=1, token="t", platform=PushPlatform.android)

        # then
        sql = _sql(execute.await_args_list[0].args)
        assert "FOR UPDATE" in sql

    @pytest.mark.asyncio
    async def test_should_deactivate_token(self):
        # given
        repo, execute, _session = _repository(_result(scalar=1))

        # when
        ok = await repo.deactivate_token("dead")

        # then
        assert ok is True
        sql = _sql(execute.await_args_list[0].args)
        assert "is_active IS true" in sql
        assert "is_active=false" in sql


class TestNotificationServiceHook:
    def _service(self, push: Mock | None) -> NotificationService:
        notifications = Mock()
        notifications.create_notification = AsyncMock(return_value=Mock(id=99))
        return NotificationService(notifications, push)

    @pytest.mark.asyncio
    async def test_should_enqueue_with_rendered_payload(self):
        # given
        push = Mock()
        push.enqueue = AsyncMock()
        service = self._service(push)

        # when
        await service.create_notification(
            7,
            NotificationType.response_received,
            actor_name="Анна",
            project_id=3,
            project_name="Проект",
        )

        # then
        assert push.enqueue.await_count == 1
        kwargs = push.enqueue.await_args.kwargs
        assert kwargs["user_id"] == 7
        assert kwargs["notification_id"] == 99
        assert kwargs["type"] == NotificationType.response_received
        assert kwargs["payload"]["route"] == "/app/projects/3"
        assert kwargs["payload"]["title"] == "Новый отклик"

    @pytest.mark.asyncio
    async def test_should_not_store_token_in_payload(self):
        # given — токен подставляется в момент отправки, иначе смена
        # устройства ломала бы очередь
        push = Mock()
        push.enqueue = AsyncMock()
        service = self._service(push)

        # when
        await service.create_notification(
            7,
            NotificationType.task_moved,
            actor_name="Анна",
            project_id=3,
            project_name="Проект",
            task_title="Дизайн",
            column_name="Готово",
        )

        # then
        payload = push.enqueue.await_args.kwargs["payload"]
        assert "token" not in payload
        assert "token" not in payload["data"]

    @pytest.mark.asyncio
    async def test_should_survive_push_failure(self):
        # given — из-за FCM не должен падать отклик на проект
        push = Mock()
        push.enqueue = AsyncMock(side_effect=RuntimeError("db gone"))
        service = self._service(push)

        # when
        notification = await service.create_notification(
            7,
            NotificationType.response_received,
            actor_name="Анна",
            project_id=3,
            project_name="Проект",
        )

        # then
        assert notification.id == 99

    @pytest.mark.asyncio
    async def test_should_work_without_push_repository(self):
        # given — push выключен, репозиторий не подключён
        service = self._service(None)

        # when
        notification = await service.create_notification(
            7,
            NotificationType.response_received,
            actor_name="Анна",
            project_id=3,
            project_name="Проект",
        )

        # then
        assert notification.id == 99

    @pytest.mark.asyncio
    async def test_should_cover_every_type(self):
        # given — новый тип уведомления не должен молча ломать create_notification
        push = Mock()
        push.enqueue = AsyncMock()
        service = self._service(push)

        # when
        for type in NotificationType:
            await service.create_notification(7, type, actor_name="Анна", project_id=3, project_name="Проект")

        # then
        assert push.enqueue.await_count == len(NotificationType)
