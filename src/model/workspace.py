from __future__ import annotations

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database import Base


class WorkSpace(Base):
    __tablename__ = "workspace"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    status_id: Mapped[int] = mapped_column(ForeignKey("workspace_status.id"), nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            f"WorkSpace(id={self.id!r}, name={self.name!r}, author_id={self.author_id!r}, status_id={self.status_id!r})"
        )


class WorkSpaceStatus(Base):
    __tablename__ = "workspace_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            f"WorkSpace(id={self.id!r}, name={self.name!r}, author_id={self.author_id!r}, status_id={self.status_id!r})"
        )


class WorkSpaceParticipation(Base):
    __tablename__ = "workspace_participation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id"), nullable=False)
    participant_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    created_at: Mapped[TIMESTAMP] = mapped_column(TIMESTAMP, server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return (
            f"WorkSpace(id={self.id!r}, name={self.name!r}, author_id={self.author_id!r}, status_id={self.status_id!r})"
        )
