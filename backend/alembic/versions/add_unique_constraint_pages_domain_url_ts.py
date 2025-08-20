"""
Add unique constraint on pages (domain_id, original_url, unix_timestamp)

Revision ID: add_unique_pages_domain_url_ts
Revises: c2f4a7d1b9a0
Create Date: 2025-08-20
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_unique_pages_domain_url_ts'
down_revision = 'c2f4a7d1b9a0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_pages_domain_url_ts',
        'pages',
        ['domain_id', 'original_url', 'unix_timestamp']
    )


def downgrade() -> None:
    op.drop_constraint('uq_pages_domain_url_ts', 'pages', type_='unique')


