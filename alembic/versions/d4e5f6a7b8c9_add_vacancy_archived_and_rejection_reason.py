"""add project_vacancy.archived and response.rejection_reason

Revision ID: d4e5f6a7b8c9
Revises: a4e7b2f91c35
Create Date: 2026-10-08 12:00:00.000000

Две колонки одной миграцией, потому что живут они в одной фиче «удаление
роли и отказ с причиной»:

* ``project_vacancy.archived`` — роль больше не удаляется физически, а
  помечается: ``response.vacancy_id`` не рвётся, поэтому история откликов
  сохраняет название роли, а счётчик мест у вышедших участников продолжает
  работать. Архивные роли не отдаются в ``ProjectFull.vacancies``.
* ``response.rejection_reason`` — причина отказа, указанная руководителем
  при отклонении отклика. NULL означает «отказ без причины».

Данные не переливаются: колонки либо дефолтные (``archived = false``), либо
пустые (``rejection_reason = NULL``), существующее поведение не меняется.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "a4e7b2f91c35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "project_vacancy",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("response", sa.Column("rejection_reason", sa.String(length=200), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("response", "rejection_reason")
    op.drop_column("project_vacancy", "archived")
