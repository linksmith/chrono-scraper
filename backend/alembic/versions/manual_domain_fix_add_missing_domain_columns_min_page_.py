"""Add missing domain columns (min_page_size, page_size, etc.)

Revision ID: manual_domain_fix
Revises: efb9d4a1be04
Create Date: 2025-08-14 07:27:23.936415

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'manual_domain_fix'
down_revision: Union[str, None] = 'efb9d4a1be04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands manually added for domain table fixes ###
    # These columns were added manually via SQL to fix immediate errors
    # This migration serves as a record of the changes made
    pass


def downgrade() -> None:
    pass