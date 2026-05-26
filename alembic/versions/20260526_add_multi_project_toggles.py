"""add allow_multi_project fields to space_settings

Revision ID: 001
Revises:
Create Date: 2026-05-26 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "space_settings",
        sa.Column(
            "allow_multi_project_participation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "space_settings",
        sa.Column(
            "allow_multi_project_creation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("space_settings", "allow_multi_project_participation")
    op.drop_column("space_settings", "allow_multi_project_creation")
