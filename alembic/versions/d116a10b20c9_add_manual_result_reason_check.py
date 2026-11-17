"""add_manual_result_reason_check

Revision ID: d116a10b20c9
Revises: d112a10b20c9
Create Date: 2026-11-17 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d116a10b20c9"
down_revision: Union[str, Sequence[str], None] = "d112a10b20c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_check_constraint(
        "ck_result_edition_manual_reason",
        "exam_result_edition",
        "kind<>'manual' OR (reason IS NOT NULL AND btrim(reason)<>'')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_result_edition_manual_reason", "exam_result_edition", type_="check")
