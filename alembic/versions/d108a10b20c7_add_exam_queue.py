"""add_exam_queue

Revision ID: d108a10b20c7
Revises: d107a10b20c6
Create Date: 2026-11-13 11:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d108a10b20c7"
down_revision: Union[str, Sequence[str], None] = "d107a10b20c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("exam", sa.Column("queue_revision", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_exam_queue_revision", "exam", "queue_revision>=0")

    op.add_column("exam_registration", sa.Column("queue_position", sa.Integer(), nullable=True))
    op.add_column("exam_registration", sa.Column("queue_hold", sa.String(length=20), nullable=True))
    op.create_check_constraint(
        "ck_registration_queue_position", "exam_registration", "queue_position IS NULL OR queue_position>=1"
    )
    op.create_check_constraint(
        "ck_registration_queue_hold",
        "exam_registration",
        "queue_hold IS NULL OR queue_hold IN ('postponed','no_show')",
    )
    op.create_check_constraint(
        "ck_registration_hold_off_queue",
        "exam_registration",
        "queue_hold IS NULL OR (queue_position IS NULL AND started_at IS NULL)",
    )
    op.create_index(
        "uq_registration_queue_position",
        "exam_registration",
        ["exam_id", "queue_position"],
        unique=True,
        postgresql_where=sa.text("queue_position IS NOT NULL"),
    )

    op.add_column("registration_event", sa.Column("from_position", sa.Integer(), nullable=True))
    op.add_column("registration_event", sa.Column("to_position", sa.Integer(), nullable=True))

    op.add_column("exam_attempt", sa.Column("postponed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("exam_attempt", sa.Column("postponed_phase", sa.String(length=20), nullable=True))

    # Existing registrations become the initial queue: slot time when slots exist, else registration order.
    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT r.id,
                       row_number() OVER (
                           PARTITION BY r.exam_id
                           ORDER BY s.starts_at NULLS LAST, r.created_at, r.id
                       ) AS position
                FROM exam_registration r
                LEFT JOIN exam_slot s ON s.id = r.slot_id
                WHERE r.status = 'active' AND r.started_at IS NULL
            )
            UPDATE exam_registration r
            SET queue_position = ordered.position
            FROM ordered
            WHERE r.id = ordered.id
            """
        )
    )

    op.drop_constraint("ck_event_action", "registration_event", type_="check")
    op.create_check_constraint(
        "ck_event_action",
        "registration_event",
        "action IN ('created','cancelled','slot_changed','moved_out','moved_in','defense_started',"
        "'postponed','returned','no_show','queue_changed')",
    )
    op.drop_constraint("ck_event_reason", "registration_event", type_="check")
    op.create_check_constraint(
        "ck_event_reason",
        "registration_event",
        "action NOT IN ('cancelled','slot_changed','moved_out','moved_in','postponed','no_show')"
        " OR (reason IS NOT NULL AND btrim(reason)<>'')",
    )
    op.create_check_constraint(
        "ck_event_queue_source",
        "registration_event",
        "action NOT IN ('postponed','returned','no_show','queue_changed') OR source='organizer'",
    )
    op.create_check_constraint(
        "ck_event_queue_positions",
        "registration_event",
        "(action='queue_changed' AND from_position IS NOT NULL AND to_position IS NOT NULL)"
        " OR (action='returned' AND from_position IS NULL AND to_position IS NOT NULL)"
        " OR (action IN ('postponed','no_show') AND to_position IS NULL)"
        " OR (action NOT IN ('queue_changed','returned','postponed','no_show')"
        " AND from_position IS NULL AND to_position IS NULL)",
    )

    op.drop_constraint("ck_attempt_status", "exam_attempt", type_="check")
    op.create_check_constraint(
        "ck_attempt_status", "exam_attempt", "status IN ('speaking','questions','postponed','finished')"
    )
    op.drop_constraint("ck_attempt_pause", "exam_attempt", type_="check")
    op.create_check_constraint(
        "ck_attempt_pause", "exam_attempt", "paused_at IS NULL OR status NOT IN ('finished','postponed')"
    )
    op.create_check_constraint(
        "ck_attempt_postponed_state",
        "exam_attempt",
        "(status='postponed') = (postponed_at IS NOT NULL AND postponed_phase IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_attempt_postponed_phase",
        "exam_attempt",
        "postponed_phase IS NULL OR postponed_phase IN ('speaking','questions')",
    )
    op.create_index("ix_attempt_exam_postponed", "exam_attempt", ["exam_id", "postponed_at", "id"], unique=False)

    op.drop_constraint("ck_attempt_event_action", "attempt_event", type_="check")
    op.create_check_constraint(
        "ck_attempt_event_action",
        "attempt_event",
        "action IN ('started','questions','paused','resumed','finished','postponed','restarted')",
    )
    op.create_check_constraint(
        "ck_attempt_event_postponed_reason",
        "attempt_event",
        "action<>'postponed' OR (reason IS NOT NULL AND btrim(reason)<>'')",
    )


