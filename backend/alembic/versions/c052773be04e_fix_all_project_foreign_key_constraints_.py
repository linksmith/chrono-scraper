"""Fix all project foreign key constraints for CASCADE deletion

This migration ensures that when a project is deleted, all related records
are automatically cleaned up to prevent foreign key constraint violations.

The following constraints are updated from NO ACTION to CASCADE:
- cdx_page_registry.created_by_project_id -> projects.id
- extracted_entities.project_id -> projects.id  
- meilisearch_keys.project_id -> projects.id
- project_shares.project_id -> projects.id
- public_search_configs.project_id -> projects.id
- scrape_sessions.project_id -> projects.id
- search_history.project_id -> projects.id

Note: domains and project_pages already have CASCADE, starred_items was fixed in previous migration

Revision ID: c052773be04e
Revises: 808a9cae928e
Create Date: 2025-08-22 22:23:56.876143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c052773be04e'
down_revision: Union[str, None] = '808a9cae928e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # List of constraints to update (table_name, constraint_name, column_name)
    constraints_to_fix = [
        ('cdx_page_registry', 'cdx_page_registry_created_by_project_id_fkey', 'created_by_project_id'),
        ('extracted_entities', 'extracted_entities_project_id_fkey', 'project_id'),
        ('meilisearch_keys', 'meilisearch_keys_project_id_fkey', 'project_id'),
        ('project_shares', 'project_shares_project_id_fkey', 'project_id'),
        ('public_search_configs', 'public_search_configs_project_id_fkey', 'project_id'),
        ('scrape_sessions', 'scrape_sessions_project_id_fkey', 'project_id'),
        ('search_history', 'search_history_project_id_fkey', 'project_id'),
    ]
    
    for table_name, constraint_name, column_name in constraints_to_fix:
        # Drop the existing constraint
        op.drop_constraint(constraint_name, table_name, type_='foreignkey')
        
        # Add the constraint with CASCADE deletion
        op.create_foreign_key(
            constraint_name,
            table_name,
            'projects',
            [column_name],
            ['id'],
            ondelete='CASCADE'
        )


def downgrade() -> None:
    # Revert all constraints back to NO ACTION
    constraints_to_revert = [
        ('cdx_page_registry', 'cdx_page_registry_created_by_project_id_fkey', 'created_by_project_id'),
        ('extracted_entities', 'extracted_entities_project_id_fkey', 'project_id'),
        ('meilisearch_keys', 'meilisearch_keys_project_id_fkey', 'project_id'),
        ('project_shares', 'project_shares_project_id_fkey', 'project_id'),
        ('public_search_configs', 'public_search_configs_project_id_fkey', 'project_id'),
        ('scrape_sessions', 'scrape_sessions_project_id_fkey', 'project_id'),
        ('search_history', 'search_history_project_id_fkey', 'project_id'),
    ]
    
    for table_name, constraint_name, column_name in constraints_to_revert:
        # Drop the CASCADE constraint
        op.drop_constraint(constraint_name, table_name, type_='foreignkey')
        
        # Add back the original constraint without CASCADE
        op.create_foreign_key(
            constraint_name,
            table_name,
            'projects',
            [column_name],
            ['id']
        )