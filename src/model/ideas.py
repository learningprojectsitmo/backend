from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column as SAColumn
from sqlalchemy import DateTime, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.user import User

idea_tag_association = Table(
    "idea_tag_association",
    Base.metadata,
    SAColumn("idea_id", Integer, ForeignKey("idea.id"), primary_key=True),
    SAColumn("tag_id", Integer, ForeignKey("idea_tag.id"), primary_key=True),
)


class IdeaTag(Base):
    __tablename__ = "idea_tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    ideas: Mapped[list[Idea]] = relationship(
        secondary=idea_tag_association,
        back_populates="tags",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"IdeaTag(id={self.id!r}, name={self.name!r})"


class Idea(Base):
    __tablename__ = "idea"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    votes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="new")
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    author: Mapped[User] = relationship(back_populates="ideas")
    tags: Mapped[list[IdeaTag]] = relationship(
        secondary=idea_tag_association,
        back_populates="ideas",
        lazy="selectin",
    )
    votes_list: Mapped[list[IdeaVote]] = relationship(
        back_populates="idea",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list[IdeaComment]] = relationship(
        back_populates="idea",
        cascade="all, delete-orphan",
        order_by="IdeaComment.created_at",
    )

    def __repr__(self) -> str:
        return f"Idea(id={self.id!r}, title={self.title!r}, author_id={self.author_id!r})"


class IdeaVote(Base):
    __tablename__ = "idea_vote"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("idea.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(4), nullable=False)  # "up" or "down"

    idea: Mapped[Idea] = relationship(back_populates="votes_list")
    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return f"IdeaVote(id={self.id!r}, idea_id={self.idea_id!r}, user_id={self.user_id!r}, direction={self.direction!r})"


class IdeaComment(Base):
    __tablename__ = "idea_comment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("idea.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    idea: Mapped[Idea] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return f"IdeaComment(id={self.id!r}, idea_id={self.idea_id!r}, author_id={self.author_id!r})"
