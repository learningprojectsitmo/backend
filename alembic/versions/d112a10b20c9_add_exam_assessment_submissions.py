"""add_exam_assessment_submissions

Revision ID: d112a10b20c9
Revises: d114a10b20c9
Create Date: 2026-11-17 18:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d112a10b20c9"
down_revision: str | Sequence[str] | None = "d114a10b20c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "exam_assessment_submission",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("sheet_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_exam_assessment_submission"),
        sa.UniqueConstraint("sheet_id", "version", name="uq_submission_sheet_version"),
        sa.ForeignKeyConstraint(
            ["sheet_id", "attempt_id", "exam_id", "workspace_id"],
            [
                "exam_assessment_sheet.id",
                "exam_assessment_sheet.attempt_id",
                "exam_assessment_sheet.exam_id",
                "exam_assessment_sheet.workspace_id",
            ],
            name="fk_submission_sheet_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version >= 1", name="ck_submission_version"),
        sa.CheckConstraint("total >= 1", name="ck_submission_total"),
    )
    op.create_index("ix_submission_attempt", "exam_assessment_submission", ["attempt_id"])

    op.create_table(
        "exam_assessment_submission_answer",
        sa.Column("submission_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=5000), nullable=True),
        sa.PrimaryKeyConstraint("submission_id", "question_id", name="pk_exam_assessment_submission_answer"),
        sa.ForeignKeyConstraint(
            ["submission_id"],
            ["exam_assessment_submission.id"],
            name="fk_submission_answer_submission",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["project_type_question.id"],
            name="fk_submission_answer_question",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_submission_answer_score"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("exam_assessment_submission_answer")
    op.drop_index("ix_submission_attempt", table_name="exam_assessment_submission")
    op.drop_table("exam_assessment_submission")
