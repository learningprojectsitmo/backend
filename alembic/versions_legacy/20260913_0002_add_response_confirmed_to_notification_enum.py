from __future__ import annotations

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'response_confirmed'")


def downgrade() -> None:
    pass
