"""Enhance filtering system with individual reasons and structured data

Revision ID: enhance_filtering_individual_reasons
Revises: enhance_filtering_system
Create Date: 2025-08-27 02:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'enhance_filtering_individual'
down_revision: Union[str, None] = 'enhance_filtering_system'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enhance filtering system with individual reasons and structured JSON data"""
    print("🔧 Enhancing filtering system with individual reasons...")
    
    # Step 1: Add new fields for individual filtering reasons (only if they don't exist)
    print("  ➡️ Adding individual reason tracking fields...")
    
    # Check if columns already exist before adding
    conn = op.get_bind()
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'scrape_pages' 
        AND column_name IN ('matched_pattern', 'filter_confidence', 'related_page_id')
    """))
    existing_columns = [row[0] for row in result]
    
    if 'matched_pattern' not in existing_columns:
        op.add_column('scrape_pages', sa.Column('matched_pattern', sa.String(length=200), nullable=True))
    if 'filter_confidence' not in existing_columns:
        op.add_column('scrape_pages', sa.Column('filter_confidence', sa.Float(), nullable=True))
    if 'related_page_id' not in existing_columns:
        op.add_column('scrape_pages', sa.Column('related_page_id', sa.Integer(), nullable=True))
    
    # Step 2: Convert filter_details from Text to JSONB
    print("  ➡️ Converting filter_details to JSONB for structured data...")
    
    # First, rename the existing text column
    op.alter_column('scrape_pages', 'filter_details', new_column_name='filter_details_old')
    
    # Add a new JSONB column
    op.add_column('scrape_pages', sa.Column('filter_details', 
                                            postgresql.JSONB(astext_type=sa.Text()), 
                                            nullable=True))
    
    # Migrate existing text data to JSONB structure
    print("  ➡️ Migrating existing filter_details to structured JSONB...")
    op.execute(text("""
        UPDATE scrape_pages 
        SET filter_details = 
            CASE 
                WHEN filter_details_old IS NOT NULL AND filter_details_old != '' THEN 
                    jsonb_build_object(
                        'reason_text', filter_details_old,
                        'filter_type', filter_category,
                        'timestamp', NOW(),
                        'migration_note', 'Migrated from text field'
                    )
                ELSE NULL
            END
    """))
    
    # Drop the old text column
    op.drop_column('scrape_pages', 'filter_details_old')
    
    # Step 3: Update existing data with specific filtering patterns
    print("  ➡️ Populating specific filtering patterns for existing data...")
    
    # For list pages, identify the specific pattern that would have matched
    op.execute(text("""
        UPDATE scrape_pages 
        SET matched_pattern = 
            CASE 
                WHEN original_url LIKE '%/blog/%' THEN '/blog/'
                WHEN original_url LIKE '%/category/%' THEN '/category/'
                WHEN original_url LIKE '%/page/%' THEN '/page/\\d+'
                WHEN original_url LIKE '%/tag/%' THEN '/tag/'
                WHEN original_url LIKE '%/archive/%' THEN '/archive/'
                WHEN original_url LIKE '%/index.html%' THEN '/index\\.html?$'
                WHEN original_url LIKE '%?page=%' THEN '\\?page=\\d+'
                WHEN original_url LIKE '%&page=%' THEN '&page=\\d+'
                WHEN original_url LIKE '%.pdf' THEN '\\.pdf$'
                WHEN original_url LIKE '%.doc%' THEN '\\.doc[x]?$'
                ELSE 'generic_pattern'
            END,
        filter_confidence = 
            CASE
                WHEN is_list_page = true THEN 0.9
                WHEN is_duplicate = true THEN 1.0
                WHEN is_pdf = true THEN 1.0
                ELSE 0.7
            END
        WHERE (is_list_page = true OR is_duplicate = true OR is_pdf = true)
        AND matched_pattern IS NULL;
    """))
    
    # Step 4: Enhanced status migration for existing records
    print("  ➡️ Updating statuses with more specific filtering statuses...")
    op.execute(text("""
        UPDATE scrape_pages 
        SET status = 
            CASE 
                WHEN status = 'filtered_duplicate' OR is_duplicate = true THEN 'filtered_already_processed'
                WHEN status = 'filtered_list_page' OR is_list_page = true THEN 'filtered_list_page'
                WHEN status = 'filtered_type' AND mime_type LIKE 'application/pdf' THEN 'filtered_attachment_disabled'
                WHEN status = 'filtered_size' AND content_length < 1000 THEN 'filtered_size_too_small'
                WHEN status = 'filtered_size' AND content_length > 10485760 THEN 'filtered_size_too_large'
                WHEN status = 'filtered_custom' THEN 'filtered_custom_rule'
                ELSE status
            END
        WHERE status LIKE 'filtered_%';
    """))
    
    # Step 5: Create comprehensive filter_details for existing records
    print("  ➡️ Creating detailed filter_details for all existing filtered records...")
    op.execute(text("""
        UPDATE scrape_pages 
        SET filter_details = jsonb_build_object(
            'filter_timestamp', created_at,
            'original_url', original_url,
            'matched_pattern', COALESCE(matched_pattern, 'not_specified'),
            'confidence_score', COALESCE(filter_confidence, 0.5),
            'filter_type', 
                CASE 
                    WHEN status = 'filtered_list_page' THEN 'list_page_detection'
                    WHEN status = 'filtered_already_processed' THEN 'duplicate_content'
                    WHEN status = 'filtered_attachment_disabled' THEN 'attachment_filtering'
                    WHEN status LIKE 'filtered_size_%' THEN 'size_filtering'
                    ELSE 'general_filtering'
                END,
            'specific_reason',
                CASE
                    WHEN status = 'filtered_list_page' AND original_url LIKE '%/blog/page/%' THEN 
                        'Blog pagination page detected - Pattern: /blog/page/[number]'
                    WHEN status = 'filtered_list_page' AND original_url LIKE '%/category/%' THEN 
                        'Category listing page detected - Pattern: /category/[name]'
                    WHEN status = 'filtered_list_page' AND original_url LIKE '%?page=%' THEN 
                        'Query parameter pagination detected - Pattern: ?page=[number]'
                    WHEN status = 'filtered_already_processed' THEN 
                        'Content with digest ' || SUBSTRING(digest_hash, 1, 8) || '... already processed'
                    WHEN status = 'filtered_attachment_disabled' AND mime_type = 'application/pdf' THEN 
                        'PDF attachment excluded - Project attachments disabled'
                    WHEN status = 'filtered_size_too_small' THEN 
                        'Content size ' || content_length || ' bytes below minimum threshold (1KB)'
                    WHEN status = 'filtered_size_too_large' THEN 
                        'Content size ' || content_length || ' bytes exceeds maximum threshold (10MB)'
                    ELSE 'Filtered based on intelligent detection rules'
                END,
            'content_metadata', jsonb_build_object(
                'mime_type', mime_type,
                'content_length', content_length,
                'status_code', status_code,
                'capture_timestamp', unix_timestamp
            )
        )
        WHERE status LIKE 'filtered_%' AND filter_details IS NULL;
    """))
    
    # Step 6: Create indexes for the new fields
    print("  ➡️ Creating indexes for new fields...")
    op.create_index('ix_scrape_pages_matched_pattern', 'scrape_pages', ['matched_pattern'])
    op.create_index('ix_scrape_pages_filter_confidence', 'scrape_pages', ['filter_confidence'])
    op.create_index('ix_scrape_pages_related_page_id', 'scrape_pages', ['related_page_id'])
    
    # Add GIN index for JSONB searching
    op.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_scrape_pages_filter_details_gin 
        ON scrape_pages USING gin (filter_details jsonb_path_ops)
        WHERE filter_details IS NOT NULL;
    """))
    
    # Step 7: Add foreign key constraint for related_page_id
    print("  ➡️ Adding foreign key constraint for related_page_id...")
    op.create_foreign_key('fk_scrape_pages_related_page', 
                         'scrape_pages', 'pages', 
                         ['related_page_id'], ['id'], 
                         ondelete='SET NULL')
    
    # Step 8: Update statistics
    print("  ➡️ Analyzing table for query optimization...")
    op.execute(text("ANALYZE scrape_pages;"))
    
    print("✅ Enhanced filtering system with individual reasons successfully implemented!")
    
    # Print migration summary
    result = op.get_bind().execute(text("""
        SELECT 
            status,
            COUNT(*) as count,
            CASE 
                WHEN filter_details IS NOT NULL THEN 'Has Details'
                ELSE 'No Details'
            END as detail_status
        FROM scrape_pages 
        WHERE status LIKE 'filtered_%'
        GROUP BY status, detail_status
        ORDER BY status;
    """))
    
    print("\n📊 Migration Summary:")
    print("=" * 60)
    for row in result:
        print(f"  {row.status}: {row.count} records ({row.detail_status})")
    print("=" * 60)


