"""Add attachment disable and domain date range features

Revision ID: 8eb311d61986
Revises: d45e1d5d87ec
Create Date: 2025-08-13 19:05:56.925341

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '8eb311d61986'
down_revision: Union[str, None] = 'd45e1d5d87ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add attachment download option to projects
    op.add_column('projects', sa.Column('enable_attachment_download', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add date range fields to domains
    op.add_column('domains', sa.Column('from_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('domains', sa.Column('to_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove the added columns
    op.drop_column('projects', 'enable_attachment_download')
    op.drop_column('domains', 'from_date')
    op.drop_column('domains', 'to_date')