"""add_assessment_window_audience

Revision ID: d104a10b20c9
Revises: d108a10b20c7
Create Date: 2026-11-16 14:20:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d104a10b20c9"
down_revision: str | Sequence[str] | None = "d109a10b20c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "assessment_window_audience",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("window_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("own_project_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("admitted", sa.Boolean(), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audience_window", "assessment_window_audience", ["window_id"])
    op.create_unique_constraint("uq_audience_user", "assessment_window_audience", ["window_id", "user_id"])
    op.create_foreign_key(
        "fk_audience_user",
        "assessment_window_audience",
        "user",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_audience_window",
        "assessment_window_audience",
        "assessment_window",
        ["window_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_audience_role",
        "assessment_window_audience",
        "role IN ('teacher','manager','member')",
    )
    op.create_check_constraint(
        "ck_audience_exclusion",
        "assessment_window_audience",
        "(admitted = TRUE AND exclusion_reason IS NULL) OR "
        "(admitted = FALSE AND exclusion_reason IN ('member_of_defending_team','manager_of_defending_team'))",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("assessment_window_audience")
