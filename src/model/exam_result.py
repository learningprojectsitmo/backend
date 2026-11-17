from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ExamResultEdition(Base):
    """One accepted version of the result of an attempt.

    Append-only: a new decision is a new row. The only allowed update of a row is the one-time
    publication mark (published_at/published_by).
    """

    __tablename__ = "exam_result_edition"
    __table_args__ = (
        UniqueConstraint("attempt_id", "version", name="uq_result_edition_version"),
        ForeignKeyConstraint(
            ["attempt_id", "exam_id", "workspace_id"],
            ["exam_attempt.id", "exam_attempt.exam_id", "exam_attempt.workspace_id"],
            name="fk_result_edition_attempt_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["exam_id", "settings_version"],
            ["exam_settings_revision.exam_id", "exam_settings_revision.version"],
            name="fk_result_edition_settings",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version>=1", name="ck_result_edition_version"),
        CheckConstraint("kind IN ('calculated','manual')", name="ck_result_edition_kind"),
        CheckConstraint("settings_version>=1", name="ck_result_edition_settings_version"),
        CheckConstraint(
            "teacher_weight BETWEEN 0 AND 100 AND manager_weight BETWEEN 0 AND 100 "
            "AND member_weight BETWEEN 0 AND 100 AND teacher_weight+manager_weight+member_weight=100",
            name="ck_result_edition_weights",
        ),
        CheckConstraint("max_score>0 AND max_score<>'NaN'::numeric", name="ck_result_edition_max_score"),
        CheckConstraint("sheet_max>0", name="ck_result_edition_sheet_max"),
        CheckConstraint(
            "teacher_sheets>=0 AND manager_sheets>=0 AND member_sheets>=0", name="ck_result_edition_sheets_count"
        ),
        CheckConstraint("used_weight BETWEEN 0 AND 100", name="ck_result_edition_used_weight"),
        CheckConstraint(
            "final_score>=0 AND final_score<=max_score AND final_score<>'NaN'::numeric",
            name="ck_result_edition_final_range",
        ),
        CheckConstraint(
            "calculated_score IS NULL OR (calculated_score>=0 AND calculated_score<=max_score "
            "AND calculated_score<>'NaN'::numeric)",
            name="ck_result_edition_calculated_range",
        ),
        CheckConstraint(
            "kind<>'calculated' OR (calculated_score IS NOT NULL AND final_score=calculated_score)",
            name="ck_result_edition_calculated_kind",
        ),
        CheckConstraint("reason IS NULL OR btrim(reason)<>''", name="ck_result_edition_reason_nonblank"),
        CheckConstraint(
            "version=1 OR (reason IS NOT NULL AND btrim(reason)<>'')", name="ck_result_edition_reason_required"
        ),
        CheckConstraint("(published_at IS NULL) = (published_by IS NULL)", name="ck_result_edition_published_pair"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    exam_id: Mapped[int] = mapped_column(Integer)
    attempt_id: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))
    calculated_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    final_score: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    settings_version: Mapped[int] = mapped_column(Integer)
    teacher_weight: Mapped[int] = mapped_column(Integer)
    manager_weight: Mapped[int] = mapped_column(Integer)
    member_weight: Mapped[int] = mapped_column(Integer)
    max_score: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sheet_max: Mapped[int] = mapped_column(Integer)
    teacher_sheets: Mapped[int] = mapped_column(Integer)
    manager_sheets: Mapped[int] = mapped_column(Integer)
    member_sheets: Mapped[int] = mapped_column(Integer)
    used_weight: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(1000))
    decided_by: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
