"""Change pages.unix_timestamp to String(14)

Revision ID: change_unix_ts_to_string
Revises: 4f8a997c785a
Create Date: 2025-08-18 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'change_unix_ts_to_string'
down_revision: Union[str, None] = '4f8a997c785a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alter pages.unix_timestamp from Integer to String(14)
    with op.batch_alter_table('pages') as batch_op:
        batch_op.alter_column('unix_timestamp',
                              existing_type=sa.Integer(),
                              type_=sa.String(length=14),
                              existing_nullable=True)


def downgrade() -> None:
    # Revert pages.unix_timestamp to Integer
    with op.batch_alter_table('pages') as batch_op:
        batch_op.alter_column('unix_timestamp',
                              existing_type=sa.String(length=14),
                              type_=sa.Integer(),
                              existing_nullable=True)


