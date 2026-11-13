"""add_exam_attempts

Revision ID: d107a10b20c6
Revises: d102a10b20c5
Create Date: 2026-11-12 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d107a10b20c6"
down_revision: Union[str, Sequence[str], None] = "d102a10b20c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "exam_attempt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("registration_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_type_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("phase_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_seconds", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(status='finished' AND finished_at IS NOT NULL) OR (status<>'finished' AND finished_at IS NULL)",
            name="ck_attempt_finished",
        ),
        sa.CheckConstraint("paused_at IS NULL OR status<>'finished'", name="ck_attempt_pause"),
        sa.CheckConstraint("paused_seconds>=0", name="ck_attempt_paused_seconds"),
        sa.CheckConstraint("phase_deadline>=phase_started_at", name="ck_attempt_deadline"),
        sa.CheckConstraint("status IN ('speaking','questions','finished')", name="ck_attempt_status"),
        sa.CheckConstraint("version>=1", name="ck_attempt_version"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_type_id", "workspace_id"],
            ["project_type.id", "project_type.workspace_id"],
            name="fk_attempt_type_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["registration_id", "exam_id", "workspace_id"],
            ["exam_registration.id", "exam_registration.exam_id", "exam_registration.workspace_id"],
            name="fk_attempt_registration_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "exam_id", "workspace_id", name="uq_attempt_scope"),
        sa.UniqueConstraint("registration_id", name="uq_attempt_registration"),
    )
    op.create_index("ix_attempt_exam_finished", "exam_attempt", ["exam_id", "finished_at", "id"], unique=False)
    op.create_index(
        "uq_attempt_running_exam",
        "exam_attempt",
        ["exam_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('speaking','questions')"),
    )
    op.create_table(
        "attempt_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.CheckConstraint(
            "action IN ('started','questions','paused','resumed','finished')",
            name="ck_attempt_event_action",
        ),
        sa.CheckConstraint("reason IS NULL OR btrim(reason)<>''", name="ck_attempt_event_reason"),
        sa.CheckConstraint("version>=1", name="ck_attempt_event_version"),
        sa.ForeignKeyConstraint(["actor_id"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["attempt_id", "exam_id", "workspace_id"],
            ["exam_attempt.id", "exam_attempt.exam_id", "exam_attempt.workspace_id"],
            name="fk_attempt_event_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "version", name="uq_attempt_event_version"),
    )
    op.create_table(
        "assessment_window",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("project_type_id", sa.Integer(), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("closes_at>opened_at", name="ck_window_interval"),
        sa.CheckConstraint("settings_version>=1", name="ck_window_version"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["attempt_id", "exam_id", "workspace_id"],
            ["exam_attempt.id", "exam_attempt.exam_id", "exam_attempt.workspace_id"],
            name="fk_window_attempt_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_type_id", "workspace_id"],
            ["project_type.id", "project_type.workspace_id"],
            name="fk_window_type_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_window_attempt"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("assessment_window")
    op.drop_table("attempt_event")
    op.drop_index(
        "uq_attempt_running_exam",
        table_name="exam_attempt",
        postgresql_where=sa.text("status IN ('speaking','questions')"),
    )
    op.drop_index("ix_attempt_exam_finished", table_name="exam_attempt")
    op.drop_table("exam_attempt")
