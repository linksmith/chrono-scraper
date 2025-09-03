"""Add CASCADE delete to project foreign keys

Revision ID: 22b334af81f5
Revises: manual_domain_fix
Create Date: 2025-08-14 07:29:49.247044

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '22b334af81f5'
down_revision: Union[str, None] = 'manual_domain_fix'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop and recreate foreign key constraints with CASCADE DELETE
    
    # domains table
    op.drop_constraint('domains_project_id_fkey', 'domains', type_='foreignkey')
    op.create_foreign_key('domains_project_id_fkey', 'domains', 'projects', 
                         ['project_id'], ['id'], ondelete='CASCADE')
    
    # scrape_sessions table  
    op.drop_constraint('scrape_sessions_project_id_fkey', 'scrape_sessions', type_='foreignkey')
    op.create_foreign_key('scrape_sessions_project_id_fkey', 'scrape_sessions', 'projects',
                         ['project_id'], ['id'], ondelete='CASCADE')
    
    # search_history table
    op.drop_constraint('search_history_project_id_fkey', 'search_history', type_='foreignkey')  
    op.create_foreign_key('search_history_project_id_fkey', 'search_history', 'projects',
                         ['project_id'], ['id'], ondelete='CASCADE')
    
    # project_shares table
    op.drop_constraint('project_shares_project_id_fkey', 'project_shares', type_='foreignkey')
    op.create_foreign_key('project_shares_project_id_fkey', 'project_shares', 'projects',
                         ['project_id'], ['id'], ondelete='CASCADE')
    
    # public_search_configs table
    op.drop_constraint('public_search_configs_project_id_fkey', 'public_search_configs', type_='foreignkey')
    op.create_foreign_key('public_search_configs_project_id_fkey', 'public_search_configs', 'projects',
                         ['project_id'], ['id'], ondelete='CASCADE')
    
    # starred_items table
    op.drop_constraint('starred_items_project_id_fkey', 'starred_items', type_='foreignkey')
    op.create_foreign_key('starred_items_project_id_fkey', 'starred_items', 'projects',
                         ['project_id'], ['id'], ondelete='CASCADE')
    
    # extracted_entities table  
    op.drop_constraint('extracted_entities_project_id_fkey', 'extracted_entities', type_='foreignkey')
    op.create_foreign_key('extracted_entities_project_id_fkey', 'extracted_entities', 'projects',
                         ['project_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Revert back to NO ACTION constraints
    
    # extracted_entities table
    op.drop_constraint('extracted_entities_project_id_fkey', 'extracted_entities', type_='foreignkey')
    op.create_foreign_key('extracted_entities_project_id_fkey', 'extracted_entities', 'projects',
                         ['project_id'], ['id'], ondelete='NO ACTION')
    
    # starred_items table
    op.drop_constraint('starred_items_project_id_fkey', 'starred_items', type_='foreignkey')
    op.create_foreign_key('starred_items_project_id_fkey', 'starred_items', 'projects',
                         ['project_id'], ['id'], ondelete='NO ACTION')
    
    # public_search_configs table
    op.drop_constraint('public_search_configs_project_id_fkey', 'public_search_configs', type_='foreignkey')
    op.create_foreign_key('public_search_configs_project_id_fkey', 'public_search_configs', 'projects',
                         ['project_id'], ['id'], ondelete='NO ACTION')
    
    # project_shares table
    op.drop_constraint('project_shares_project_id_fkey', 'project_shares', type_='foreignkey')
    op.create_foreign_key('project_shares_project_id_fkey', 'project_shares', 'projects',
                         ['project_id'], ['id'], ondelete='NO ACTION')
    
    # search_history table
    op.drop_constraint('search_history_project_id_fkey', 'search_history', type_='foreignkey')
    op.create_foreign_key('search_history_project_id_fkey', 'search_history', 'projects',
                         ['project_id'], ['id'], ondelete='NO ACTION')
    
    # scrape_sessions table
    op.drop_constraint('scrape_sessions_project_id_fkey', 'scrape_sessions', type_='foreignkey')
    op.create_foreign_key('scrape_sessions_project_id_fkey', 'scrape_sessions', 'projects',
                         ['project_id'], ['id'], ondelete='NO ACTION')
    
    # domains table
    op.drop_constraint('domains_project_id_fkey', 'domains', type_='foreignkey')
    op.create_foreign_key('domains_project_id_fkey', 'domains', 'projects',
                         ['project_id'], ['id'], ondelete='NO ACTION')