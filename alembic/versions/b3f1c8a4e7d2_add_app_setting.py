"""add app_setting table

Revision ID: b3f1c8a4e7d2
Revises: c52423977558
Create Date: 2026-10-03 12:00:00.000000

Глобальные настройки инстанса, которые админ переключает из админ-панели.
До этого в проекте не было ни одной такой подсистемы: `settings_type` —
справочник, `space_settings` — настройки отдельного пространства (их правит
автор пространства, а не админ).

Таблица хранит только переопределения: отсутствие строки означает «действует
дефолт из `src/core/app_settings_registry.py`». Поэтому миграция не сидит
данных, и добавление новой настройки в реестр миграции не требует.

Констрейнты безымянные — как во всей остальной схеме: у `Base.metadata` нет
naming_convention, и именованный `uq_app_setting_key` autogenerate не
сопоставил бы с безымянным `unique=True` в модели (проверяется `alembic check`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f1c8a4e7d2"
down_revision: str | Sequence[str] | None = "c52423977558"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "app_setting",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        # ondelete="SET NULL": настройка не должна исчезать, если удалили
        # администратора, который её включал.
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["user.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("app_setting")