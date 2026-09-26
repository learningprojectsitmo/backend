from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    binding = op.get_bind()
    inspector = sa.inspect(binding)
    columns = {c["name"] for c in inspector.get_columns("space_settings")}
    if "default_project_deadline" not in columns:
        op.execute("ALTER TABLE space_settings ADD COLUMN default_project_deadline TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE space_settings DROP COLUMN IF EXISTS default_project_deadline")
