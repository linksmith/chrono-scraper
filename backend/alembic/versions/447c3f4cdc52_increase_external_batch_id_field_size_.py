"""increase external_batch_id field size for large domains

Revision ID: 447c3f4cdc52
Revises: d065528bce33
Create Date: 2025-09-01 21:59:32.598631

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '447c3f4cdc52'
down_revision: Union[str, None] = 'd065528bce33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Increase external_batch_id field size from VARCHAR(128) to TEXT
    # This allows storing comma-separated batch IDs for large domains with 100+ batches
    op.alter_column(
        'scrape_sessions',
        'external_batch_id',
        type_=sa.Text(),
        existing_type=sa.VARCHAR(128),
        existing_nullable=True
    )


def downgrade() -> None:
    # Revert external_batch_id field back to VARCHAR(128)
    # WARNING: This will truncate data if any batch IDs exceed 128 characters
    op.alter_column(
        'scrape_sessions',
        'external_batch_id',
        type_=sa.VARCHAR(128),
        existing_type=sa.Text(),
        existing_nullable=True
    )