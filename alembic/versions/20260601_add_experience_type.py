"""add experience_type to resume_experience

Revision ID: 003
Revises: 002
Create Date: 2026-06-01 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "resume_experience",
        sa.Column("experience_type", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("resume_experience", "experience_type")
