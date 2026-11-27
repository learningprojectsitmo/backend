"""Scope project registration uniqueness to unfinished exams."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d117a11b20a5"
down_revision = "d117a11b20a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("LOCK TABLE exam IN EXCLUSIVE MODE")
    # Cancel/move can read registrations before locking exams. Fail fast if a
    # request has already reached that read, so it can finish before we retry.
    op.execute("LOCK TABLE exam_registration IN ACCESS EXCLUSIVE MODE NOWAIT")
    op.add_column("exam_registration", sa.Column("exam_completed_at", sa.DateTime(timezone=True)))
    op.execute("""
        UPDATE exam_registration AS registration
        SET exam_completed_at = exam.completed_at
        FROM exam
        WHERE exam.id = registration.exam_id AND exam.completed_at IS NOT NULL
    """)
    op.drop_index("uq_registration_active_project", table_name="exam_registration")
    op.create_index(
        "uq_registration_active_project",
        "exam_registration",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status='active' AND exam_completed_at IS NULL"),
    )
    op.execute("""
        CREATE FUNCTION sync_exam_registration_completion() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            SELECT completed_at INTO NEW.exam_completed_at
            FROM exam
            WHERE id = NEW.exam_id AND workspace_id = NEW.workspace_id
            FOR SHARE;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER sync_exam_registration_completion
        BEFORE INSERT OR UPDATE OF exam_id, workspace_id ON exam_registration
        FOR EACH ROW EXECUTE FUNCTION sync_exam_registration_completion()
    """)
    op.execute("""
        CREATE FUNCTION propagate_exam_completion() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            UPDATE exam_registration
            SET exam_completed_at = NEW.completed_at
            WHERE exam_id = NEW.id;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER propagate_exam_completion
        AFTER UPDATE OF completed_at ON exam
        FOR EACH ROW WHEN (OLD.completed_at IS DISTINCT FROM NEW.completed_at)
        EXECUTE FUNCTION propagate_exam_completion()
    """)


def downgrade() -> None:
    op.execute("LOCK TABLE exam IN EXCLUSIVE MODE")
    op.execute("LOCK TABLE exam_registration IN ACCESS EXCLUSIVE MODE NOWAIT")
    op.execute("""
        DO $$
        DECLARE
            duplicate_project_id integer;
        BEGIN
            SELECT project_id INTO duplicate_project_id
            FROM exam_registration
            WHERE status = 'active'
            GROUP BY project_id
            HAVING count(*) > 1
            ORDER BY project_id
            LIMIT 1;

            IF FOUND THEN
                RAISE EXCEPTION 'Cannot downgrade exam registration: project % has multiple active registrations',
                    duplicate_project_id
                    USING HINT = 'Keep the current schema to preserve historical registrations.';
            END IF;
        END;
        $$
    """)
    op.execute("DROP TRIGGER propagate_exam_completion ON exam")
    op.execute("DROP FUNCTION propagate_exam_completion()")
    op.execute("DROP TRIGGER sync_exam_registration_completion ON exam_registration")
    op.execute("DROP FUNCTION sync_exam_registration_completion()")
    op.drop_index("uq_registration_active_project", table_name="exam_registration")
    op.create_index(
        "uq_registration_active_project",
        "exam_registration",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status='active'"),
    )
    op.drop_column("exam_registration", "exam_completed_at")
