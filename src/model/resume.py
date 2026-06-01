from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.user import User


class Resume(Base):
    __tablename__ = "resume"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    header: Mapped[str] = mapped_column(Text, nullable=False)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    about: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_experience: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    no_experience_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="resumes")
    experiences: Mapped[list[ResumeExperience]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", order_by="ResumeExperience.sort_order"
    )
    skills: Mapped[list[ResumeSkill]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", order_by="ResumeSkill.sort_order"
    )
    interests: Mapped[list[ResumeInterest]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", order_by="ResumeInterest.sort_order"
    )
    links: Mapped[list[ResumeLink]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", order_by="ResumeLink.sort_order"
    )
    educations: Mapped[list[ResumeEducation]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", order_by="ResumeEducation.sort_order"
    )
    languages: Mapped[list[ResumeLanguage]] = relationship(
        back_populates="resume", cascade="all, delete-orphan", order_by="ResumeLanguage.sort_order"
    )

    def __repr__(self) -> str:
        return f"Resume(id={self.id!r}, author_id={self.author_id!r}, header={self.header!r})"


class ResumeExperience(Base):
    __tablename__ = "resume_experience"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"), nullable=False)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[str] = mapped_column(String(200), nullable=False)
    experience_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    period_from: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    duration: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsibilities: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    resume: Mapped[Resume] = relationship(back_populates="experiences")


class ResumeSkill(Base):
    __tablename__ = "resume_skill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    resume: Mapped[Resume] = relationship(back_populates="skills")


class ResumeInterest(Base):
    __tablename__ = "resume_interest"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    resume: Mapped[Resume] = relationship(back_populates="interests")


class ResumeLink(Base):
    __tablename__ = "resume_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    resume: Mapped[Resume] = relationship(back_populates="links")


class ResumeEducation(Base):
    __tablename__ = "resume_education"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"), nullable=False)
    institution: Mapped[str] = mapped_column(String(200), nullable=False)
    faculty: Mapped[str | None] = mapped_column(String(200), nullable=True)
    degree: Mapped[str | None] = mapped_column(String(100), nullable=True)
    years: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    resume: Mapped[Resume] = relationship(back_populates="educations")


class ResumeLanguage(Base):
    __tablename__ = "resume_language"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    resume: Mapped[Resume] = relationship(back_populates="languages")
