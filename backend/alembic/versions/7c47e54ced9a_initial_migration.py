"""Initial migration

Revision ID: 7c47e54ced9a
Revises: 2e9f802d3e2b
Create Date: 2025-08-12 18:04:24.613316

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '7c47e54ced9a'
down_revision: Union[str, None] = '2e9f802d3e2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass