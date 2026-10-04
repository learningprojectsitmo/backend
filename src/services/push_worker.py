"""Воркер доставки push из outbox.

Работает в фоне того же процесса, что и API, но держит свои транзакции и
не блокирует event loop: весь I/O асинхронный.

Почему воркер, а не `asyncio.create_task` прямо в `create_notification`:
fire-and-forget теряет уведомление при рестарте процесса и отправляет push
об откатившейся операции. Outbox решает обе проблемы — строка очереди живёт
в базе и создаётся в той же транзакции, что и уведомление.

Про `sending`: строка переходит в это состояние в своей транзакции, и если
процесс умрёт до записи результата, её больше никто не разберётся. Поэтому
на старте воркер возвращает зависшие строки в очередь — `requeue_stale`.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from loguru import logger

from src.core.config import settings
from src.core.metrics import (
    PUSH_FAILURES_TOTAL,
    PUSH_QUEUE_DEPTH,
    PUSH_QUEUED,
    PUSH_SENT_TOTAL,
    PUSH_TOKENS_DEACTIVATED,
)
from src.core.uow import SqlAlchemyUoW
from src.repository.push_repository import PushOutboxRepository
from src.services.push_client import FcmClient, build_client
from src.services.push_payload import PushPayload

#: Сколько ждать перед возвратом в очередь строк, зависших в `sending`.
#: Больше длительности цикла опроса: строка переживает падение процесса,
#: но не переживает зависание на час.
STALE_SENDING = timedelta(minutes=5)


def _age_seconds(created_at) -> float:
    """Сколько сообщение пролежало в очереди.

    asyncpg отдаёт timestamptz с таймзоной, но naive-значения тоже
    встречаются — из моков в тестах и из кода, где сравнения идут с
    datetime.now(tz=None). Смешивать их нельзя, поэтому приводим к UTC
    явно: иначе наивное значение уехало бы на несуществующий час и в
    задержке доставки появилась бы ошибка на размер смещения.
    """
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return max((datetime.now(tz=UTC) - created_at).total_seconds(), 0.0)


def _payload_from_row(row) -> PushPayload:
    """Восстановить сообщение из JSON-колонки очереди.

    Токена в сохранённом payload нет (см. PushPayload), поэтому строка не
    привязана к устройству и годится для повторной отправки.
    """
    return PushPayload(
        title=row.payload["title"],
        body=row.payload["body"],
        route=row.payload["route"],
        channel_id=row.payload["channel_id"],
        high_priority=row.payload["high_priority"],
        collapse_key=row.payload["collapse_key"],
        data=row.payload.get("data") or {},
    )


class PushWorker:
    """Фоновый цикл: забрать батч, разослать, записать результат."""

    def __init__(
        self,
        client: FcmClient,
        *,
        poll_seconds: float | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._client = client
        self._poll = poll_seconds if poll_seconds is not None else settings.PUSH_WORKER_POLL_SECONDS
        self._batch = batch_size if batch_size is not None else settings.PUSH_WORKER_BATCH_SIZE
        self._task: asyncio.Task | None = None

    async def run_once(self) -> int:
        """Один проход по очереди. Возвращает число обработанных строк.

        Каждая строка батча обрабатывается в своей транзакции, поэтому
        падение на одном сообщении не откатывает уже отправленные соседние.
        """
        async with SqlAlchemyUoW() as uow:
            repo = PushOutboxRepository(uow)
            rows = await repo.claim_batch(self._batch)
            # Глубина очереди — главный признак, что воркер не справляется или
            # FCM лежит. Публикуем после чтения батча: значение и есть «сколько
            # работы ждёт».
            PUSH_QUEUED.set(await repo.count_pending())

        if not rows:
            return 0

        for row in rows:
            await self._deliver(row)
        return len(rows)

    async def _deliver(self, row) -> None:
        """Разослать одну строку по всем устройствам пользователя."""
        async with SqlAlchemyUoW() as uow:
            repo = PushOutboxRepository(uow)
            tokens = await repo.active_tokens(row.user_id)

        if not tokens:
            # Устройства сняли между постановкой в очередь и отправкой.
            # Помечаем отправленным, а не failed: сообщение не забыто, просто
            # отправлять его уже некому.
            async with SqlAlchemyUoW() as uow:
                await PushOutboxRepository(uow).mark_sent(row)
            return

        PUSH_SENT_TOTAL.inc()
        PUSH_QUEUE_DEPTH.observe(_age_seconds(row.created_at))

        payload = _payload_from_row(row)
        invalid_tokens: list[str] = []
        retryable_error: str | None = None
        fatal_error: str | None = None

        for token in tokens:
            result = await self._client.send(payload.to_fcm_message(token))
            if result.accepted:
                continue
            if result.token_invalid:
                invalid_tokens.append(token)
            elif result.retryable:
                # Сетевая ошибка или 5xx — попробуем ещё раз позже.
                retryable_error = retryable_error or result.error
            else:
                # Наш сломанный payload или формат, который FCM не принимает.
                # Повтор бесполезен, а молча считать это доставкой нельзя:
                # тогда баг в сборке сообщения жил бы незаметно.
                fatal_error = fatal_error or result.error

        async with SqlAlchemyUoW() as uow:
            repo = PushOutboxRepository(uow)
            PUSH_TOKENS_DEACTIVATED.inc(len(invalid_tokens))
            for token in invalid_tokens:
                # Токен мёртв: гасим, чтобы в следующий раз не тратить на него
                # запрос. На доставку это не влияет — остальные устройства
                # своё получили.
                await repo.deactivate_token(token)

            if fatal_error is not None:
                logger.error(f"PushWorker: сообщение {row.id} отклонено безвозвратно: {fatal_error}")
                PUSH_FAILURES_TOTAL.labels(reason="failed_permanent").inc()
                await repo.mark_failed(row, fatal_error, permanent=True)
            elif retryable_error is not None:
                PUSH_FAILURES_TOTAL.labels(reason="retry").inc()
                await repo.mark_failed(row, retryable_error)
            else:
                # Все токены либо приняты, либо погашены как мёртвые. Второй
                # случай — это тоже не повод для повтора: отправлять больше
                # некуда, сообщение просто некуда было доставить.
                await repo.mark_sent(row)

    async def _loop(self) -> None:
        try:
            released = await self._requeue_stale()
            if released:
                logger.info(f"PushWorker: вернул {released} зависших сообщений в очередь")
        except Exception as exc:
            # Старт воркера не должен ронять API: без доставки приложение
            # всё ещё работает, просто без push.
            logger.warning(f"PushWorker: не удалось разобрать зависшие сообщения: {exc}")

        while True:
            try:
                processed = await self.run_once()
                # Пустая очередь — спим полный интервал. Непустая
                # отрабатывается сразу, чтобы большой бэклог разослался
                # одним заходом, а не растянулся на часы.
                if processed == 0:
                    await asyncio.sleep(self._poll)
            except asyncio.CancelledError:
                logger.info("PushWorker: остановлен")
                raise
            except Exception as exc:
                logger.error(f"PushWorker: сбой прохода: {exc}")
                await asyncio.sleep(self._poll)

    async def _requeue_stale(self) -> int:
        async with SqlAlchemyUoW() as uow:
            return await PushOutboxRepository(uow).requeue_stale(STALE_SENDING)

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="push-worker")
        logger.info(f"PushWorker: запущен (poll={self._poll}с, batch={self._batch})")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None


def build_worker() -> PushWorker | None:
    """Собрать воркер, если push включён и ключ есть.

    `None` означает «push выключен» — это штатный режим: dev без Firebase и
    прод до настройки ключа. Бросать исключение здесь нельзя, иначе
    приложение не поднимется из-за второстепенной подсистемы.
    """
    if not settings.PUSH_ENABLED:
        logger.info("PushWorker: push выключен (PUSH_ENABLED=false)")
        return None

    try:
        client = build_client(
            credentials_base64=settings.FIREBASE_CREDENTIALS_BASE64,
            credentials_file=settings.FIREBASE_CREDENTIALS_FILE,
            project_id=settings.FIREBASE_PROJECT_ID,
            timeout=settings.FCM_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.error(f"PushWorker: push включён, но клиент не собрался: {exc}")
        return None

    if not settings.PUSH_WORKER_ENABLED:
        logger.info("PushWorker: воркер отключён (PUSH_WORKER_ENABLED=false)")
        return None

    return PushWorker(client)
