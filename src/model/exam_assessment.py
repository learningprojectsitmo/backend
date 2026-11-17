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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ExamAssessmentSheet(Base):
    __tablename__ = "exam_assessment_sheet"
    __table_args__ = (
        UniqueConstraint("user_id", "attempt_id", name="uq_sheet_user_attempt"),
        UniqueConstraint("id", "attempt_id", "exam_id", "workspace_id", name="uq_sheet_scope"),
        ForeignKeyConstraint(
            ["attempt_id", "exam_id", "workspace_id"],
            ["exam_attempt.id", "exam_attempt.exam_id", "exam_attempt.workspace_id"],
            name="fk_sheet_attempt_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('draft','submitted')", name="ck_sheet_status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    exam_id: Mapped[int] = mapped_column(Integer)
    attempt_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExamAssessmentAnswer(Base):
    __tablename__ = "exam_assessment_answer"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sheet_id"],
            ["exam_assessment_sheet.id"],
            name="fk_answer_sheet",
            ondelete="CASCADE",
        ),
        CheckConstraint("score IS NULL OR score BETWEEN 1 AND 5", name="ck_answer_score"),
    )
    sheet_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("project_type_question.id", ondelete="RESTRICT"), primary_key=True
    )
    score: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(String(5000))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExamAssessmentSubmission(Base):
    """Immutable edition of a submitted sheet; the latest edition is the assessor's counted vote."""

    __tablename__ = "exam_assessment_submission"
    __table_args__ = (
        UniqueConstraint("sheet_id", "version", name="uq_submission_sheet_version"),
        ForeignKeyConstraint(
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
        CheckConstraint("version >= 1", name="ck_submission_version"),
        CheckConstraint("total >= 1", name="ck_submission_total"),
        Index("ix_submission_attempt", "attempt_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    exam_id: Mapped[int] = mapped_column(Integer)
    attempt_id: Mapped[int] = mapped_column(Integer)
    sheet_id: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total: Mapped[int] = mapped_column(Integer)


class ExamAssessmentSubmissionAnswer(Base):
    __tablename__ = "exam_assessment_submission_answer"
    __table_args__ = (
        ForeignKeyConstraint(
            ["submission_id"],
            ["exam_assessment_submission.id"],
            name="fk_submission_answer_submission",
            ondelete="CASCADE",
        ),
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_submission_answer_score"),
    )
    submission_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("project_type_question.id", ondelete="RESTRICT"), primary_key=True
    )
    score: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(String(5000))
