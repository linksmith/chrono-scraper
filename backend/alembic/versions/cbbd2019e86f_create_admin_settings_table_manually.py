"""Create admin settings table manually

Revision ID: cbbd2019e86f
Revises: d0304b16226e
Create Date: 2025-08-23 14:13:47.060947

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cbbd2019e86f'
down_revision: Union[str, None] = 'd0304b16226e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create admin_settings table
    op.create_table(
        'admin_settings',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('users_open_registration', sa.Boolean, nullable=False, default=True),
        sa.Column('allow_invitation_tokens', sa.Boolean, nullable=False, default=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_by_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
    )


def downgrade() -> None:
    # Drop admin_settings table
    op.drop_table('admin_settings')