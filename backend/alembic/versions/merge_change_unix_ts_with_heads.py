"""merge change_unix_ts_to_string with other head

Revision ID: merge_change_unix_ts_with_heads
Revises: 05eb0e699606, change_unix_ts_to_string
Create Date: 2025-08-18 11:15:00.000000

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = 'merge_change_unix_ts_with_heads'
down_revision: Union[str, None] = ('05eb0e699606', 'change_unix_ts_to_string')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass


