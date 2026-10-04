"""add push subscription and outbox

Revision ID: a1f2c3d4e5b6
Revises: b3f1c8a4e7d2
Create Date: 2026-10-04 12:00:00.000000

FCM-push для мобильного клиента.

Две таблицы с разными задачами:

* `push_subscription` — по строке на устройство. Раньше токен хранился колонкой
  `user.push_token`, но её не было ни в одной Pydantic-схеме, поэтому колонка
  всегда оставалась NULL и записать токен было нечем. Плюс одна колонка на
  пользователя не годится в принципе: у него может быть телефон и планшет, а
  после переустановки приложения FCM выдаёт новый токен вместо старого. Поэтому
  здесь несколько строк на пользователя, а уникальность по `token` превращает
  повторную регистрацию того же устройства (refresh токена при запуске) в upsert.

* `push_outbox` — очередь доставки. Строка пишется в той же транзакции, что и
  `notification`, поэтому откат бизнес-операции откатывает и push. Отправкой
  занимается отдельный воркер, так что запрос больше не ждёт сеть, а рестарт
  процесса не теряет недоставленное.

`push_outbox.type` переиспользует существующий `notification_type_enum` — новый
тип для него не создаётся, иначе в БС появился бы второй независимый enum с
тем же набором значений. Поэтому `create_constraint=False`: CHECK уже создаён
таблицей `notification`, второй такой же только конфликтует по имени.

Констрейнты безымянные — как во всей остальной схеме: у `Base.metadata` нет
naming_convention, и именованный констрейнт autogenerate не сопоставил бы с
безымянным `unique=True` в модели (проверяется `alembic check`).

Индексы на новых таблицах создаются обычным CREATE INDEX, а не
CONCURRENTLY: таблицы только что появились и пусты, блокировать нечего.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f2c3d4e5b6"
down_revision: str | Sequence[str] | None = "b3f1c8a4e7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PUSH_PLATFORM_ENUM = "push_platform_enum"
PUSH_OUTBOX_STATUS_ENUM = "push_outbox_status_enum"


def upgrade() -> None:
    """Upgrade schema."""
    # CREATE TYPE из create_table идёт без checkfirst, поэтому на повторном
    # прогоне (или на базе, где тип остался с прошлой неудачной попытки) падает
    # DuplicateObjectError. Сбрасываем типы перед созданием таблиц.
    sa.Enum(name=PUSH_PLATFORM_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=PUSH_OUTBOX_STATUS_ENUM).drop(op.get_bind(), checkfirst=True)

    # Колонка была мёртвой: push_token не входил ни в UserUpdate, ни в
    # UserCreate, ни в UserFull — записать токен было нечем, читать тоже
    # незачем. Данных в ней нет by construction.
    op.drop_column("user", "push_token")

    op.create_table(
        "push_subscription",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column(
            "platform",
            # Члены enum-а обязаны идти позиционными аргументами, а не через
            # values=(...): в SQLAlchemy 2.0 values= игнорируется, enums
            # остаётся пустым, и DDL получается `CREATE TYPE ... AS ENUM ()` —
            # пустой тип, на котором сразу падает даже DEFAULT в своей же
            # таблице. Явный список заодно замораживает историю миграции.
            sa.Enum(
                "android",
                "ios",
                "web",
                name=PUSH_PLATFORM_ENUM,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("device_id", sa.String(length=128), nullable=True),
        sa.Column("app_version", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_push_subscription_user_active", "push_subscription", ["user_id", "is_active"], unique=False)

    op.create_table(
        "push_outbox",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            # Существующий тип из таблицы notification: ни CREATE TYPE
            # (create_type=False, иначе DuplicateObjectError), ни второй
            # CHECK-констрейнт (create_constraint=False) тут не создаём.
            sa.Enum(
                "response_received",
                "response_accepted",
                "response_rejected",
                "response_confirmed",
                "invitation_received",
                "invitation_accepted",
                "invitation_rejected",
                "stage_approval_required",
                "task_created",
                "task_updated",
                "task_moved",
                "task_deleted",
                "subtask_created",
                "subtask_updated",
                "subtask_deleted",
                name="notification_type_enum",
                create_constraint=False,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "sending",
                "sent",
                "failed",
                name=PUSH_OUTBOX_STATUS_ENUM,
                create_constraint=True,
            ),
            # Именно текстовый литерал в кавычках: server_default="pending"
            # как строка дал бы DEFAULT 'pending', а sa.text("pending") —
            # DEFAULT pending, который Postgres читает как ссылку на колонку и
            # отбивает ошибкой "cannot use column reference in DEFAULT expression".
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notification.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # Частичный индекс под выборку батча воркером: отправленные строки, которых
    # в базе подавляющее большинство, в выборку не попадают вообще.
    op.create_index(
        "ix_push_outbox_ready",
        "push_outbox",
        ["status", "available_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )
    op.create_index("ix_push_outbox_created", "push_outbox", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_push_outbox_created", table_name="push_outbox")
    op.drop_index("ix_push_outbox_ready", table_name="push_outbox")
    op.drop_table("push_outbox")
    op.drop_index("ix_push_subscription_user_active", table_name="push_subscription")
    op.drop_table("push_subscription")

    op.add_column("user", sa.Column("push_token", sa.String(length=255), nullable=True, comment="FCM/APNs push token for mobile"))

    # Типы надо сбрасывать в конце: drop_table их не убирает, они остаются
    # висеть в базе и следующий upgrade упал бы с DuplicateObjectError.
    sa.Enum(name=PUSH_PLATFORM_ENUM).drop(op.get_bind(), checkfirst=True)
    sa.Enum(name=PUSH_OUTBOX_STATUS_ENUM).drop(op.get_bind(), checkfirst=True)
