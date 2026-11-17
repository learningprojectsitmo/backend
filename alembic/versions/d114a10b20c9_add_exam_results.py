"""add_exam_results

Revision ID: d114a10b20c9
Revises: d111a10b20c9
Create Date: 2026-11-17 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d114a10b20c9"
down_revision: Union[str, Sequence[str], None] = "d111a10b20c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "exam_result_edition",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("calculated_score", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("final_score", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("teacher_weight", sa.Integer(), nullable=False),
        sa.Column("manager_weight", sa.Integer(), nullable=False),
        sa.Column("member_weight", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("sheet_max", sa.Integer(), nullable=False),
        sa.Column("teacher_sheets", sa.Integer(), nullable=False),
        sa.Column("manager_sheets", sa.Integer(), nullable=False),
        sa.Column("member_sheets", sa.Integer(), nullable=False),
        sa.Column("used_weight", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.CheckConstraint("version>=1", name="ck_result_edition_version"),
        sa.CheckConstraint("kind IN ('calculated','manual')", name="ck_result_edition_kind"),
        sa.CheckConstraint("settings_version>=1", name="ck_result_edition_settings_version"),
        sa.CheckConstraint(
            "teacher_weight BETWEEN 0 AND 100 AND manager_weight BETWEEN 0 AND 100 "
            "AND member_weight BETWEEN 0 AND 100 AND teacher_weight+manager_weight+member_weight=100",
            name="ck_result_edition_weights",
        ),
        sa.CheckConstraint("max_score>0 AND max_score<>'NaN'::numeric", name="ck_result_edition_max_score"),
        sa.CheckConstraint("sheet_max>0", name="ck_result_edition_sheet_max"),
        sa.CheckConstraint(
            "teacher_sheets>=0 AND manager_sheets>=0 AND member_sheets>=0", name="ck_result_edition_sheets_count"
        ),
        sa.CheckConstraint("used_weight BETWEEN 0 AND 100", name="ck_result_edition_used_weight"),
        sa.CheckConstraint(
            "final_score>=0 AND final_score<=max_score AND final_score<>'NaN'::numeric",
            name="ck_result_edition_final_range",
        ),
        sa.CheckConstraint(
            "calculated_score IS NULL OR (calculated_score>=0 AND calculated_score<=max_score "
            "AND calculated_score<>'NaN'::numeric)",
            name="ck_result_edition_calculated_range",
        ),
        sa.CheckConstraint(
            "kind<>'calculated' OR (calculated_score IS NOT NULL AND final_score=calculated_score)",
            name="ck_result_edition_calculated_kind",
        ),
        sa.CheckConstraint("reason IS NULL OR btrim(reason)<>''", name="ck_result_edition_reason_nonblank"),
        sa.CheckConstraint(
            "version=1 OR (reason IS NOT NULL AND btrim(reason)<>'')", name="ck_result_edition_reason_required"
        ),
        sa.CheckConstraint("(published_at IS NULL) = (published_by IS NULL)", name="ck_result_edition_published_pair"),
        sa.ForeignKeyConstraint(["decided_by"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["published_by"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["attempt_id", "exam_id", "workspace_id"],
            ["exam_attempt.id", "exam_attempt.exam_id", "exam_attempt.workspace_id"],
            name="fk_result_edition_attempt_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["exam_id", "settings_version"],
            ["exam_settings_revision.exam_id", "exam_settings_revision.version"],
            name="fk_result_edition_settings",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "version", name="uq_result_edition_version"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("exam_result_edition")
