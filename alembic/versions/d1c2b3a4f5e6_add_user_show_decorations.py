"""add user.show_decorations

Revision ID: d1c2b3a4f5e6
Revises: f7a8b9c0d1e2
Create Date: 2026-10-17 13:00:00.000000

Персональная настройка: пользователь может отключить праздничный декор у себя
(новогодний и хэллоуинский). Глобальное включение остаётся за админом
(`app_setting`), а этот столбец лишь позволяет конкретному пользователю
спрятать украшения. По умолчанию ``true`` — существующие строки сохраняют
текущее поведение.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1c2b3a4f5e6"
down_revision: str | Sequence[str] | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "user",
        sa.Column("show_decorations", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("user", "show_decorations")
