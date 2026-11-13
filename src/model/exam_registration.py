from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class ExamSlot(Base):
    __tablename__ = "exam_slot"
    __table_args__ = (
        UniqueConstraint("id", "exam_id", "workspace_id", name="uq_exam_slot_scope"),
        UniqueConstraint("exam_id", "starts_at", "ends_at", name="uq_exam_slot_interval"),
        ForeignKeyConstraint(
            ["exam_id", "workspace_id"],
            ["exam.id", "exam.workspace_id"],
            name="fk_slot_exam_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint("ends_at>starts_at", name="ck_slot_interval"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    exam_id: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExamRegistration(Base):
    __tablename__ = "exam_registration"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_registration_scope"),
        UniqueConstraint("id", "exam_id", "workspace_id", name="uq_registration_exam_scope"),
        ForeignKeyConstraint(
            ["exam_id", "workspace_id"],
            ["exam.id", "exam.workspace_id"],
            name="fk_registration_exam_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["slot_id", "exam_id", "workspace_id"],
            ["exam_slot.id", "exam_slot.exam_id", "exam_slot.workspace_id"],
            name="fk_registration_slot_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["project_type_id_at_registration", "workspace_id"],
            ["project_type.id", "project_type.workspace_id"],
            name="fk_registration_type_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('active','cancelled','moved')", name="ck_registration_status"),
        CheckConstraint("created_source IN ('manager','organizer')", name="ck_registration_source"),
        CheckConstraint("version>=1", name="ck_registration_version"),
        CheckConstraint("started_at IS NULL OR status='active'", name="ck_registration_started"),
        CheckConstraint("queue_position IS NULL OR queue_position>=1", name="ck_registration_queue_position"),
        CheckConstraint(
            "queue_hold IS NULL OR queue_hold IN ('postponed','no_show')", name="ck_registration_queue_hold"
        ),
        CheckConstraint(
            "queue_hold IS NULL OR (queue_position IS NULL AND started_at IS NULL)",
            name="ck_registration_hold_off_queue",
        ),
        Index("uq_registration_active_project", "project_id", unique=True, postgresql_where=text("status='active'")),
        Index(
            "uq_registration_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status='active' AND slot_id IS NOT NULL"),
        ),
        Index("ix_registration_exam_created", "exam_id", "created_at", "id"),
        Index(
            "uq_registration_queue_position",
            "exam_id",
            "queue_position",
            unique=True,
            postgresql_where=text("queue_position IS NOT NULL"),
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    exam_id: Mapped[int] = mapped_column(Integer)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="RESTRICT"))
    project_type_id_at_registration: Mapped[int] = mapped_column(Integer)
    slot_id: Mapped[int | None] = mapped_column(Integer)
    queue_position: Mapped[int | None] = mapped_column(Integer)
    queue_hold: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer)
    created_source: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegistrationEvent(Base):
    __tablename__ = "registration_event"
    __table_args__ = (
        UniqueConstraint("registration_id", "version", name="uq_registration_event_version"),
        UniqueConstraint("transfer_id", "action", name="uq_registration_transfer_action"),
        ForeignKeyConstraint(
            ["registration_id", "exam_id", "workspace_id"],
            ["exam_registration.id", "exam_registration.exam_id", "exam_registration.workspace_id"],
            name="fk_event_registration_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["related_registration_id", "workspace_id"],
            ["exam_registration.id", "exam_registration.workspace_id"],
            name="fk_event_related_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["from_slot_id", "exam_id", "workspace_id"],
            ["exam_slot.id", "exam_slot.exam_id", "exam_slot.workspace_id"],
            name="fk_event_from_slot_scope",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["to_slot_id", "exam_id", "workspace_id"],
            ["exam_slot.id", "exam_slot.exam_id", "exam_slot.workspace_id"],
            name="fk_event_to_slot_scope",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "action IN ('created','cancelled','slot_changed','moved_out','moved_in','defense_started',"
            "'postponed','returned','no_show','queue_changed')",
            name="ck_event_action",
        ),
        CheckConstraint("source IN ('manager','organizer')", name="ck_event_source"),
        CheckConstraint("version>=1", name="ck_event_version"),
        CheckConstraint(
            "(action IN ('moved_out','moved_in') AND transfer_id IS NOT NULL AND related_registration_id IS NOT NULL) OR (action NOT IN ('moved_out','moved_in') AND transfer_id IS NULL AND related_registration_id IS NULL)",
            name="ck_event_transfer",
        ),
        CheckConstraint(
            "action NOT IN ('cancelled','slot_changed','moved_out','moved_in','postponed','no_show')"
            " OR (reason IS NOT NULL AND btrim(reason)<>'')",
            name="ck_event_reason",
        ),
        CheckConstraint("action<>'defense_started' OR source='organizer'", name="ck_event_start_source"),
        CheckConstraint(
            "action NOT IN ('postponed','returned','no_show','queue_changed') OR source='organizer'",
            name="ck_event_queue_source",
        ),
        CheckConstraint(
            "(action='queue_changed' AND from_position IS NOT NULL AND to_position IS NOT NULL)"
            " OR (action='returned' AND from_position IS NULL AND to_position IS NOT NULL)"
            " OR (action IN ('postponed','no_show') AND to_position IS NULL)"
            " OR (action NOT IN ('queue_changed','returned','postponed','no_show')"
            " AND from_position IS NULL AND to_position IS NULL)",
            name="ck_event_queue_positions",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(Integer)
    exam_id: Mapped[int] = mapped_column(Integer)
    registration_id: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="RESTRICT"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(1000))
    from_slot_id: Mapped[int | None] = mapped_column(Integer)
    to_slot_id: Mapped[int | None] = mapped_column(Integer)
    from_position: Mapped[int | None] = mapped_column(Integer)
    to_position: Mapped[int | None] = mapped_column(Integer)
    related_registration_id: Mapped[int | None] = mapped_column(Integer)
    transfer_id: Mapped[UUID | None] = mapped_column(Uuid)
