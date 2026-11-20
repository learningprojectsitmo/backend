"""Add timestamps for exam completion and archival."""

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
    op.drop_column("exam", "archived_at")
    op.drop_column("exam", "completed_at")
