"""add specification comment table

Revision ID: c2d3e4f5a6b7
Revises: 074a657a4dde
Create Date: 2026-09-20 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c2d3e4f5a6b7"
down_revision = "074a657a4dde"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("project_specification_comment"):
        return
    op.create_table(
        "project_specification_comment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("specification_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["specification_id"], ["project_specification.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    if not _table_exists("project_specification_comment"):
        return
    op.drop_table("project_specification_comment")
