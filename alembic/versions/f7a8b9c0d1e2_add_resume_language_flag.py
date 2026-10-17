"""add resume_language.flag

Revision ID: f7a8b9c0d1e2
Revises: d6e7f8a9b0c1
Create Date: 2026-10-17 12:00:00.000000

Резюме-языки получают колонку ``flag`` (эмодзи), чтобы блок «Языки» в редакторе
резюме совпадал с блоком на странице профиля. У профильных языков флаг уже
хранится (``language.flag``) и теперь копируется в резюме при его создании.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "resume_language",
        sa.Column("flag", sa.String(length=10), nullable=False, server_default="🌐"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("resume_language", "flag")
