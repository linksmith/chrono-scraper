"""Rename wayback_url to content_url in scrape_pages and pages tables

Revision ID: 66fcf1690d1f
Revises: c9bd5b89fa4a
Create Date: 2025-08-25 08:51:11.331528

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '66fcf1690d1f'
down_revision: Union[str, None] = 'c9bd5b89fa4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename wayback_url to content_url in scrape_pages table
    op.alter_column('scrape_pages', 'wayback_url', new_column_name='content_url')
    
    # Rename wayback_url to content_url in pages table
    op.alter_column('pages', 'wayback_url', new_column_name='content_url')


def downgrade() -> None:
    # Rename content_url back to wayback_url in pages table
    op.alter_column('pages', 'content_url', new_column_name='wayback_url')
    
    # Rename content_url back to wayback_url in scrape_pages table
    op.alter_column('scrape_pages', 'content_url', new_column_name='wayback_url')