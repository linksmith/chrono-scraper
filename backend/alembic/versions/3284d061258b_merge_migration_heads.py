"""Merge migration heads

Revision ID: 3284d061258b
Revises: c2f4a7d1b9a0, remove_redundant_content
Create Date: 2025-08-20 09:45:26.123645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '3284d061258b'
down_revision: Union[str, None] = ('c2f4a7d1b9a0', 'remove_redundant_content')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass