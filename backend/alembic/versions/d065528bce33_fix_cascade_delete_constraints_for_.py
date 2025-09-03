"""Fix cascade delete constraints for project deletion - comprehensive fix

This migration addresses the foreign key constraint violations when deleting projects
by updating all foreign key constraints that reference projects.id to use CASCADE delete.

The issue: When trying to delete a project through the admin interface, PostgreSQL
prevents deletion with errors like:
"update or delete on table "projects" violates foreign key constraint "domains_project_id_fkey" on table "domains""

This migration fixes all project references to cascade delete properly, ensuring
that when a project is deleted, all related data is cleaned up automatically.

Revision ID: d065528bce33
Revises: c554393a3b3b
Create Date: 2025-09-01 12:24:48.797945

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd065528bce33'
down_revision: Union[str, None] = 'c554393a3b3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Update foreign key constraints to use CASCADE delete for project references.
    This ensures that when a project is deleted, all related data is automatically cleaned up.
    """
    
    # Fix domains -> projects foreign key
    op.drop_constraint('domains_project_id_fkey', 'domains', type_='foreignkey')
    op.create_foreign_key(
        'domains_project_id_fkey', 'domains', 'projects',
        ['project_id'], ['id'], ondelete='CASCADE'
    )
    
    # Fix extracted_entities -> projects foreign key  
    op.drop_constraint('extracted_entities_project_id_fkey', 'extracted_entities', type_='foreignkey')
    op.create_foreign_key(
        'extracted_entities_project_id_fkey', 'extracted_entities', 'projects',
        ['project_id'], ['id'], ondelete='CASCADE'
    )
    
    # Fix project_shares -> projects foreign key
    op.drop_constraint('project_shares_project_id_fkey', 'project_shares', type_='foreignkey')
    op.create_foreign_key(
        'project_shares_project_id_fkey', 'project_shares', 'projects',
        ['project_id'], ['id'], ondelete='CASCADE'
    )
    
    # Fix public_search_configs -> projects foreign key
    op.drop_constraint('public_search_configs_project_id_fkey', 'public_search_configs', type_='foreignkey')
    op.create_foreign_key(
        'public_search_configs_project_id_fkey', 'public_search_configs', 'projects',
        ['project_id'], ['id'], ondelete='CASCADE'
    )
    
    # Fix scrape_sessions -> projects foreign key
    op.drop_constraint('scrape_sessions_project_id_fkey', 'scrape_sessions', type_='foreignkey')
    op.create_foreign_key(
        'scrape_sessions_project_id_fkey', 'scrape_sessions', 'projects',
        ['project_id'], ['id'], ondelete='CASCADE'
    )
    
    # Fix search_history -> projects foreign key
    op.drop_constraint('search_history_project_id_fkey', 'search_history', type_='foreignkey')
    op.create_foreign_key(
        'search_history_project_id_fkey', 'search_history', 'projects',
        ['project_id'], ['id'], ondelete='CASCADE'
    )
    
    # Fix starred_items -> projects foreign key
    op.drop_constraint('starred_items_project_id_fkey', 'starred_items', type_='foreignkey')
    op.create_foreign_key(
        'starred_items_project_id_fkey', 'starred_items', 'projects',
        ['project_id'], ['id'], ondelete='CASCADE'
    )
    
    # Now handle the cascade chain: domains -> other tables
    # These tables reference domains, so when a domain is deleted (due to project deletion),
    # these records should also be cleaned up
    
    # Fix cdx_resume_states -> domains foreign key
    op.drop_constraint('cdx_resume_states_domain_id_fkey', 'cdx_resume_states', type_='foreignkey')
    op.create_foreign_key(
        'cdx_resume_states_domain_id_fkey', 'cdx_resume_states', 'domains',
        ['domain_id'], ['id'], ondelete='CASCADE'
    )
    
    # Fix incremental_scraping_history -> domains foreign key
    op.drop_constraint('incremental_scraping_history_domain_id_fkey', 'incremental_scraping_history', type_='foreignkey')
    op.create_foreign_key(
        'incremental_scraping_history_domain_id_fkey', 'incremental_scraping_history', 'domains',
        ['domain_id'], ['id'], ondelete='CASCADE'
    )
    
    # Fix pages -> domains foreign key (if pages table still exists and references domains)
    # Note: This may not be needed if using shared pages architecture
    try:
        op.drop_constraint('pages_domain_id_fkey', 'pages', type_='foreignkey')
        op.create_foreign_key(
            'pages_domain_id_fkey', 'pages', 'domains',
            ['domain_id'], ['id'], ondelete='CASCADE'
        )
    except Exception:
        # pages table might not exist or constraint might not exist
        pass


