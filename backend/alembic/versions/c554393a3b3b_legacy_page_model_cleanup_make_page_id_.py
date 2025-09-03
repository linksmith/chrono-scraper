"""Legacy Page model cleanup - make page_id nullable

Revision ID: c554393a3b3b
Revises: drop_legacy_pages_table
Create Date: 2025-09-01 10:57:11.242513

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c554393a3b3b'
down_revision: Union[str, None] = 'drop_legacy_pages_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Make page_id fields nullable in tables that previously referenced the legacy pages table
    """
    # Drop any remaining foreign key constraints referencing pages table (if they exist)
    try:
        op.drop_constraint('content_extractions_page_id_fkey', 'content_extractions', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    try:
        op.drop_constraint('entity_mentions_page_id_fkey', 'entity_mentions', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    try:
        op.drop_constraint('extracted_entities_page_id_fkey', 'extracted_entities', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    try:
        op.drop_constraint('investigation_timelines_page_id_fkey', 'investigation_timelines', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    try:
        op.drop_constraint('evidence_page_id_fkey', 'evidence', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    try:
        op.drop_constraint('page_comparisons_baseline_page_id_fkey', 'page_comparisons', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    try:
        op.drop_constraint('page_comparisons_target_page_id_fkey', 'page_comparisons', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist
    
    try:
        op.drop_constraint('scrape_pages_page_id_fkey', 'scrape_pages', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist

    # Make page_id fields nullable
    op.alter_column('content_extractions', 'page_id', nullable=True)
    op.alter_column('entity_mentions', 'page_id', nullable=True)
    op.alter_column('extracted_entities', 'page_id', nullable=True)
    
    # Check if tables exist before altering
    conn = op.get_bind()
    
    # investigation_timelines
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'investigation_timelines')"))
    if result.scalar():
        op.alter_column('investigation_timelines', 'page_id', nullable=True)
    
    # evidence  
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'evidence')"))
    if result.scalar():
        op.alter_column('evidence', 'page_id', nullable=True)
    
    # page_comparisons
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'page_comparisons')"))
    if result.scalar():
        try:
            op.alter_column('page_comparisons', 'baseline_page_id', nullable=True)
            op.alter_column('page_comparisons', 'target_page_id', nullable=True)
        except Exception:
            pass  # Columns might not exist
    
    # scrape_pages 
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'scrape_pages')"))
    if result.scalar():
        op.alter_column('scrape_pages', 'page_id', nullable=True)


def downgrade() -> None:
    """
    Reverse the changes - make page_id fields non-nullable again
    Note: This may fail if there are NULL values in the database
    """
    # Make page_id fields non-nullable (this may fail if there are NULLs)
    op.alter_column('content_extractions', 'page_id', nullable=False)
    op.alter_column('entity_mentions', 'page_id', nullable=False) 
    op.alter_column('extracted_entities', 'page_id', nullable=False)
    
    # Check if tables exist before altering
    conn = op.get_bind()
    
    # investigation_timelines
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'investigation_timelines')"))
    if result.scalar():
        op.alter_column('investigation_timelines', 'page_id', nullable=False)
    
    # evidence
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'evidence')"))
    if result.scalar():
        op.alter_column('evidence', 'page_id', nullable=False)
    
    # page_comparisons  
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'page_comparisons')"))
    if result.scalar():
        try:
            op.alter_column('page_comparisons', 'baseline_page_id', nullable=False)
            op.alter_column('page_comparisons', 'target_page_id', nullable=False)
        except Exception:
            pass
    
    # scrape_pages
    result = conn.execute(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'scrape_pages')"))
    if result.scalar():
        op.alter_column('scrape_pages', 'page_id', nullable=False)