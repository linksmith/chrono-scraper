"""Merge migration heads

Revision ID: 660d3b654afb
Revises: add_meilisearch_security_fields, e4f414c67094
Create Date: 2025-08-21 12:10:54.298168

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '660d3b654afb'
down_revision: Union[str, None] = ('add_meilisearch_security_fields', 'e4f414c67094')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass