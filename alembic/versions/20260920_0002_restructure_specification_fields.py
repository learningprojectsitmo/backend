"""restructure specification fields: add functional/non-functional requirements, drop deadline

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-20 14:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_specification",
        sa.Column(
            "functional_requirements",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "project_specification",
        sa.Column(
            "non_functional_requirements",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.drop_column("project_specification", "deadline")


def downgrade() -> None:
    op.add_column(
        "project_specification",
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_column("project_specification", "non_functional_requirements")
    op.drop_column("project_specification", "functional_requirements")