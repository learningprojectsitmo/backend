from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    binding = op.get_bind()
    inspector = sa.inspect(binding)
    columns = {c["name"] for c in inspector.get_columns("project_stage")}
    if "visible_to_participants" not in columns:
        # Новые этапы видимы участникам по умолчанию; первый этап каждого типа
        # закрываем — это прежнее поведение «черновика».
        op.execute("ALTER TABLE project_stage ADD COLUMN visible_to_participants BOOLEAN NOT NULL DEFAULT TRUE")
        op.execute(
            """
            UPDATE project_stage SET visible_to_participants = FALSE
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           row_number() OVER (
                               PARTITION BY project_type_id ORDER BY "order", id
                           ) AS rn
                    FROM project_stage
                ) ranked
                WHERE rn = 1
            )
            """
        )


def downgrade() -> None:
    op.execute("ALTER TABLE project_stage DROP COLUMN IF EXISTS visible_to_participants")
