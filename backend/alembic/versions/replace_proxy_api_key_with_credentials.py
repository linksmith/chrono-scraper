"""Replace proxy_api_key with proxy server, username, and password

Revision ID: replace_proxy_api_key
Revises: drop_legacy_pages_table
Create Date: 2025-01-02 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'replace_proxy_api_key'
down_revision = '447c3f4cdc52'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new proxy credential columns
    op.add_column('users', sa.Column('proxy_server', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('proxy_username', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('proxy_password', sa.String(length=255), nullable=True))
    
    # Drop the old proxy_api_key column
    op.drop_column('users', 'proxy_api_key')


def downgrade() -> None:
    # Re-add the proxy_api_key column
    op.add_column('users', sa.Column('proxy_api_key', sa.String(length=255), nullable=True))
    
    # Drop the new proxy credential columns
    op.drop_column('users', 'proxy_password')
    op.drop_column('users', 'proxy_username')
    op.drop_column('users', 'proxy_server')