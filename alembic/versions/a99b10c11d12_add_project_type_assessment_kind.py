"""Add an explicit nullable assessment category to project types.

Revision ID: a99b10c11d12
Revises: b2c3d4e5f6a7
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a99b10c11d12"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_type", sa.Column("assessment_kind", sa.String(32), nullable=True))
    op.create_check_constraint(
        "ck_project_type_assessment_kind",
        "project_type",
        "assessment_kind IS NULL OR assessment_kind IN ('product', 'technical_integration', 'research')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_project_type_assessment_kind", "project_type", type_="check")
    op.drop_column("project_type", "assessment_kind")
