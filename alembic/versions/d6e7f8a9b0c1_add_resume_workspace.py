"""add resume_workspace and drop resume.is_default

Revision ID: d6e7f8a9b0c1
Revises: e1a2b3c4d5e6
Create Date: 2026-10-15 12:00:00.000000

Резюме назначается на конкретные пространства (M:N). Раньше резюме попадало
во все пространства неявно — через workspace_participation; теперь выдача
(``GET /workspaces/{id}/resumes``) идёт по явной связи resume_workspace.

Признак «основное» переносится с ``resume.is_default`` (одно на автора)
на связь: ровно одно основное резюме на автора В КАЖДОМ пространстве —
это то резюме, которое показывается карточкой участника на странице
пространства.

Backfill: каждое существующее резюме привязывается к первому пространству
автора (самое раннее участие в workspace_participation, тай-брейк по
workspace_id); флаг is_default переносится на новую связь. Резюме в других
пространствах не числились — автор сможет назначить их заново в редакторе.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "e1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "resume_workspace",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("resume_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["resume_id"], ["resume.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Одно резюме — одно пространство (без дублей при повторном сохранении).
    op.create_index("uq_rw_resume_workspace", "resume_workspace", ["resume_id", "workspace_id"], unique=True)
    # Основное резюме ровно одно на автора в пространстве. Частичный индекс
    # объявлен и в модели, и здесь — autogenerate иначе считает его лишним.
    op.create_index(
        "uq_rw_author_workspace_default",
        "resume_workspace",
        ["author_id", "workspace_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.create_index("ix_rw_workspace_id", "resume_workspace", ["workspace_id"])
    op.create_index("ix_rw_author_id", "resume_workspace", ["author_id"])

    # Backfill: первое пространство автора = самое раннее участие
    # (тай-брейк по workspace_id — детерминированность на пустых created_at).
    op.execute(
        sa.text(
            """
            INSERT INTO resume_workspace (resume_id, workspace_id, author_id, is_default, created_at)
            SELECT r.id, first_ws.workspace_id, r.author_id, r.is_default, now()
            FROM resume r
            JOIN LATERAL (
                SELECT wp.workspace_id
                FROM workspace_participation wp
                WHERE wp.participant_id = r.author_id
                ORDER BY wp.created_at ASC NULLS LAST, wp.workspace_id ASC
                LIMIT 1
            ) first_ws ON true
            """
        )
    )

    op.drop_index("uq_resume_author_default", table_name="resume", postgresql_where=sa.text("is_default"))
    op.drop_column("resume", "is_default")


def downgrade() -> None:
    """Downgrade schema."""
    # server_default нужен только чтобы добавить NOT NULL-колонку в таблицу
    # с данными; ниже снимаем его — в исходной схеме колонка без DEFAULT.
    op.add_column("resume", sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        sa.text(
            """
            UPDATE resume r
            SET is_default = true
            FROM resume_workspace rw
            WHERE rw.resume_id = r.id
              AND rw.is_default = true
            """
        )
    )
    # Индекс uq_resume_author_default требует ровно одно основное на автора:
    # при нескольких «основных в пространствах» оставляем самое старое резюме.
    op.execute(
        sa.text(
            """
            UPDATE resume r
            SET is_default = false
            WHERE r.is_default = true
              AND EXISTS (
                  SELECT 1
                  FROM resume r2
                  WHERE r2.author_id = r.author_id
                    AND r2.is_default = true
                    AND r2.id < r.id
              )
            """
        )
    )
    op.create_index(
        "uq_resume_author_default",
        "resume",
        ["author_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )
    op.alter_column("resume", "is_default", server_default=None)
    op.drop_index("ix_rw_author_id", table_name="resume_workspace")
    op.drop_index("ix_rw_workspace_id", table_name="resume_workspace")
    op.drop_index(
        "uq_rw_author_workspace_default",
        table_name="resume_workspace",
        postgresql_where=sa.text("is_default"),
    )
    op.drop_index("uq_rw_resume_workspace", table_name="resume_workspace")
    op.drop_table("resume_workspace")
