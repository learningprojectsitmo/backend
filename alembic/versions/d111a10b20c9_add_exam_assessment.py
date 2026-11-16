"""add_exam_assessment

Revision ID: d111a10b20c9
Revises: d108a10b20c7
Create Date: 2026-11-16 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d111a10b20c9"
down_revision: Union[str, Sequence[str], None] = "d108a10b20c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "exam_assessment_sheet",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_exam_assessment_sheet"),
        sa.UniqueConstraint("user_id", "attempt_id", name="uq_sheet_user_attempt"),
        sa.UniqueConstraint(
            "id", "attempt_id", "exam_id", "workspace_id", name="uq_sheet_scope"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ['"user".id'], name="fk_sheet_user", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["attempt_id", "exam_id", "workspace_id"],
            ["exam_attempt.id", "exam_attempt.exam_id", "exam_attempt.workspace_id"],
            name="fk_sheet_attempt_scope",
            ondelete="RESTRICT",
        ),
    )
    op.create_check_constraint("ck_sheet_status", "exam_assessment_sheet", "status IN ('draft','submitted')")

    op.create_table(
        "exam_assessment_answer",
        sa.Column("sheet_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("comment", sa.String(length=5000), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("sheet_id", "question_id", name="pk_exam_assessment_answer"),
        sa.ForeignKeyConstraint(
            ["sheet_id"],
            ["exam_assessment_sheet.id"],
            name="fk_answer_sheet",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["project_type_question.id"],
            name="fk_answer_question",
            ondelete="RESTRICT",
        ),
    )
    op.create_check_constraint(
        "ck_answer_score", "exam_assessment_answer", "score IS NULL OR score BETWEEN 1 AND 5"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("exam_assessment_answer")
    op.drop_table("exam_assessment_sheet")