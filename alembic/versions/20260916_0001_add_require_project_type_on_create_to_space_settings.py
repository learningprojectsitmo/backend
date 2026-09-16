from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    binding = op.get_bind()
    inspector = sa.inspect(binding)
    columns = {c["name"] for c in inspector.get_columns("space_settings")}
    if "require_project_type_on_create" not in columns:
        # Настройка включена по умолчанию для всех пространств,
        # в том числе уже существующих.
        op.execute("ALTER TABLE space_settings ADD COLUMN require_project_type_on_create BOOLEAN NOT NULL DEFAULT TRUE")


def downgrade() -> None:
    op.execute("ALTER TABLE space_settings DROP COLUMN IF EXISTS require_project_type_on_create")
