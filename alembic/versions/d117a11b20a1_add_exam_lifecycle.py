"""Add timestamps for exam completion and archival."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d117a11b20a1"
down_revision = "d116a10b20c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.add_column("exam", sa.Column("archived_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.execute("LOCK TABLE exam IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM exam WHERE completed_at IS NOT NULL OR archived_at IS NOT NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade while completed or archived exams exist';
            END IF;
        END
        $$
    """)
    op.drop_column("exam", "archived_at")
    op.drop_column("exam", "completed_at")
