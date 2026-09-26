from __future__ import annotations

from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'task_created'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'task_updated'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'task_moved'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'task_deleted'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'subtask_created'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'subtask_updated'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'subtask_deleted'")


def downgrade() -> None:
    pass
