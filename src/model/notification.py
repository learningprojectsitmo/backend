from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.user import User


class NotificationType(str, enum.Enum):
    response_received = "response_received"
    response_accepted = "response_accepted"
    response_rejected = "response_rejected"
    response_confirmed = "response_confirmed"
    invitation_received = "invitation_received"
    invitation_accepted = "invitation_accepted"
    invitation_rejected = "invitation_rejected"
    stage_approval_required = "stage_approval_required"
    task_created = "task_created"
    task_updated = "task_updated"
    task_moved = "task_moved"
    task_deleted = "task_deleted"
    subtask_created = "subtask_created"
    subtask_updated = "subtask_updated"
    subtask_deleted = "subtask_deleted"


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type_enum", create_constraint=True),
        nullable=False,
    )
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    read: Mapped[bool] = mapped_column(nullable=False, server_default="false", default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="notifications")

    def __repr__(self) -> str:
        return f"Notification(id={self.id!r}, user_id={self.user_id!r}, type={self.type!r}, read={self.read!r})"
