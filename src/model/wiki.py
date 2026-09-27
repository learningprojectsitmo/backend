from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.model.project import Project
    from src.model.user import User

# Видимость страницы. private — только команда проекта, public — всем,
# включая анонимного посетителя. Обычная строка, а не PG-enum: значения
# фиксированы приложением, а String не тянет за собой CREATE TYPE и
# DuplicateObjectError при downgrade/upgrade цикле миграций.
WIKI_VISIBILITY_PUBLIC = "public"
WIKI_VISIBILITY_PRIVATE = "private"


class WikiPage(Base):
    """Страница вики проекта."""

    __tablename__ = "wiki_page"
    __table_args__ = (
        Index("ix_wiki_page_project_id", "project_id"),
        Index("ix_wiki_page_project_visibility", "project_id", "visibility"),
        # Обход дерева в ширину ищет страницы по `parent_id IN (...)` — этот
        # индекс нужен именно как одиночный, префиксом его не заменить.
        Index("ix_wiki_page_parent_id", "parent_id"),
        # Корневые страницы и поддерево: фильтр по проекту и родителю плюс
        # сортировка сайдбара по position.
        Index("ix_wiki_page_project_parent_position", "project_id", "parent_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    # NULL — корневая страница, иначе вложенная.
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("wiki_page.id"), nullable=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # HTML в том же виде, что отдаёт TipTap (RichTextViewer на фронте).
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=WIKI_VISIBILITY_PRIVATE,
        server_default=WIKI_VISIBILITY_PRIVATE,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="wiki_pages")
    author: Mapped[User] = relationship()
    parent: Mapped[WikiPage | None] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list[WikiPage]] = relationship(back_populates="parent", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (
            f"WikiPage(id={self.id!r}, project_id={self.project_id!r}, "
            f"parent_id={self.parent_id!r}, title={self.title!r}, visibility={self.visibility!r})"
        )
