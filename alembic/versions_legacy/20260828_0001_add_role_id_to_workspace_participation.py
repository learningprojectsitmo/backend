from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    binding = op.get_bind()
    inspector = sa.inspect(binding)
    columns = {c["name"] for c in inspector.get_columns("workspace_participation")}
    if "role_id" not in columns:
        op.execute("ALTER TABLE workspace_participation ADD COLUMN role_id INTEGER REFERENCES role(id)")
    op.execute(
        """
        UPDATE workspace_participation
        SET role_id = (SELECT r.id FROM role r WHERE r.name = 'member')
        WHERE role_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE workspace_participation DROP COLUMN IF EXISTS role_id")