def downgrade() -> None:
    """Revert enhancements to filtering system"""
    print("🔄 Reverting filtering system enhancements...")
    
    # Drop foreign key constraint
    print("  ➡️ Dropping foreign key constraint...")
    op.drop_constraint('fk_scrape_pages_related_page', 'scrape_pages', type_='foreignkey')
    
    # Drop indexes
    print("  ➡️ Dropping indexes...")
    op.execute(text("DROP INDEX IF EXISTS ix_scrape_pages_filter_details_gin;"))
    op.drop_index('ix_scrape_pages_related_page_id', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_filter_confidence', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_matched_pattern', table_name='scrape_pages')
    
    # Convert filter_details back to Text
    print("  ➡️ Converting filter_details back to Text...")
    op.add_column('scrape_pages', sa.Column('filter_details_text', sa.Text(), nullable=True))
    
    # Extract text from JSON
    op.execute(text("""
        UPDATE scrape_pages 
        SET filter_details_text = filter_details->>'reason_text'
        WHERE filter_details IS NOT NULL;
    """))
    
    op.drop_column('scrape_pages', 'filter_details')
    op.alter_column('scrape_pages', 'filter_details_text', new_column_name='filter_details')
    
    # Remove new fields
    print("  ➡️ Removing individual reason tracking fields...")
    op.drop_column('scrape_pages', 'related_page_id')
    op.drop_column('scrape_pages', 'filter_confidence')
    op.drop_column('scrape_pages', 'matched_pattern')
    
    # Revert status changes
    print("  ➡️ Reverting status changes...")
    op.execute(text("""
        UPDATE scrape_pages 
        SET status = 
            CASE 
                WHEN status = 'filtered_already_processed' THEN 'filtered_duplicate'
                WHEN status IN ('filtered_size_too_small', 'filtered_size_too_large') THEN 'filtered_size'
                WHEN status = 'filtered_attachment_disabled' THEN 'filtered_type'
                WHEN status = 'filtered_custom_rule' THEN 'filtered_custom'
                ELSE status
            END
        WHERE status LIKE 'filtered_%';
    """))
    
    print("✅ Filtering system enhancements successfully reverted!")