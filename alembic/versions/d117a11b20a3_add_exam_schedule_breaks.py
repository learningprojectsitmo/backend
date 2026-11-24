"""Persist exam schedule breaks and permit atomic slot interval swaps."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d117a11b20a3"
down_revision = "d117a11b20a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exam_slot", sa.Column("kind", sa.String(length=10), nullable=False, server_default="defense"))
    op.create_check_constraint("ck_slot_kind", "exam_slot", "kind IN ('defense', 'break')")
    op.drop_constraint("uq_exam_slot_interval", "exam_slot", type_="unique")
    op.create_unique_constraint(
        "uq_exam_slot_interval", "exam_slot", ["exam_id", "starts_at", "ends_at"], deferrable=True
    )


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM exam_slot WHERE kind = 'break') THEN
                RAISE EXCEPTION 'Cannot downgrade while exam schedules contain breaks';
            END IF;
        END
        $$
    """)
    op.drop_constraint("uq_exam_slot_interval", "exam_slot", type_="unique")
    op.create_unique_constraint("uq_exam_slot_interval", "exam_slot", ["exam_id", "starts_at", "ends_at"])
    op.drop_constraint("ck_slot_kind", "exam_slot", type_="check")
    op.drop_column("exam_slot", "kind")
