"""Persist the scoring scale of each project type."""

import sqlalchemy as sa
from alembic import op

revision = "d117a11b20a2"
down_revision = "d117a11b20a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_type", sa.Column("question_max_score", sa.Integer(), server_default="5", nullable=False))
    op.create_check_constraint("ck_project_type_question_scale", "project_type", "question_max_score IN (3, 5)")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM project_type WHERE question_max_score = 3) THEN
                RAISE EXCEPTION 'Cannot downgrade while a project type uses the three-point question scale';
            END IF;
        END
        $$
    """)
    op.drop_constraint("ck_project_type_question_scale", "project_type", type_="check")
    op.drop_column("project_type", "question_max_score")
