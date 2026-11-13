"""Add project type questions and five-level explanations.

Revision ID: d100a10b20c3
Revises: b2c3d4e5f6a7
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d100a10b20c3"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_type_question",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_type_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(1000), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_type_id"], ["project_type.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_type_id",
            "position",
            name="uq_project_type_question_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint("btrim(text) <> ''", name="ck_ptq_text_nonblank"),
        sa.CheckConstraint("description IS NULL OR btrim(description) <> ''", name="ck_ptq_description_nonblank"),
        sa.CheckConstraint("position >= 0", name="ck_ptq_position_nonnegative"),
    )
    op.create_table(
        "project_type_question_level",
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(4000), nullable=False),
        sa.PrimaryKeyConstraint("question_id", "score"),
        sa.ForeignKeyConstraint(["question_id"], ["project_type_question.id"], ondelete="CASCADE"),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_ptql_score_range"),
        sa.CheckConstraint("btrim(description) <> ''", name="ck_ptql_description_nonblank"),
    )


def downgrade() -> None:
    op.drop_table("project_type_question_level")
    op.drop_table("project_type_question")
