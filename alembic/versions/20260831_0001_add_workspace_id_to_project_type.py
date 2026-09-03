from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    binding = op.get_bind()
    inspector = sa.inspect(binding)
    columns = {c["name"] for c in inspector.get_columns("project_type")}
    if "workspace_id" not in columns:
        op.execute(
            "ALTER TABLE project_type ADD COLUMN workspace_id INTEGER REFERENCES workspace(id)"
        )
    # Уникальность имени в рамках пространства (ранее была глобальная UNIQUE на name).
    # Снимаем старый global-constraint и добавляем составной (workspace_id, name).
    unique_constraints = [uc["name"] for uc in inspector.get_unique_constraints("project_type")]
    if "uq_project_type_workspace_name" not in unique_constraints:
        op.execute("ALTER TABLE project_type DROP CONSTRAINT IF EXISTS project_type_name_key")
        op.execute(
            "ALTER TABLE project_type ADD CONSTRAINT uq_project_type_workspace_name "
            "UNIQUE (workspace_id, name)"
        )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE project_type DROP CONSTRAINT IF EXISTS uq_project_type_workspace_name"
    )
    op.execute("ALTER TABLE project_type DROP COLUMN IF EXISTS workspace_id")