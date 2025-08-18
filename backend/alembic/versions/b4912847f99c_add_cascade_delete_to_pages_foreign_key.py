"""Add CASCADE delete to pages foreign key

Revision ID: b4912847f99c
Revises: 22b334af81f5
Create Date: 2025-08-14 07:32:48.134130

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b4912847f99c'
down_revision: Union[str, None] = '22b334af81f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop and recreate pages domain foreign key with CASCADE DELETE
    op.drop_constraint('pages_domain_id_fkey', 'pages', type_='foreignkey')
    op.create_foreign_key('pages_domain_id_fkey', 'pages', 'domains', 
                         ['domain_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Revert back to NO ACTION constraint  
    op.drop_constraint('pages_domain_id_fkey', 'pages', type_='foreignkey')
    op.create_foreign_key('pages_domain_id_fkey', 'pages', 'domains',
                         ['domain_id'], ['id'], ondelete='NO ACTION')