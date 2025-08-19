"""Remove redundant content columns from pages table

Revision ID: remove_redundant_content
Revises: 
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'remove_redundant_content'
down_revision = 'merge_change_unix_ts_with_heads'
branch_labels = None
depends_on = None


def upgrade():
    """Remove redundant content columns and optimize storage"""
    
    # Create migration log table if it doesn't exist
    op.execute("""
        CREATE TABLE IF NOT EXISTS migration_log (
            id SERIAL PRIMARY KEY,
            migration_name VARCHAR(255) NOT NULL,
            step VARCHAR(255) NOT NULL,
            data JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # Step 1: Audit current data distribution
    op.execute("""
        WITH content_audit AS (
            SELECT 
                COUNT(*) as total_pages,
                COUNT(content) as has_content,
                COUNT(extracted_content) as has_extracted_content,
                COUNT(extracted_text) as has_extracted_text,
                ROUND(AVG(LENGTH(content))) as avg_content_length,
                ROUND(AVG(LENGTH(extracted_content))) as avg_extracted_content_length,
                ROUND(AVG(LENGTH(extracted_text))) as avg_extracted_text_length
            FROM pages
        )
        INSERT INTO migration_log (migration_name, step, data) 
        SELECT 'remove_redundant_content', 'pre_migration_audit', 
               to_jsonb(content_audit.*) 
        FROM content_audit
    """)
    
    # Step 2: Ensure extracted_text is populated where content exists
    op.execute("""
        UPDATE pages 
        SET extracted_text = COALESCE(
            extracted_text,
            extracted_content, 
            CASE 
                WHEN mime_type = 'text/html' THEN regexp_replace(content, '<[^>]*>', '', 'g')
                ELSE content 
            END
        )
        WHERE extracted_text IS NULL 
          AND (extracted_content IS NOT NULL OR content IS NOT NULL)
    """)
    
    # Step 3: Create backup table for rollback purposes
    op.execute("""
        DROP TABLE IF EXISTS pages_content_backup;
        CREATE TABLE pages_content_backup AS 
        SELECT id, content, extracted_content
        FROM pages 
        WHERE content IS NOT NULL 
           OR extracted_content IS NOT NULL
    """)
    
    # Step 4: Drop redundant columns
    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.drop_column('content')
        batch_op.drop_column('extracted_content')
    
    # Step 5: Optimize storage for remaining text column
    op.execute("ALTER TABLE pages ALTER COLUMN extracted_text SET STORAGE EXTENDED")
    
    # Step 6: Update indexes - drop old ones if they exist
    op.execute("DROP INDEX IF EXISTS idx_pages_content")
    op.execute("DROP INDEX IF EXISTS idx_pages_extracted_content")
    op.execute("DROP INDEX IF EXISTS idx_pages_markdown_content")
    
    # Create new optimized index
    op.create_index('idx_pages_extracted_text_exists', 'pages', ['id'], 
                   postgresql_where=sa.text('extracted_text IS NOT NULL'))
    
    # Optional: Create GIN index for full-text search (PostgreSQL backup)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_pages_extracted_text_fts 
        ON pages USING gin(to_tsvector('english', extracted_text)) 
        WHERE extracted_text IS NOT NULL
    """)
    
    # Step 7: Final audit and log results
    op.execute("""
        WITH final_audit AS (
            SELECT 
                COUNT(*) as total_pages,
                COUNT(extracted_text) as has_extracted_text,
                ROUND(AVG(LENGTH(extracted_text))) as avg_extracted_text_length,
                (SELECT pg_size_pretty(pg_total_relation_size('pages_content_backup'))) as backup_size,
                (SELECT pg_size_pretty(pg_total_relation_size('pages'))) as current_size
            FROM pages
        )
        INSERT INTO migration_log (migration_name, step, data)
        SELECT 'remove_redundant_content', 'post_migration_audit', 
               to_jsonb(final_audit.*)
        FROM final_audit
    """)


def downgrade():
    """Restore redundant content columns from backup"""
    
    # Add columns back
    with op.batch_alter_table('pages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('extracted_content', sa.Text(), nullable=True))
    
    # Restore data from backup table if it exists
    op.execute("""
        UPDATE pages 
        SET content = backup.content,
            extracted_content = backup.extracted_content
        FROM pages_content_backup backup
        WHERE pages.id = backup.id
    """)
    
    # Drop optimized indexes
    op.drop_index('idx_pages_extracted_text_exists', table_name='pages')
    op.execute("DROP INDEX IF EXISTS idx_pages_extracted_text_fts")
    
    # Log downgrade
    op.execute("""
        INSERT INTO migration_log (migration_name, step, data)
        VALUES ('remove_redundant_content', 'downgrade_completed', '{"status": "restored"}')
    """)