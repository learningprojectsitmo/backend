from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    binding = op.get_bind()
    inspector = sa.inspect(binding)
    columns = {c["name"] for c in inspector.get_columns("project_stage")}
    if "duration_days" not in columns:
        op.execute("ALTER TABLE project_stage ADD COLUMN duration_days INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE project_stage DROP COLUMN IF EXISTS duration_days")