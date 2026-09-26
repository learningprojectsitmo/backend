"""add is_default to resume with backfill and per-author unique index

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-26 14:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import context, op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_resume_author_default"

# Список резюме пространства строится как INNER JOIN по author_id, поэтому без
# ограничения «одно резюме на автора» участник с N резюме даёт N карточек.
# Partial unique index делает «не больше одного основного» гарантией БД, а не
# договорённостью сервиса: два конкурентных запроса на смену основного не
# смогут записать две строки is_default = true одному автору.
BACKFILL_SQL = """
UPDATE resume AS r
SET is_default = true
WHERE r.id = (
    SELECT MIN(r2.id) FROM resume AS r2 WHERE r2.author_id = r.author_id
)
"""


def _has_table(name: str) -> bool:
    if context.is_offline_mode():
        # В offline-режиме БД нет — предполагаем состояние до миграции.
        return True
    return name in sa.inspect(op.get_bind()).get_table_names()


def _has_column(table: str, column: str, *, offline_assumed: bool) -> bool:
    if context.is_offline_mode():
        return offline_assumed
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_index(name: str) -> bool:
    if context.is_offline_mode():
        return False
    return name in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("resume")}


def upgrade() -> None:
    if not _has_table("resume"):
        return

    # До этой миграции колонки не было.
    if not _has_column("resume", "is_default", offline_assumed=False):
        op.add_column(
            "resume",
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    # Старые резюме: основным становится самое раннее созданное. MIN(id) на
    # автора даёт ровно одну строку, поэтому до создания индекса дубликатов
    # не возникает.
    op.execute(BACKFILL_SQL)

    if not _has_index(INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            "resume",
            ["author_id"],
            unique=True,
            postgresql_where=sa.text("is_default"),
        )


def downgrade() -> None:
    if not _has_table("resume"):
        return

    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    # Колонку добавил upgrade этой миграции.
    if _has_column("resume", "is_default", offline_assumed=True):
        op.drop_column("resume", "is_default")
