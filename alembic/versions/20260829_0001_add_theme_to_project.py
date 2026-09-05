from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    binding = op.get_bind()
    inspector = sa.inspect(binding)
    columns = {c["name"] for c in inspector.get_columns("project")}
    if "theme" not in columns:
        op.execute("ALTER TABLE project ADD COLUMN theme TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE project DROP COLUMN IF EXISTS theme")
