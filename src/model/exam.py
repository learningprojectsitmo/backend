from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class Exam(Base):
    __tablename__ = "exam"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_exam_scope"),
        ForeignKeyConstraint(
            ["id", "current_settings_version"],
            ["exam_settings_revision.exam_id", "exam_settings_revision.version"],
            name="fk_exam_current_revision",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        CheckConstraint("status IN ('draft','published')", name="ck_exam_status"),
        CheckConstraint("queue_revision>=0", name="ck_exam_queue_revision"),
        CheckConstraint("stream_seq>=0", name="ck_exam_stream_seq"),
        CheckConstraint(
            "(status='draft' AND published_at IS NULL AND published_by IS NULL) OR (status='published' AND published_at IS NOT NULL AND published_by IS NOT NULL)",
            name="ck_exam_publication",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement="ignore_fk")
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    current_settings_version: Mapped[int] = mapped_column(Integer, default=1)
    queue_revision: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    stream_seq: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"))
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExamSettingsRevision(Base):
    __tablename__ = "exam_settings_revision"
    __table_args__ = (
        ForeignKeyConstraint(
            ["exam_id", "workspace_id"], ["exam.id", "exam.workspace_id"], name="fk_esr_exam_scope", ondelete="RESTRICT"
        ),
        UniqueConstraint("exam_id", "version", "workspace_id", name="uq_esr_scope"),
        CheckConstraint("version>=1", name="ck_esr_version"),
        CheckConstraint("btrim(title)<>''", name="ck_esr_title"),
        CheckConstraint("version=1 OR (reason IS NOT NULL AND btrim(reason)<>'')", name="ck_esr_reason"),
        CheckConstraint(
            "teacher_weight BETWEEN 0 AND 100 AND manager_weight BETWEEN 0 AND 100 AND member_weight BETWEEN 0 AND 100 AND teacher_weight+manager_weight+member_weight=100",
            name="ck_esr_weights",
        ),
        CheckConstraint("max_score>0 AND max_score<>'NaN'::numeric", name="ck_esr_max_score"),
        CheckConstraint(
            "presentation_minutes BETWEEN 1 AND 1440 AND questions_minutes BETWEEN 0 AND 1440 AND transition_minutes BETWEEN 0 AND 1440 AND assessment_window_minutes BETWEEN 1 AND 1440",
            name="ck_esr_minutes",
        ),
        CheckConstraint(
            "(registration_opens_at IS NULL OR registration_opens_at<=starts_at) AND (registration_closes_at IS NULL OR registration_closes_at<=starts_at) AND (registration_opens_at IS NULL OR registration_closes_at IS NULL OR registration_opens_at<registration_closes_at)",
            name="ck_esr_registration",
        ),
    )
    exam_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(5000))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    connection_url: Mapped[str | None] = mapped_column(String(2048))
    registration_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    teacher_weight: Mapped[int] = mapped_column(Integer)
    manager_weight: Mapped[int] = mapped_column(Integer)
    member_weight: Mapped[int] = mapped_column(Integer)
    max_score: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    presentation_minutes: Mapped[int] = mapped_column(Integer)
    questions_minutes: Mapped[int] = mapped_column(Integer)
    transition_minutes: Mapped[int] = mapped_column(Integer)
    assessment_window_minutes: Mapped[int] = mapped_column(Integer)
    changed_by: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str | None] = mapped_column(String(1000))


class ExamSettingsProjectType(Base):
    __tablename__ = "exam_settings_project_type"
    __table_args__ = (
        ForeignKeyConstraint(
            ["exam_id", "settings_version", "workspace_id"],
            ["exam_settings_revision.exam_id", "exam_settings_revision.version", "exam_settings_revision.workspace_id"],
            name="fk_espt_revision",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_type_id", "workspace_id"],
            ["project_type.id", "project_type.workspace_id"],
            name="fk_espt_type_scope",
            ondelete="RESTRICT",
        ),
    )
    exam_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settings_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
