"""merge_heads

Revision ID: d45e1d5d87ec
Revises: 7c47e54ced9a, add_langextract_fields
Create Date: 2025-08-13 12:50:53.862264

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd45e1d5d87ec'
down_revision: Union[str, None] = ('7c47e54ced9a', 'add_langextract_fields')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


"""
NOTE: This merge migration exists to unify previous divergent heads.
We will now create another merge to include 'change_unix_ts_to_string'.
"""
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass