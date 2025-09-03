"""Merge migration heads

Revision ID: 670b566d398f
Revises: add_unique_pages_domain_url_ts, b745403ddd61
Create Date: 2025-08-20 20:23:20.724448

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '670b566d398f'
down_revision: Union[str, None] = ('add_unique_pages_domain_url_ts', 'b745403ddd61')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass