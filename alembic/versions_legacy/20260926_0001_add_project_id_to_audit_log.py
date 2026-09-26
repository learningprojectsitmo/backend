"""add project_id and lookup indexes to audit_logs

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-26 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import context, op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None

# Лента активности проекта фильтрует по project_id, лента профиля — по
# performed_by + performed_at, поэтому индексы на все три колонки.
INDEX_COLUMNS = {
    "ix_audit_logs_project_id": "project_id",
    "ix_audit_logs_performed_at": "performed_at",
    "ix_audit_logs_performed_by": "performed_by",
}


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        # В offline-режиме БД нет — предполагаем состояние до миграции.
        return True
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str, *, offline_assumed: bool) -> bool:
    if context.is_offline_mode():
        return offline_assumed
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if not _has_table("audit_logs"):
        return

    # До этой миграции колонки не было.
    if not _has_column("audit_logs", "project_id", offline_assumed=False):
        op.add_column("audit_logs", sa.Column("project_id", sa.Integer(), nullable=True))

    for index, column in INDEX_COLUMNS.items():
        op.execute(f"CREATE INDEX IF NOT EXISTS {index} ON audit_logs ({column})")


def downgrade() -> None:
    if not _has_table("audit_logs"):
        return

    for index in INDEX_COLUMNS:
        op.execute(f"DROP INDEX IF EXISTS {index}")
    # Колонку добавил upgrade этой миграции.
    if _has_column("audit_logs", "project_id", offline_assumed=True):
        op.drop_column("audit_logs", "project_id")
