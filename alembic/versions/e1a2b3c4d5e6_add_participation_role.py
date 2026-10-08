"""add project_participation.role

Revision ID: e1a2b3c4d5e6
Revises: d4e5f6a7b8c9
Create Date: 2026-10-09 12:00:00.000000

Роль участника, заданная руководителем вручную. ``NULL`` означает «роль не
задавали»: тогда она по-прежнему выводится автоматически (автор проекта или
вакансия принятого отклика). Ручное значение имеет приоритет.

Данные не переливаются: колонка пустая, существующее поведение не меняется.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("project_participation", sa.Column("role", sa.String(length=200), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("project_participation", "role")
