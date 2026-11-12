"""add_exam_registrations

Revision ID: d102a10b20c5
Revises: d101a10b20c4
Create Date: 2026-11-12 18:15:31.404789

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d102a10b20c5"
down_revision: Union[str, Sequence[str], None] = "d101a10b20c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "exam_slot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("ends_at>starts_at", name="ck_slot_interval"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["exam_id", "workspace_id"],
            ["exam.id", "exam.workspace_id"],
            name="fk_slot_exam_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_id", "starts_at", "ends_at", name="uq_exam_slot_interval"),
        sa.UniqueConstraint("id", "exam_id", "workspace_id", name="uq_exam_slot_scope"),
    )
    op.create_table(
        "exam_registration",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_type_id_at_registration", sa.Integer(), nullable=False),
        sa.Column("slot_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_source", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("created_source IN ('manager','organizer')", name="ck_registration_source"),
        sa.CheckConstraint("started_at IS NULL OR status='active'", name="ck_registration_started"),
        sa.CheckConstraint("status IN ('active','cancelled','moved')", name="ck_registration_status"),
        sa.CheckConstraint("version>=1", name="ck_registration_version"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["exam_id", "workspace_id"],
            ["exam.id", "exam.workspace_id"],
            name="fk_registration_exam_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["project_type_id_at_registration", "workspace_id"],
            ["project_type.id", "project_type.workspace_id"],
            name="fk_registration_type_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["slot_id", "exam_id", "workspace_id"],
            ["exam_slot.id", "exam_slot.exam_id", "exam_slot.workspace_id"],
            name="fk_registration_slot_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "exam_id", "workspace_id", name="uq_registration_exam_scope"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_registration_scope"),
    )
    op.create_index("ix_registration_exam_created", "exam_registration", ["exam_id", "created_at", "id"], unique=False)
    op.create_index(
        "uq_registration_active_project",
        "exam_registration",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status='active'"),
    )
    op.create_index(
        "uq_registration_active_slot",
        "exam_registration",
        ["slot_id"],
        unique=True,
        postgresql_where=sa.text("status='active' AND slot_id IS NOT NULL"),
    )
    op.create_table(
        "registration_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("registration_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("from_slot_id", sa.Integer(), nullable=True),
        sa.Column("to_slot_id", sa.Integer(), nullable=True),
        sa.Column("related_registration_id", sa.Integer(), nullable=True),
        sa.Column("transfer_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(action IN ('moved_out','moved_in') AND transfer_id IS NOT NULL AND related_registration_id IS NOT NULL) OR (action NOT IN ('moved_out','moved_in') AND transfer_id IS NULL AND related_registration_id IS NULL)",
            name="ck_event_transfer",
        ),
        sa.CheckConstraint(
            "action IN ('created','cancelled','slot_changed','moved_out','moved_in','defense_started')",
            name="ck_event_action",
        ),
        sa.CheckConstraint(
            "action NOT IN ('cancelled','slot_changed','moved_out','moved_in') OR (reason IS NOT NULL AND btrim(reason)<>'')",
            name="ck_event_reason",
        ),
        sa.CheckConstraint("action<>'defense_started' OR source='organizer'", name="ck_event_start_source"),
        sa.CheckConstraint("source IN ('manager','organizer')", name="ck_event_source"),
        sa.CheckConstraint("version>=1", name="ck_event_version"),
        sa.ForeignKeyConstraint(["actor_id"], ["user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["from_slot_id", "exam_id", "workspace_id"],
            ["exam_slot.id", "exam_slot.exam_id", "exam_slot.workspace_id"],
            name="fk_event_from_slot_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["registration_id", "exam_id", "workspace_id"],
            ["exam_registration.id", "exam_registration.exam_id", "exam_registration.workspace_id"],
            name="fk_event_registration_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["related_registration_id", "workspace_id"],
            ["exam_registration.id", "exam_registration.workspace_id"],
            name="fk_event_related_scope",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["to_slot_id", "exam_id", "workspace_id"],
            ["exam_slot.id", "exam_slot.exam_id", "exam_slot.workspace_id"],
            name="fk_event_to_slot_scope",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registration_id", "version", name="uq_registration_event_version"),
        sa.UniqueConstraint("transfer_id", "action", name="uq_registration_transfer_action"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("registration_event")
    op.drop_index(
        "uq_registration_active_slot",
        table_name="exam_registration",
        postgresql_where=sa.text("status='active' AND slot_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_registration_active_project", table_name="exam_registration", postgresql_where=sa.text("status='active'")
    )
    op.drop_index("ix_registration_exam_created", table_name="exam_registration")
    op.drop_table("exam_registration")
    op.drop_table("exam_slot")