def downgrade() -> None:
    """Downgrade schema.

    Destructive: postponed attempts become finished without an assessment window
    and queue-only events are deleted. Run only against a disposable database.
    """
    op.drop_constraint("ck_attempt_event_postponed_reason", "attempt_event", type_="check")
    op.drop_constraint("ck_attempt_event_action", "attempt_event", type_="check")
    op.execute(sa.text("DELETE FROM attempt_event WHERE action IN ('postponed','restarted')"))
    op.create_check_constraint(
        "ck_attempt_event_action",
        "attempt_event",
        "action IN ('started','questions','paused','resumed','finished')",
    )

    op.drop_index("ix_attempt_exam_postponed", table_name="exam_attempt")
    op.drop_constraint("ck_attempt_postponed_phase", "exam_attempt", type_="check")
    op.drop_constraint("ck_attempt_postponed_state", "exam_attempt", type_="check")
    op.drop_constraint("ck_attempt_status", "exam_attempt", type_="check")
    op.drop_constraint("ck_attempt_pause", "exam_attempt", type_="check")
    op.execute(
        sa.text(
            "UPDATE exam_attempt SET status='finished', "
            "finished_at=COALESCE(postponed_at, updated_at), paused_at=NULL, "
            "postponed_at=NULL, postponed_phase=NULL WHERE status='postponed'"
        )
    )
    op.drop_column("exam_attempt", "postponed_phase")
    op.drop_column("exam_attempt", "postponed_at")
    op.create_check_constraint(
        "ck_attempt_status", "exam_attempt", "status IN ('speaking','questions','finished')"
    )
    op.create_check_constraint("ck_attempt_pause", "exam_attempt", "paused_at IS NULL OR status<>'finished'")

    op.drop_constraint("ck_event_queue_positions", "registration_event", type_="check")
    op.drop_constraint("ck_event_queue_source", "registration_event", type_="check")
    op.drop_constraint("ck_event_action", "registration_event", type_="check")
    op.drop_constraint("ck_event_reason", "registration_event", type_="check")
    op.execute(sa.text("DELETE FROM registration_event WHERE action IN ('postponed','returned','no_show','queue_changed')"))
    op.create_check_constraint(
        "ck_event_action",
        "registration_event",
        "action IN ('created','cancelled','slot_changed','moved_out','moved_in','defense_started')",
    )
    op.create_check_constraint(
        "ck_event_reason",
        "registration_event",
        "action NOT IN ('cancelled','slot_changed','moved_out','moved_in')"
        " OR (reason IS NOT NULL AND btrim(reason)<>'')",
    )
    op.drop_column("registration_event", "to_position")
    op.drop_column("registration_event", "from_position")

    op.drop_index("uq_registration_queue_position", table_name="exam_registration")
    op.drop_constraint("ck_registration_hold_off_queue", "exam_registration", type_="check")
    op.drop_constraint("ck_registration_queue_hold", "exam_registration", type_="check")
    op.drop_constraint("ck_registration_queue_position", "exam_registration", type_="check")
    op.drop_column("exam_registration", "queue_hold")
    op.drop_column("exam_registration", "queue_position")

    op.drop_constraint("ck_exam_queue_revision", "exam", type_="check")
    op.drop_column("exam", "queue_revision")
