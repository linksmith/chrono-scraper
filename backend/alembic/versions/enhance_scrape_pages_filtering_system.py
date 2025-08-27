"""Add enhanced filtering system to scrape_pages

Revision ID: enhance_scrape_pages_filtering_system
Revises: 66fcf1690d1f
Create Date: 2025-08-27 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'enhance_filtering_system'
down_revision: Union[str, None] = '66fcf1690d1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add enhanced filtering system fields to scrape_pages table"""
    print("🔧 Upgrading ScrapePage model with enhanced filtering system...")
    
    # Add new filtering system fields
    print("  ➡️ Adding filtering system fields...")
    op.add_column('scrape_pages', sa.Column('filter_reason', sa.String(length=100), nullable=True))
    op.add_column('scrape_pages', sa.Column('filter_category', sa.String(length=50), nullable=True))
    op.add_column('scrape_pages', sa.Column('filter_details', sa.Text(), nullable=True))
    op.add_column('scrape_pages', sa.Column('is_manually_overridden', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('scrape_pages', sa.Column('original_filter_decision', sa.String(length=100), nullable=True))
    op.add_column('scrape_pages', sa.Column('priority_score', sa.Integer(), nullable=True, server_default='5'))
    op.add_column('scrape_pages', sa.Column('can_be_manually_processed', sa.Boolean(), nullable=False, server_default='true'))
    
    # Add foreign key reference to pages table for successful scraping results
    print("  ➡️ Adding page_id foreign key...")
    op.add_column('scrape_pages', sa.Column('page_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_scrape_pages_page_id', 'scrape_pages', 'pages', ['page_id'], ['id'], ondelete='SET NULL')
    
    # Extend status column to accommodate longer filtering status names
    print("  ➡️ Extending status column for new filtering statuses...")
    op.alter_column('scrape_pages', 'status',
               existing_type=sa.String(20),
               type_=sa.String(30),
               existing_nullable=True)
    
    # Create performance indexes for filtering queries
    print("  ➡️ Creating indexes for filtering performance...")
    
    # Index for filtering by category and reason
    op.create_index('ix_scrape_pages_filter_category', 'scrape_pages', ['filter_category'])
    op.create_index('ix_scrape_pages_filter_reason', 'scrape_pages', ['filter_reason'])
    
    # Composite index for filtering queries with status
    op.create_index('ix_scrape_pages_status_filter_category', 'scrape_pages', ['status', 'filter_category'])
    
    # Index for manual override queries
    op.create_index('ix_scrape_pages_manual_override', 'scrape_pages', ['is_manually_overridden', 'can_be_manually_processed'])
    
    # Index for priority-based queries
    op.create_index('ix_scrape_pages_priority_score', 'scrape_pages', ['priority_score'])
    
    # Composite index for efficient filtering dashboard queries
    op.create_index('ix_scrape_pages_filtering_dashboard', 'scrape_pages', 
                   ['domain_id', 'status', 'filter_category', 'priority_score'])
    
    # Index for page relationship queries
    op.create_index('ix_scrape_pages_page_id', 'scrape_pages', ['page_id'])
    
    # Data migration: Set default values for existing records
    print("  ➡️ Setting default values for existing records...")
    
    # Set default priority_score for existing records (already handled by server_default)
    # Set default flags for existing records (already handled by server_default)
    
    # Update priority scores based on existing flags for better initial filtering
    op.execute(text("""
        UPDATE scrape_pages 
        SET priority_score = 
            CASE 
                WHEN is_duplicate = true THEN 2
                WHEN is_list_page = true THEN 3
                WHEN is_pdf = true AND content_length > 1000000 THEN 8  -- Large PDFs are high priority
                WHEN mime_type LIKE 'application/pdf' THEN 7
                WHEN mime_type LIKE 'text/html' THEN 6
                ELSE 5
            END
        WHERE priority_score IS NULL OR priority_score = 5;
    """))
    
    # Set initial filter categories based on existing flags
    op.execute(text("""
        UPDATE scrape_pages 
        SET filter_category = 
            CASE 
                WHEN is_duplicate = true THEN 'duplicate'
                WHEN is_list_page = true THEN 'list_page'
                WHEN is_pdf = true THEN 'document'
                ELSE NULL
            END,
            filter_reason = 
            CASE 
                WHEN is_duplicate = true THEN 'Content hash duplication detected'
                WHEN is_list_page = true THEN 'Identified as navigation/list page'
                WHEN is_pdf = true THEN 'PDF document detected'
                ELSE NULL
            END
        WHERE filter_category IS NULL;
    """))
    
    print("✅ Enhanced filtering system successfully added to scrape_pages!")


def downgrade() -> None:
    """Remove enhanced filtering system fields from scrape_pages table"""
    print("🔄 Downgrading ScrapePage model - removing enhanced filtering system...")
    
    # Drop indexes
    print("  ➡️ Dropping indexes...")
    op.drop_index('ix_scrape_pages_filtering_dashboard', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_priority_score', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_manual_override', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_status_filter_category', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_filter_reason', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_filter_category', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_page_id', table_name='scrape_pages')
    
    # Drop foreign key and column
    print("  ➡️ Removing page_id foreign key...")
    op.drop_constraint('fk_scrape_pages_page_id', 'scrape_pages', type_='foreignkey')
    op.drop_column('scrape_pages', 'page_id')
    
    # Remove filtering system fields
    print("  ➡️ Removing filtering system fields...")
    op.drop_column('scrape_pages', 'can_be_manually_processed')
    op.drop_column('scrape_pages', 'priority_score')
    op.drop_column('scrape_pages', 'original_filter_decision')
    op.drop_column('scrape_pages', 'is_manually_overridden')
    op.drop_column('scrape_pages', 'filter_details')
    op.drop_column('scrape_pages', 'filter_category')
    op.drop_column('scrape_pages', 'filter_reason')
    
    # Revert status column to original size
    print("  ➡️ Reverting status column size...")
    op.alter_column('scrape_pages', 'status',
               existing_type=sa.String(30),
               type_=sa.String(20),
               existing_nullable=True)
    
    print("✅ Enhanced filtering system successfully removed from scrape_pages!")