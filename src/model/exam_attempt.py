from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ExamAttempt(Base):
    __tablename__ = "exam_attempt"
    __table_args__ = (
        UniqueConstraint("registration_id", name="uq_attempt_registration"),
        UniqueConstraint("id", "exam_id", "workspace_id", name="uq_attempt_scope"),
        ForeignKeyConstraint(
            ["registration_id", "exam_id", "workspace_id"],
            ["exam_registration.id", "exam_registration.exam_id", "exam_registration.workspace_id"],
            name="fk_attempt_registration_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_type_id", "workspace_id"],
            ["project_type.id", "project_type.workspace_id"],
            name="fk_attempt_type_scope",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_attempt_running_exam",
            "exam_id",
            unique=True,
            postgresql_where=text("status IN ('speaking','questions')"),
        ),
        Index("ix_attempt_exam_finished", "exam_id", "finished_at", "id"),
        CheckConstraint("status IN ('speaking','questions','finished')", name="ck_attempt_status"),
        CheckConstraint("version>=1", name="ck_attempt_version"),
        CheckConstraint("paused_seconds>=0", name="ck_attempt_paused_seconds"),
        CheckConstraint(
            "(status='finished' AND finished_at IS NOT NULL) OR (status<>'finished' AND finished_at IS NULL)",
            name="ck_attempt_finished",
        ),
        CheckConstraint("paused_at IS NULL OR status<>'finished'", name="ck_attempt_pause"),
        CheckConstraint("phase_deadline>=phase_started_at", name="ck_attempt_deadline"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    exam_id: Mapped[int] = mapped_column(Integer)
    registration_id: Mapped[int] = mapped_column(Integer)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="RESTRICT"))
    project_type_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    settings_version: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    phase_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    phase_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_seconds: Mapped[int] = mapped_column(Integer, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AttemptEvent(Base):
    __tablename__ = "attempt_event"
    __table_args__ = (
        UniqueConstraint("attempt_id", "version", name="uq_attempt_event_version"),
        ForeignKeyConstraint(
            ["attempt_id", "exam_id", "workspace_id"],
            ["exam_attempt.id", "exam_attempt.exam_id", "exam_attempt.workspace_id"],
            name="fk_attempt_event_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "action IN ('started','questions','paused','resumed','finished')",
            name="ck_attempt_event_action",
        ),
        CheckConstraint("version>=1", name="ck_attempt_event_version"),
        CheckConstraint("reason IS NULL OR btrim(reason)<>''", name="ck_attempt_event_reason"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    exam_id: Mapped[int] = mapped_column(Integer)
    attempt_id: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(1000))


class AssessmentWindow(Base):
    __tablename__ = "assessment_window"
    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_window_attempt"),
        ForeignKeyConstraint(
            ["attempt_id", "exam_id", "workspace_id"],
            ["exam_attempt.id", "exam_attempt.exam_id", "exam_attempt.workspace_id"],
            name="fk_window_attempt_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_type_id", "workspace_id"],
            ["project_type.id", "project_type.workspace_id"],
            name="fk_window_type_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint("closes_at>opened_at", name="ck_window_interval"),
        CheckConstraint("settings_version>=1", name="ck_window_version"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    exam_id: Mapped[int] = mapped_column(Integer)
    attempt_id: Mapped[int] = mapped_column(Integer)
    project_type_id: Mapped[int] = mapped_column(Integer)
    settings_version: Mapped[int] = mapped_column(Integer)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
