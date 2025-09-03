"""Add CASCADE delete to meilisearch_keys foreign key

Revision ID: add_cascade_meilisearch_keys
Revises: 22b334af81f5
Create Date: 2025-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'add_cascade_meilisearch_keys'
down_revision: Union[str, None] = '22b334af81f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add CASCADE DELETE to meilisearch_keys foreign key (only if table exists)
    from sqlalchemy import text
    from alembic import op

    # Check if table exists
    conn = op.get_bind()
    result = conn.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'meilisearch_keys')"))
    table_exists = result.scalar()

    if table_exists:
        # Drop existing constraint if it exists
        try:
            op.drop_constraint('meilisearch_keys_project_id_fkey', 'meilisearch_keys', type_='foreignkey')
        except:
            pass  # Constraint might not exist

        # Create new constraint with CASCADE DELETE
        op.create_foreign_key('meilisearch_keys_project_id_fkey', 'meilisearch_keys', 'projects',
                             ['project_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Revert back to NO ACTION constraint (only if table exists)
    from sqlalchemy import text

    # Check if table exists
    conn = op.get_bind()
    result = conn.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'meilisearch_keys')"))
    table_exists = result.scalar()

    if table_exists:
        try:
            op.drop_constraint('meilisearch_keys_project_id_fkey', 'meilisearch_keys', type_='foreignkey')
        except:
            pass  # Constraint might not exist

        op.create_foreign_key('meilisearch_keys_project_id_fkey', 'meilisearch_keys', 'projects',
                             ['project_id'], ['id'], ondelete='NO ACTION')