def downgrade() -> None:
    """
    Revert foreign key constraints back to NO ACTION.
    """
    
    # Revert domains -> projects foreign key
    op.drop_constraint('domains_project_id_fkey', 'domains', type_='foreignkey')
    op.create_foreign_key(
        'domains_project_id_fkey', 'domains', 'projects',
        ['project_id'], ['id'], ondelete='NO ACTION'
    )
    
    # Revert extracted_entities -> projects foreign key
    op.drop_constraint('extracted_entities_project_id_fkey', 'extracted_entities', type_='foreignkey')
    op.create_foreign_key(
        'extracted_entities_project_id_fkey', 'extracted_entities', 'projects',
        ['project_id'], ['id'], ondelete='NO ACTION'
    )
    
    # Revert project_shares -> projects foreign key
    op.drop_constraint('project_shares_project_id_fkey', 'project_shares', type_='foreignkey')
    op.create_foreign_key(
        'project_shares_project_id_fkey', 'project_shares', 'projects',
        ['project_id'], ['id'], ondelete='NO ACTION'
    )
    
    # Revert public_search_configs -> projects foreign key
    op.drop_constraint('public_search_configs_project_id_fkey', 'public_search_configs', type_='foreignkey')
    op.create_foreign_key(
        'public_search_configs_project_id_fkey', 'public_search_configs', 'projects',
        ['project_id'], ['id'], ondelete='NO ACTION'
    )
    
    # Revert scrape_sessions -> projects foreign key
    op.drop_constraint('scrape_sessions_project_id_fkey', 'scrape_sessions', type_='foreignkey')
    op.create_foreign_key(
        'scrape_sessions_project_id_fkey', 'scrape_sessions', 'projects',
        ['project_id'], ['id'], ondelete='NO ACTION'
    )
    
    # Revert search_history -> projects foreign key
    op.drop_constraint('search_history_project_id_fkey', 'search_history', type_='foreignkey')
    op.create_foreign_key(
        'search_history_project_id_fkey', 'search_history', 'projects',
        ['project_id'], ['id'], ondelete='NO ACTION'
    )
    
    # Revert starred_items -> projects foreign key  
    op.drop_constraint('starred_items_project_id_fkey', 'starred_items', type_='foreignkey')
    op.create_foreign_key(
        'starred_items_project_id_fkey', 'starred_items', 'projects',
        ['project_id'], ['id'], ondelete='NO ACTION'
    )
    
    # Revert domain cascade constraints
    
    # Revert cdx_resume_states -> domains foreign key
    op.drop_constraint('cdx_resume_states_domain_id_fkey', 'cdx_resume_states', type_='foreignkey')
    op.create_foreign_key(
        'cdx_resume_states_domain_id_fkey', 'cdx_resume_states', 'domains',
        ['domain_id'], ['id'], ondelete='NO ACTION'
    )
    
    # Revert incremental_scraping_history -> domains foreign key
    op.drop_constraint('incremental_scraping_history_domain_id_fkey', 'incremental_scraping_history', type_='foreignkey')
    op.create_foreign_key(
        'incremental_scraping_history_domain_id_fkey', 'incremental_scraping_history', 'domains',
        ['domain_id'], ['id'], ondelete='NO ACTION'
    )
    
    # Revert pages -> domains foreign key (if exists)
    try:
        op.drop_constraint('pages_domain_id_fkey', 'pages', type_='foreignkey')
        op.create_foreign_key(
            'pages_domain_id_fkey', 'pages', 'domains',
            ['domain_id'], ['id'], ondelete='NO ACTION'
        )
    except Exception:
        # pages table might not exist or constraint might not exist
        pass