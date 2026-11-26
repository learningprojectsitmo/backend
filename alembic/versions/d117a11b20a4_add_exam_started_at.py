"""Persist the actual start of an exam independently of a defense timer."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d117a11b20a4"
down_revision = "d117a11b20a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("""
        UPDATE exam
        SET started_at = COALESCE(
            (SELECT min(attempt.started_at) FROM exam_attempt AS attempt WHERE attempt.exam_id = exam.id),
            exam.completed_at
        )
        WHERE exam.status = 'published'
    """)
    op.create_check_constraint("ck_exam_started", "exam", "started_at IS NULL OR status = 'published'")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM exam
                WHERE exam.started_at IS NOT NULL
                  AND exam.started_at IS DISTINCT FROM COALESCE(
                      (SELECT min(attempt.started_at) FROM exam_attempt AS attempt WHERE attempt.exam_id = exam.id),
                      exam.completed_at
                  )
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade while explicit exam starts exist';
            END IF;
        END
        $$
    """)
    op.drop_constraint("ck_exam_started", "exam", type_="check")
    op.drop_column("exam", "started_at")
