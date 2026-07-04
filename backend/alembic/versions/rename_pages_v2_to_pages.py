"""Rename pages_v2 table to pages

Revision ID: rename_pages_v2
Revises: 4d3a2c03ebf3
Create Date: 2026-02-06

Completes migration from PageV2 → Page by renaming the DB table.
"""
from alembic import op

# revision identifiers
revision = 'rename_pages_v2'
down_revision = '4d3a2c03ebf3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop FK constraints that reference pages_v2
    op.drop_constraint('project_pages_page_id_fkey', 'project_pages', type_='foreignkey')
    op.drop_constraint('cdx_page_registry_page_id_fkey', 'cdx_page_registry', type_='foreignkey')

    # 2. Rename table
    op.rename_table('pages_v2', 'pages')

    # 3. Rename PK constraint and its backing index
    op.execute('ALTER INDEX pages_v2_pkey RENAME TO pages_pkey')

    # 4. Rename unique constraint (which is also an index in PostgreSQL)
    op.execute('ALTER INDEX uq_pages_v2_url_timestamp RENAME TO uq_pages_url_timestamp')

    # 5. Recreate FK constraints pointing to new table name
    op.create_foreign_key(
        'project_pages_page_id_fkey', 'project_pages', 'pages',
        ['page_id'], ['id']
    )
    op.create_foreign_key(
        'cdx_page_registry_page_id_fkey', 'cdx_page_registry', 'pages',
        ['page_id'], ['id']
    )


def downgrade() -> None:
    # 1. Drop FK constraints
    op.drop_constraint('project_pages_page_id_fkey', 'project_pages', type_='foreignkey')
    op.drop_constraint('cdx_page_registry_page_id_fkey', 'cdx_page_registry', type_='foreignkey')

    # 2. Rename table back
    op.rename_table('pages', 'pages_v2')

    # 3. Rename PK constraint and its backing index back
    op.execute('ALTER INDEX pages_pkey RENAME TO pages_v2_pkey')

    # 4. Rename unique constraint back
    op.execute('ALTER INDEX uq_pages_url_timestamp RENAME TO uq_pages_v2_url_timestamp')

    # 5. Recreate FK constraints pointing to old table name
    op.create_foreign_key(
        'project_pages_page_id_fkey', 'project_pages', 'pages_v2',
        ['page_id'], ['id']
    )
    op.create_foreign_key(
        'cdx_page_registry_page_id_fkey', 'cdx_page_registry', 'pages_v2',
        ['page_id'], ['id']
    )
