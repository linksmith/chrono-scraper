"""Implement shared pages architecture with many-to-many relationships

Revision ID: 001_shared_pages_architecture
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_shared_pages_architecture'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade to shared pages architecture"""
    
    # Step 1: Create new independent pages table
    op.create_table(
        'pages_v2',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('unix_timestamp', sa.BigInteger, nullable=False),
        sa.Column('wayback_url', sa.Text, nullable=True),
        sa.Column('content', sa.Text, nullable=True),
        sa.Column('markdown_content', sa.Text, nullable=True),
        sa.Column('extracted_data', postgresql.JSONB, nullable=True),
        sa.Column('quality_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        
        # Enhanced metadata fields
        sa.Column('title', sa.String(500), nullable=True),
        sa.Column('extracted_title', sa.String(500), nullable=True),
        sa.Column('extracted_text', sa.Text, nullable=True),
        sa.Column('meta_description', sa.Text, nullable=True),
        sa.Column('meta_keywords', sa.Text, nullable=True),
        sa.Column('author', sa.String(255), nullable=True),
        sa.Column('published_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('language', sa.String(10), nullable=True),
        sa.Column('word_count', sa.Integer, nullable=True),
        sa.Column('character_count', sa.Integer, nullable=True),
        sa.Column('content_type', sa.String(100), nullable=True),
        sa.Column('content_length', sa.Integer, nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('status_code', sa.Integer, nullable=True),
        sa.Column('capture_date', sa.DateTime(timezone=True), nullable=True),
        
        # Content processing
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('processed', sa.Boolean, default=False),
        sa.Column('indexed', sa.Boolean, default=False),
        
        # Error tracking
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('retry_count', sa.Integer, default=0),
        sa.Column('last_retry_at', sa.DateTime(timezone=True), nullable=True),
        
        # Global deduplication constraint
        sa.UniqueConstraint('url', 'unix_timestamp', name='uq_pages_v2_url_timestamp'),
        
        # Performance indexes
        sa.Index('idx_pages_v2_url', 'url'),
        sa.Index('idx_pages_v2_timestamp', 'unix_timestamp'),
        sa.Index('idx_pages_v2_url_timestamp', 'url', 'unix_timestamp'),
        sa.Index('idx_pages_v2_processed', 'processed'),
        sa.Index('idx_pages_v2_indexed', 'indexed'),
    )
    
    # Step 2: Create junction table for many-to-many relationship
    op.create_table(
        'project_pages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', sa.Integer, sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('page_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pages_v2.id', ondelete='CASCADE'), nullable=False),
        sa.Column('domain_id', sa.Integer, sa.ForeignKey('domains.id', ondelete='SET NULL'), nullable=True),
        
        # Project-specific metadata
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('added_by', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('review_status', sa.String(50), default='pending'),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.Text), default=[]),
        sa.Column('is_starred', sa.Boolean, default=False),
        
        # Page management fields (project-specific)
        sa.Column('page_category', sa.String(20), nullable=True),
        sa.Column('priority_level', sa.String(20), default='medium'),
        sa.Column('review_notes', sa.Text, nullable=True),
        sa.Column('quick_notes', sa.String(500), nullable=True),
        sa.Column('is_duplicate', sa.Boolean, default=False),
        sa.Column('duplicate_of_page_id', postgresql.UUID(as_uuid=True), nullable=True),
        
        # Review tracking
        sa.Column('reviewed_by', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        
        # Prevent duplicate associations
        sa.UniqueConstraint('project_id', 'page_id', name='uq_project_pages_project_page'),
        
        # Performance indexes
        sa.Index('idx_pp_project', 'project_id'),
        sa.Index('idx_pp_page', 'page_id'),
        sa.Index('idx_pp_project_starred', 'project_id', 'is_starred'),
        sa.Index('idx_pp_review_status', 'review_status'),
        sa.Index('idx_pp_domain', 'domain_id'),
    )
    
    # Step 3: Create CDX deduplication registry
    op.create_table(
        'cdx_page_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('unix_timestamp', sa.BigInteger, nullable=False),
        sa.Column('page_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pages_v2.id'), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('scrape_status', sa.String(50), nullable=False),  # 'pending', 'in_progress', 'completed', 'failed'
        sa.Column('created_by_project_id', sa.Integer, sa.ForeignKey('projects.id'), nullable=True),
        
        # Deduplication constraint
        sa.UniqueConstraint('url', 'unix_timestamp', name='uq_cdx_registry_url_timestamp'),
        
        # Performance indexes
        sa.Index('idx_cpr_status', 'scrape_status'),
        sa.Index('idx_cpr_url_time', 'url', 'unix_timestamp'),
        sa.Index('idx_cpr_page_id', 'page_id'),
    )
    
    # Step 4: Fix CASCADE constraints on existing tables
    op.drop_constraint('domains_project_id_fkey', 'domains', type_='foreignkey')
    op.create_foreign_key(
        'domains_project_id_fkey',
        'domains', 'projects',
        ['project_id'], ['id'],
        ondelete='CASCADE'
    )
    
    op.drop_constraint('pages_domain_id_fkey', 'pages', type_='foreignkey')
    op.create_foreign_key(
        'pages_domain_id_fkey',
        'pages', 'domains',
        ['domain_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade from shared pages architecture"""
    
    # Remove new tables
    op.drop_table('cdx_page_registry')
    op.drop_table('project_pages')
    op.drop_table('pages_v2')
    
    # Restore original CASCADE constraints
    op.drop_constraint('domains_project_id_fkey', 'domains', type_='foreignkey')
    op.create_foreign_key(
        'domains_project_id_fkey',
        'domains', 'projects',
        ['project_id'], ['id'],
        ondelete='NO ACTION'
    )
    
    op.drop_constraint('pages_domain_id_fkey', 'pages', type_='foreignkey')
    op.create_foreign_key(
        'pages_domain_id_fkey',
        'pages', 'domains',
        ['domain_id'], ['id'],
        ondelete='NO ACTION'
    )