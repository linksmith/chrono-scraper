"""Add config and is_active columns to projects

Revision ID: 1ec5bfaae1f9
Revises: 670b566d398f
Create Date: 2025-08-20 20:23:32.576969

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '1ec5bfaae1f9'
down_revision: Union[str, None] = '670b566d398f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add config column with JSON type
    op.add_column('projects', sa.Column('config', sa.JSON(), nullable=True))
    
    # Add is_active column with default value
    op.add_column('projects', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    
    # Update existing rows to have empty dict for config
    op.execute("UPDATE projects SET config = '{}' WHERE config IS NULL")


def downgrade() -> None:
    # Remove the columns
    op.drop_column('projects', 'is_active')
    op.drop_column('projects', 'config')