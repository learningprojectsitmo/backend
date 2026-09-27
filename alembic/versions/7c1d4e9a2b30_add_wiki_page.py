"""add wiki_page

Revision ID: 7c1d4e9a2b30
Revises: 62a9db7b0f16
Create Date: 2026-09-27 10:12:44.118902

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1d4e9a2b30"
down_revision: str | Sequence[str] | None = "62a9db7b0f16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "wiki_page",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        # Обычная строка, а не PG-enum: фиксированный набор значений и
        # никакого CREATE TYPE, который ломает downgrade/upgrade цикл.
        sa.Column("visibility", sa.String(length=20), server_default="private", nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["wiki_page.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wiki_page_parent_id", "wiki_page", ["parent_id"], unique=False)
    op.create_index("ix_wiki_page_project_id", "wiki_page", ["project_id"], unique=False)
    op.create_index(
        "ix_wiki_page_project_visibility",
        "wiki_page",
        ["project_id", "visibility"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_wiki_page_project_visibility", table_name="wiki_page")
    op.drop_index("ix_wiki_page_project_id", table_name="wiki_page")
    op.drop_index("ix_wiki_page_parent_id", table_name="wiki_page")
    op.drop_table("wiki_page")
