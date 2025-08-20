"""add_external_batch_fields_to_scrape_sessions

Revision ID: e4f414c67094
Revises: 1ec5bfaae1f9
Create Date: 2025-08-20 22:02:57.742135

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e4f414c67094'
down_revision: Union[str, None] = '1ec5bfaae1f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('scrape_sessions', sa.Column('external_batch_id', sa.String(length=128), nullable=True))
    op.add_column('scrape_sessions', sa.Column('external_batch_provider', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('scrape_sessions', 'external_batch_provider')
    op.drop_column('scrape_sessions', 'external_batch_id')