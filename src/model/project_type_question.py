from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.project import ProjectType


class ProjectTypeQuestion(Base):
    __tablename__ = "project_type_question"
    __table_args__ = (
        UniqueConstraint(
            "project_type_id",
            "position",
            name="uq_project_type_question_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("btrim(text) <> ''", name="ck_ptq_text_nonblank"),
        CheckConstraint("description IS NULL OR btrim(description) <> ''", name="ck_ptq_description_nonblank"),
        CheckConstraint("position >= 0", name="ck_ptq_position_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_type_id: Mapped[int] = mapped_column(ForeignKey("project_type.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    project_type: Mapped[ProjectType] = relationship(back_populates="questions")
    levels: Mapped[list[ProjectTypeQuestionLevel]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectTypeQuestionLevel.score",
    )


class ProjectTypeQuestionLevel(Base):
    __tablename__ = "project_type_question_level"
    __table_args__ = (
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_ptql_score_range"),
        CheckConstraint("btrim(description) <> ''", name="ck_ptql_description_nonblank"),
    )

    question_id: Mapped[int] = mapped_column(
        ForeignKey("project_type_question.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(String(4000), nullable=False)
    question: Mapped[ProjectTypeQuestion] = relationship(back_populates="levels")
