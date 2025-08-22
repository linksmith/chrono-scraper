"""Merge meilisearch cascade migration

Revision ID: ecaea27bc016
Revises: add_cascade_meilisearch_keys, ce456b0160d8
Create Date: 2025-08-22 09:57:08.000765

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'ecaea27bc016'
down_revision: Union[str, None] = ('add_cascade_meilisearch_keys', 'ce456b0160d8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass