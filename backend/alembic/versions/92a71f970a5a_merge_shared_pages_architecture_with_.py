"""Merge shared pages architecture with existing migrations

Revision ID: 92a71f970a5a
Revises: ecaea27bc016, 001_shared_pages_architecture
Create Date: 2025-08-22 19:26:02.275620

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '92a71f970a5a'
down_revision: Union[str, None] = ('ecaea27bc016', '001_shared_pages_architecture')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass