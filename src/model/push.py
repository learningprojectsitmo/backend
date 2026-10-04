from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, select, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base
from src.model.notification import NotificationType

if TYPE_CHECKING:
    from src.model.notification import Notification
    from src.model.user import User


class PushPlatform(enum.StrEnum):
    """Клиент, зарегистрировавший токен.

    `web` оставлен на будущее: браузер сейчас работает на polling, и FCM для
    него — это VAPID-ключ, а не тот же токен, что у нативного клиента.
    """

    android = "android"
    ios = "ios"
    web = "web"


class PushOutboxStatus(enum.StrEnum):
    """Состояние строки очереди доставки.

    `sending` нужен для переиспользования: если воркер упал между чтением батча
    и записью результата, строка навсегда осталась бы в `sending`. Поэтому
    воркер при старте переводит в `pending` всё, что висит дольше
    `PUSH_SENDING_STALE_SECONDS`.
    """

    pending = "pending"
    sending = "sending"
    sent = "sent"
    failed = "failed"


class PushSubscription(Base):
    """Регистрация токена FCM на конкретное устройство.

    Раньше токен лежал колонкой в `user.push_token`, но её не было ни в одной
    схеме — записать токен было нечем, колонка всегда оставалась NULL. Хранить
    по одному токену на пользователя тоже нельзя: у него может быть телефон и
    планшет, а после переустановки приложения FCM выдаёт новый токен вместо
    старого. Поэтому здесь одна строка на устройство, а уникальность по
    `token` превращает повторную регистрацию того же устройства в upsert.
    """

    __tablename__ = "push_subscription"

    # Выборка активных токенов пользователя при отправке — самый частый запрос.
    __table_args__ = (Index("ix_push_subscription_user_active", "user_id", "is_active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    # 512 с запасом: FCM registration token для Android — порядка 160 символов,
    # APNs — 64 hex, web — около 250. Документация Firebase допускает до 4 КБ,
    # но btree-индекс в Postgres не переваривает значение длиннее ~2700 байт,
    # поэтому 512 — это компромисс между запасом и работоспособностью UNIQUE.
    token: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    platform: Mapped[PushPlatform] = mapped_column(
        Enum(PushPlatform, name="push_platform_enum", create_constraint=True),
        nullable=False,
    )
    # Только для диагностики: "iPhone 15 Pro", "SM-S918B". На логику не влияет.
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", default=True)
    # Клиент шлёт токен при каждом запуске и при каждом refresh от FCM —
    # по нему видно, жив ли токен, не дожидаясь ответа от Firebase.
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="push_subscriptions")

    def __repr__(self) -> str:
        return f"PushSubscription(id={self.id!r}, user_id={self.user_id!r}, platform={self.platform!r}, is_active={self.is_active!r})"


class PushOutbox(Base):
    """Очередь доставки push.

    Строка пишется в той же транзакции, что и `notification`, поэтому откат
    бизнес-операции откатывает и push — уведомление об откатившемся действии
    уйти не может. Отправкой занимается отдельный воркер: сам запрос больше не
    ждёт сеть, а если воркер перезапустится, недоставленное просто останется в
    очереди.

    Отдельная таблица вместо `asyncio.create_task` внутри `create_notification`
    именно ради этого: fire-and-forget теряет уведомление при рестарте процесса
    и при откате транзакции.
    """

    __tablename__ = "push_outbox"

    __table_args__ = (
        # Выборка батча воркером: строки со статусом pending/failed, у которых
        # наступил available_at (после backoff). Частичный индекс — потому что
        # отправленные строки, которых в базе большинство, в выборку не попадают.
        Index(
            "ix_push_outbox_ready",
            "status",
            "available_at",
            postgresql_where=text("status IN ('pending', 'failed')"),
        ),
        # Уборка отправленного по возрасту.
        Index("ix_push_outbox_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notification.id"), nullable=False)
    type: Mapped[NotificationType] = mapped_column(
        # Тип уже создан таблицей notification, поэтому и CREATE TYPE, и второй
        # CHECK-констрейнт тут не нужны — иначе autogenerate увидит расхождение
        # и начнёт предлагать пересоздать тип.
        Enum(
            NotificationType,
            name="notification_type_enum",
            create_type=False,
            create_constraint=False,
        ),
        nullable=False,
    )
    # Готовое сообщение для FCM v1 целиком. Собирается в одной чистой функции
    # (push_payload.build_push), поэтому воркер ничего не знает про типы.
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[PushOutboxStatus] = mapped_column(
        Enum(PushOutboxStatus, name="push_outbox_status_enum", create_constraint=True),
        nullable=False,
        # server_default строкой, а не sa.text(...): enum-дефолт обязан быть
        # литералом 'pending', иначе Postgres получает DEFAULT pending.
        server_default="pending",
        default=PushOutboxStatus.pending,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="push_outbox")
    notification: Mapped[Notification] = relationship(back_populates="push_outbox")

    def __repr__(self) -> str:
        return f"PushOutbox(id={self.id!r}, user_id={self.user_id!r}, type={self.type!r}, status={self.status!r})"


#: Статусы, которые воркер готов взять в работу.
PUSH_OUTBOX_OPEN_STATUSES = (PushOutboxStatus.pending, PushOutboxStatus.failed)


def active_tokens_query(user_id: int):
    """Запрос активных токенов пользователя — используется репозиторием."""
    return select(PushSubscription.token).where(
        PushSubscription.user_id == user_id,
        PushSubscription.is_active.is_(True),
    )
