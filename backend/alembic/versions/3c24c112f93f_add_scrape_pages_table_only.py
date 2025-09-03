"""Add scrape_pages table only

Revision ID: 3c24c112f93f
Revises: 7b61c60d84d0
Create Date: 2025-08-14 12:25:55.903494

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c24c112f93f'
down_revision: Union[str, None] = 'b4912847f99c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add scrape_pages table for intelligent filtering
    op.create_table('scrape_pages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('original_url', sa.String(), nullable=False),
    sa.Column('wayback_url', sa.String(), nullable=True),
    sa.Column('digest_hash', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False, default='pending'),
    sa.Column('content_length', sa.Integer(), nullable=True),
    sa.Column('mime_type', sa.String(), nullable=True),
    sa.Column('extraction_method', sa.String(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('retry_count', sa.Integer(), nullable=False, default=0),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.Index('ix_scrape_pages_original_url', 'original_url'),
    sa.Index('ix_scrape_pages_digest_hash', 'digest_hash'),
    sa.Index('ix_scrape_pages_status', 'status'),
    )


def downgrade() -> None:
    op.drop_table('scrape_pages')