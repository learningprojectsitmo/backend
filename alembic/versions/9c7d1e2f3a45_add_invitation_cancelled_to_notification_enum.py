"""add invitation_cancelled to notification_type_enum

Revision ID: 9c7d1e2f3a45
Revises: b3f1c8a4e7d2
Create Date: 2026-10-04 10:30:00.000000

Руководитель проекта теперь может отозвать отправленное приглашение, и об этом
узнаёт приглашённый — из ленты уведомлений и из письма. Отдельный тип, а не
переиспользование `invitation_rejected`: там решение принимает сам приглашённый,
здесь — руководитель проекта.

Значение внесено и в baseline, чтобы пустая БД получала полный тип сразу;
`IF NOT EXISTS` делает дельту на ней идемпотентной.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c7d1e2f3a45"
down_revision: str | Sequence[str] | None = "b3f1c8a4e7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # `ALTER TYPE ... ADD VALUE` выполняется в транзакции самой миграции,
    # поэтому воспользоваться новым значением в этом же migrate нельзя:
    # вставить уведомление с ним может только следующая транзакция.
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'invitation_cancelled'")


def downgrade() -> None:
    """Downgrade schema.

    Postgres не умеет удалять значение из типа без пересоздания самого типа,
    а пересоздание потеряло бы строки уведомлений с этим значением. Поэтому
    откат ничего не делает: значение остаётся в типе, но код его больше не
    пишет, а следующий `upgrade` добавляет его идемпотентно.
    """