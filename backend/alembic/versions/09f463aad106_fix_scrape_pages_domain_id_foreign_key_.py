"""Fix scrape_pages domain_id foreign key cascade

Revision ID: 09f463aad106
Revises: 660d3b654afb
Create Date: 2025-08-21 12:37:25.619336

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '09f463aad106'
down_revision: Union[str, None] = '660d3b654afb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the existing foreign key constraint without CASCADE
    op.drop_constraint('scrape_pages_domain_id_fkey', 'scrape_pages', type_='foreignkey')
    
    # Recreate with CASCADE delete
    op.create_foreign_key(
        'scrape_pages_domain_id_fkey', 
        'scrape_pages', 
        'domains', 
        ['domain_id'], 
        ['id'], 
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Drop the CASCADE foreign key constraint
    op.drop_constraint('scrape_pages_domain_id_fkey', 'scrape_pages', type_='foreignkey')
    
    # Recreate without CASCADE (original state)
    op.create_foreign_key(
        'scrape_pages_domain_id_fkey', 
        'scrape_pages', 
        'domains', 
        ['domain_id'], 
        ['id']
    )