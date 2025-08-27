"""Merge migration branches

Revision ID: c9bd5b89fa4a
Revises: 777e63cf31a3, perf_admin_optimization
Create Date: 2025-08-25 08:50:39.918210

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c9bd5b89fa4a'
down_revision: Union[str, None] = ('777e63cf31a3', 'perf_admin_optimization')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass