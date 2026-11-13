"""add_exam_live_stream

Revision ID: d109a10b20c8
Revises: d108a10b20c7
Create Date: 2026-11-13 22:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d109a10b20c8"
down_revision: Union[str, Sequence[str], None] = "d108a10b20c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("exam", sa.Column("stream_seq", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_exam_stream_seq", "exam", "stream_seq>=0")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_exam_stream_seq", "exam", type_="check")
    op.drop_column("exam", "stream_seq")
