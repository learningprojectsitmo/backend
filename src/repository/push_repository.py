from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, cast, select, update
from sqlalchemy.sql import func

from src.core.uow import IUnitOfWork
from src.model.notification import NotificationType
from src.model.push import (
    PUSH_OUTBOX_OPEN_STATUSES,
    PushOutbox,
    PushOutboxStatus,
    PushPlatform,
    PushSubscription,
)
from src.repository.base_repository import BaseRepository

#: После скольких неудачных попыток сообщение перестаёт мучить FCM. Пять
#: попыток с backoff — это около двух часов; к моменту, когда человек
#: вернётся к телефону, push всё равно не покажут задним числом.
MAX_ATTEMPTS = 5

#: Стартовая задержка перед первой повторной попыткой.
BACKOFF_BASE_SECONDS = 60
#: Потолок задержки: без него одна «упавшая» строка раз в сутки стучится в
#: FCM вечно.
BACKOFF_MAX_SECONDS = 3600


def retry_delay(attempts: int) -> timedelta:
    """Экспоненциальный backoff с потолком.

    `attempts` — число уже сделанных попыток, поэтому первая повторная
    отодвигается на BASE, а не на BASE*2.
    """
    seconds = min(BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), BACKOFF_MAX_SECONDS)
    return timedelta(seconds=seconds)


