"""Drop legacy pages table and related constraints

Revision ID: drop_legacy_pages_table
Revises: 054763a38e19
Create Date: 2025-09-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'drop_legacy_pages_table'
down_revision: Union[str, None] = '054763a38e19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop legacy pages table and all related constraints"""
    
    # Drop foreign key constraints that reference pages table
    try:
        # Drop starred_items page_id foreign key if exists
        op.drop_constraint('starred_items_page_id_fkey', 'starred_items', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    # Drop starred_items page_id column if exists
    try:
        op.drop_column('starred_items', 'page_id')
    except Exception:
        pass  # Column might not exist
    
    # Drop any other foreign key constraints that might reference pages
    try:
        op.execute("DO $$ DECLARE r RECORD; BEGIN FOR r IN SELECT constraint_name, table_name FROM information_schema.table_constraints WHERE constraint_type = 'FOREIGN KEY' AND constraint_name LIKE '%page%' AND table_schema = 'public' LOOP EXECUTE 'ALTER TABLE ' || r.table_name || ' DROP CONSTRAINT IF EXISTS ' || r.constraint_name || ' CASCADE'; END LOOP; END $$;")
    except Exception:
        pass  # Some constraints might not exist
    
    # Drop the pages table if it exists
    try:
        op.drop_table('pages')
    except Exception:
        pass  # Table might not exist
    
    # Drop any indexes related to pages table
    try:
        op.execute("DROP INDEX IF EXISTS idx_pages_domain_id CASCADE;")
        op.execute("DROP INDEX IF EXISTS idx_pages_original_url CASCADE;")
        op.execute("DROP INDEX IF EXISTS idx_pages_unix_timestamp CASCADE;")
        op.execute("DROP INDEX IF EXISTS uq_pages_domain_url_ts CASCADE;")
    except Exception:
        pass  # Indexes might not exist


def downgrade() -> None:
    """Recreate pages table structure (without data)"""
    
    # Note: This only recreates the table structure, not the data
    # Data migration should be handled separately if needed
    
    op.create_table('pages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain_id', sa.Integer(), nullable=False),
        sa.Column('original_url', sa.Text(), nullable=False),
        sa.Column('content_url', sa.Text(), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('unix_timestamp', sa.String(length=14), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('extracted_title', sa.String(length=500), nullable=True),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.Column('meta_description', sa.Text(), nullable=True),
        sa.Column('meta_keywords', sa.Text(), nullable=True),
        sa.Column('author', sa.String(length=255), nullable=True),
        sa.Column('published_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('character_count', sa.Integer(), nullable=True),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('content_length', sa.Integer(), nullable=True),
        sa.Column('capture_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_status', sa.String(length=20), nullable=False, server_default='unreviewed'),
        sa.Column('page_category', sa.String(length=20), nullable=True),
        sa.Column('priority_level', sa.String(length=20), nullable=False, server_default='medium'),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('quick_notes', sa.String(length=500), nullable=True),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('is_duplicate', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('duplicate_of_page_id', sa.Integer(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('indexed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('content_embedding', sa.Text(), nullable=True),
        sa.Column('embedding_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scraped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain_id', 'original_url', 'unix_timestamp', name='uq_pages_domain_url_ts')
    )
    
    # Recreate page_id column in starred_items
    op.add_column('starred_items', sa.Column('page_id', sa.Integer(), nullable=True))
    op.create_foreign_key('starred_items_page_id_fkey', 'starred_items', 'pages', ['page_id'], ['id'])