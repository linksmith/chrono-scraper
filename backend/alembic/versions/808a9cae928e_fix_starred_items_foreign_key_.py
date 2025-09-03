"""Fix starred_items foreign key constraints for CASCADE deletion

This migration fixes a critical issue where starred_items were not being automatically
deleted when their referenced pages or projects were deleted, causing foreign key
constraint violations during project deletion.

Changes:
- starred_items.page_id -> pages.id: Added ON DELETE CASCADE
- starred_items.project_id -> projects.id: Added ON DELETE CASCADE
- starred_items.user_id -> users.id: Remains NO ACTION (preserve starred items when user exists)

This ensures that when pages or projects are deleted, their associated starred items
are automatically cleaned up, preventing the constraint violation:
"update or delete on table "pages" violates foreign key constraint "starred_items_page_id_fkey""

Revision ID: 808a9cae928e
Revises: 92a71f970a5a
Create Date: 2025-08-22 22:04:48.809359

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '808a9cae928e'
down_revision: Union[str, None] = '92a71f970a5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the existing foreign key constraint without CASCADE
    op.drop_constraint('starred_items_page_id_fkey', 'starred_items', type_='foreignkey')
    
    # Add the new foreign key constraint with CASCADE deletion
    op.create_foreign_key(
        'starred_items_page_id_fkey',
        'starred_items', 
        'pages',
        ['page_id'], 
        ['id'],
        ondelete='CASCADE'
    )
    
    # Also fix the project_id foreign key constraint to CASCADE
    op.drop_constraint('starred_items_project_id_fkey', 'starred_items', type_='foreignkey')
    
    op.create_foreign_key(
        'starred_items_project_id_fkey',
        'starred_items', 
        'projects',
        ['project_id'], 
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Revert to the original constraints without CASCADE
    op.drop_constraint('starred_items_page_id_fkey', 'starred_items', type_='foreignkey')
    
    op.create_foreign_key(
        'starred_items_page_id_fkey',
        'starred_items', 
        'pages',
        ['page_id'], 
        ['id']
    )
    
    op.drop_constraint('starred_items_project_id_fkey', 'starred_items', type_='foreignkey')
    
    op.create_foreign_key(
        'starred_items_project_id_fkey',
        'starred_items', 
        'projects',
        ['project_id'], 
        ['id']
    )