class PushOutboxRepository(BaseRepository[PushOutbox, int, dict]):
    """Работа с очередью доставки и с токенами устройств."""

    def __init__(self, uow: IUnitOfWork) -> None:
        super().__init__(uow)
        self._model = PushOutbox

    async def has_active_subscription(self, user_id: int) -> bool:
        """Есть ли у пользователя хоть одно живое устройство.

        Без этой проверки каждое уведомление в приложении, где push не
        настроен, оставляло бы в очереди строку, которую воркер обязан
        отправлять в никуда.
        """
        result = await self.uow.session.execute(
            select(func.count())
            .select_from(PushSubscription)
            .where(PushSubscription.user_id == user_id, PushSubscription.is_active.is_(True))
        )
        return bool((result.scalar() or 0) > 0)

    async def enqueue(
        self,
        *,
        user_id: int,
        notification_id: int,
        type: NotificationType,
        payload: dict,
    ) -> PushOutbox | None:
        """Положить сообщение в очередь.

        Вызывается в той же транзакции, что и создание уведомления: откат
        бизнес-операции откатывает и push. Возвращает `None`, если у
        пользователя нет активных устройств.
        """
        if not await self.has_active_subscription(user_id):
            return None

        row = PushOutbox(
            user_id=user_id,
            notification_id=notification_id,
            type=type,
            payload=payload,
            status=PushOutboxStatus.pending,
        )
        self.uow.session.add(row)
        await self.uow.session.flush()
        return row

    async def active_tokens(self, user_id: int) -> list[str]:
        result = await self.uow.session.execute(
            select(PushSubscription.token).where(
                PushSubscription.user_id == user_id,
                PushSubscription.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def claim_batch(self, limit: int, now: datetime | None = None) -> list[PushOutbox]:
        """Взять батч в работу, заблокировав строки от других воркеров.

        `FOR UPDATE SKIP LOCKED` — то, что позволяет запустить воркер в
        нескольких процессах: каждый заберёт свой батч, а не заблокируется
        и не продублирует отправку.
        """
        moment = now or datetime.now(tz=None)
        query = (
            select(PushOutbox)
            .where(
                PushOutbox.status.in_(PUSH_OUTBOX_OPEN_STATUSES),
                PushOutbox.available_at <= moment,
                PushOutbox.attempts < MAX_ATTEMPTS,
            )
            .order_by(PushOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = list((await self.uow.session.execute(query)).scalars().all())
        if not rows:
            return []

        # Сразу помечаем строки как взятые: если воркер умрёт до записи
        # результата, их вернёт requeue_stale.
        for row in rows:
            row.status = PushOutboxStatus.sending
            row.attempts += 1
        await self.uow.session.flush()
        return rows

    async def mark_sent(self, row: PushOutbox, now: datetime | None = None) -> None:
        row.status = PushOutboxStatus.sent
        row.sent_at = now or datetime.now(tz=None)
        row.last_error = None
        await self.uow.session.flush()

    async def mark_failed(self, row: PushOutbox, error: str, *, permanent: bool = False) -> bool:
        """Записать неудачу. `True` — строка ещё может уйти повторно.

        `permanent=True` для ошибок, которые повтором не лечатся: наш сломанный
        payload, отказ FCM по формату сообщения. Такую строку не откладываем
        заново — иначе она будет возвращаться в батч и портить статистику
        отправок, пока не исчерпает все попытки впустую.

        Неудачные попытки не удаляем: иначе при повреждённом payload строка
        гонялась бы по кругу вечно. Дойдя до MAX_ATTEMPTS, она замирает в
        failed, а алерт по метрике подскажет, что пора разбираться.
        """
        row.status = PushOutboxStatus.failed
        row.last_error = error[:1000]
        if permanent:
            # Повтор не поможет, поэтому исчерпываем попытки сразу. Иначе строка
            # снова попадала бы в батч (failed — открытый статус), воркер
            # брал бы её, отдавал бы FCM тот же невалидный payload и так до
            # бесконечности. attempts — единственный признак терминальности,
            # отдельного статуса в схеме нет.
            row.attempts = MAX_ATTEMPTS
            return False
        if row.attempts < MAX_ATTEMPTS:
            row.available_at = datetime.now(tz=None) + retry_delay(row.attempts)
            return True
        return False

    async def requeue_stale(self, older_than: timedelta) -> int:
        """Вернуть в очередь всё, что зависло в `sending`.

        Нужно на старте воркера: строка переходит в sending в своей
        транзакции, и если процесс упал до записи результата, она больше
        никто не разберётся — без этого перезапуска доставка встала бы
        навсегда.
        """
        cutoff = datetime.now(tz=None) - older_than
        result = await self.uow.session.execute(
            update(PushOutbox)
            .where(PushOutbox.status == PushOutboxStatus.sending, PushOutbox.created_at < cutoff)
            .values(
                # Вернуть в pending можно только то, что ещё имеет право на
                # попытку. Исчерпанное возвращать в pending бессмысленно —
                # его уже не заберет ни один батч, и строка навсегда осталась
                # бы висеть в очереди, обманывая и счётчик, и алерт.
                status=case(
                    (
                        PushOutbox.attempts < MAX_ATTEMPTS,
                        cast(PushOutboxStatus.pending, PushOutbox.status.type),
                    ),
                    else_=cast(PushOutboxStatus.failed, PushOutbox.status.type),
                ),
                available_at=cutoff,
            )
        )
        return int(result.rowcount or 0)

    async def owns_token(self, user_id: int, token: str) -> bool:
        """Токен принадлежит этому пользователю.

        Отдельный метод, а не `deactivate_token`, потому что токен уникален
        глобально: гасить чужой токен по одному совпадению строки нельзя, и
        проверка должна идти по паре (владелец, токен).
        """
        result = await self.uow.session.execute(
            select(func.count())
            .select_from(PushSubscription)
            .where(PushSubscription.user_id == user_id, PushSubscription.token == token)
        )
        return bool((result.scalar() or 0) > 0)

    async def deactivate_token(self, token: str) -> bool:
        """Погасить токен, который FCM посчитал несуществующим.

        Само по себе это ещё не повод отказываться от сообщения: у
        пользователя может быть другое устройство. Поэтому статус строки
        выбирает воркер, а репозиторий только гасит токен.
        """
        result = await self.uow.session.execute(
            update(PushSubscription)
            .where(PushSubscription.token == token, PushSubscription.is_active.is_(True))
            .values(is_active=False)
        )
        return bool(result.rowcount)

    async def delete_tokens_of_user(self, user_id: int) -> int:
        """Убрать все устройства пользователя — например, при выходе из аккаунта."""
        result = await self.uow.session.execute(
            update(PushSubscription).where(PushSubscription.user_id == user_id).values(is_active=False)
        )
        return int(result.rowcount or 0)

    async def upsert_subscription(
        self,
        *,
        user_id: int,
        token: str,
        platform: PushPlatform,
        device_id: str | None = None,
        app_version: str | None = None,
    ) -> PushSubscription:
        """Зарегистрировать устройство.

        Клиент шлёт токен при каждом запуске, поэтому повторная регистрация
        того же устройства — норма, а не ошибка. Токен уникален глобально:
        если он уже был записан на другого пользователя (например, при
        входе в общий телефон), запись переезжает на текущего.
        """
        existing = (
            await self.uow.session.execute(
                select(PushSubscription).where(PushSubscription.token == token).with_for_update()
            )
        ).scalar_one_or_none()

        if existing is None:
            row = PushSubscription(
                user_id=user_id,
                token=token,
                platform=platform,
                device_id=device_id,
                app_version=app_version,
                is_active=True,
            )
            self.uow.session.add(row)
        else:
            row = existing
            row.user_id = user_id
            row.platform = platform
            row.device_id = device_id
            row.app_version = app_version
            # Главное при повторной регистрации: возвращаем токен в работу.
            # FCM выдаёт новый токен после переустановки приложения, и без
            # этого реактивации уведомления молча пропадали бы навсегда.
            row.is_active = True
        await self.uow.session.flush()
        # last_seen_at и created_at заполняет сама БД (server_default), и после
        # INSERT SQLAlchemy считает их непрочитанными. Слой схем читает их из
        # ORM-объекта уже вне awaits, а ленивая догрузка в async-сессии падает
        # с MissingGreenlet. Refresh делает значения доступными сразу — в том
        # числе если upsert ничего не менял и сервер не вернул бы строку.
        await self.uow.session.refresh(row)
        return row

    async def count_pending(self) -> int:
        """Сколько сообщений ждёт отправки — для метрик и алертов."""
        result = await self.uow.session.execute(
            select(func.count())
            .select_from(PushOutbox)
            .where(
                PushOutbox.status.in_(PUSH_OUTBOX_OPEN_STATUSES),
                PushOutbox.attempts < MAX_ATTEMPTS,
            )
        )
        return int(result.scalar() or 0)
