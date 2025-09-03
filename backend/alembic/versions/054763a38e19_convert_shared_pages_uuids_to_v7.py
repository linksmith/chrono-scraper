"""convert_shared_pages_uuids_to_v7

Revision ID: 054763a38e19
Revises: add_incremental_scraping_only
Create Date: 2025-09-01 10:20:41.803684

"""
from typing import Sequence, Union
import time
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '054763a38e19'
down_revision: Union[str, None] = 'add_incremental_scraping_only'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def uuid_v7() -> uuid.UUID:
    """
    Generate a UUIDv7 with time-based ordering for better database indexing.
    """
    # Get current time in milliseconds
    timestamp_ms = int(time.time() * 1000)
    
    # Generate random bytes for the rest
    random_bytes = uuid.uuid4().bytes
    
    # Build UUID bytes manually for better control
    uuid_bytes = bytearray(16)
    
    # First 6 bytes: 48-bit timestamp (big-endian)
    uuid_bytes[0] = (timestamp_ms >> 40) & 0xFF
    uuid_bytes[1] = (timestamp_ms >> 32) & 0xFF  
    uuid_bytes[2] = (timestamp_ms >> 24) & 0xFF
    uuid_bytes[3] = (timestamp_ms >> 16) & 0xFF
    uuid_bytes[4] = (timestamp_ms >> 8) & 0xFF
    uuid_bytes[5] = timestamp_ms & 0xFF
    
    # Next 2 bytes: 12-bit random + 4-bit version
    uuid_bytes[6] = (random_bytes[6] & 0x0F) | 0x70  # Version 7 in upper nibble
    uuid_bytes[7] = random_bytes[7]
    
    # Next 2 bytes: 2-bit variant + 14-bit random  
    uuid_bytes[8] = (random_bytes[8] & 0x3F) | 0x80  # Variant 10
    uuid_bytes[9] = random_bytes[9]
    
    # Last 6 bytes: 48-bit random
    uuid_bytes[10:16] = random_bytes[10:16]
    
    return uuid.UUID(bytes=bytes(uuid_bytes))


def upgrade() -> None:
    """
    Convert existing UUIDs in shared pages tables to UUIDv7 format.
    This migration preserves data integrity by creating new UUIDv7 IDs
    and updating all foreign key references.
    
    If the tables don't exist yet, this migration does nothing - the model
    changes will ensure new records use UUIDv7 by default.
    """
    connection = op.get_bind()
    
    # Check if the shared pages tables exist
    inspector = sa.inspect(connection)
    existing_tables = inspector.get_table_names()
    
    shared_pages_tables = ['pages_v2', 'project_pages', 'cdx_page_registry']
    tables_exist = all(table in existing_tables for table in shared_pages_tables)
    
    if not tables_exist:
        # Tables don't exist yet - nothing to convert
        # The model changes will ensure new records use UUIDv7
        return
    
    # Create a temporary mapping table to store old UUID to new UUIDv7 mappings
    # for pages_v2
    op.create_table(
        'temp_pages_v2_uuid_mapping',
        sa.Column('old_id', UUID(as_uuid=True), nullable=False),
        sa.Column('new_id', UUID(as_uuid=True), nullable=False),
    )
    
    # Create mapping for project_pages
    op.create_table(
        'temp_project_pages_uuid_mapping', 
        sa.Column('old_id', UUID(as_uuid=True), nullable=False),
        sa.Column('new_id', UUID(as_uuid=True), nullable=False),
    )
    
    # Create mapping for cdx_page_registry
    op.create_table(
        'temp_cdx_registry_uuid_mapping',
        sa.Column('old_id', UUID(as_uuid=True), nullable=False), 
        sa.Column('new_id', UUID(as_uuid=True), nullable=False),
    )
    
    try:
        # Step 1: Generate new UUIDv7s for pages_v2 and store mapping
        result = connection.execute(sa.text("SELECT id FROM pages_v2"))
        pages_mappings = []
        for row in result:
            old_id = row[0]
            new_id = uuid_v7()
            pages_mappings.append({'old_id': old_id, 'new_id': new_id})
        
        if pages_mappings:
            connection.execute(
                sa.text("INSERT INTO temp_pages_v2_uuid_mapping (old_id, new_id) VALUES (:old_id, :new_id)"),
                pages_mappings
            )
        
        # Step 2: Generate new UUIDv7s for project_pages and store mapping
        result = connection.execute(sa.text("SELECT id FROM project_pages"))
        project_pages_mappings = []
        for row in result:
            old_id = row[0]
            new_id = uuid_v7()
            project_pages_mappings.append({'old_id': old_id, 'new_id': new_id})
            
        if project_pages_mappings:
            connection.execute(
                sa.text("INSERT INTO temp_project_pages_uuid_mapping (old_id, new_id) VALUES (:old_id, :new_id)"),
                project_pages_mappings
            )
        
        # Step 3: Generate new UUIDv7s for cdx_page_registry and store mapping  
        result = connection.execute(sa.text("SELECT id FROM cdx_page_registry"))
        cdx_mappings = []
        for row in result:
            old_id = row[0]
            new_id = uuid_v7()
            cdx_mappings.append({'old_id': old_id, 'new_id': new_id})
            
        if cdx_mappings:
            connection.execute(
                sa.text("INSERT INTO temp_cdx_registry_uuid_mapping (old_id, new_id) VALUES (:old_id, :new_id)"),
                cdx_mappings
            )
        
        # Step 4: Update foreign key references in cdx_page_registry.page_id
        connection.execute(sa.text("""
            UPDATE cdx_page_registry 
            SET page_id = mapping.new_id
            FROM temp_pages_v2_uuid_mapping mapping
            WHERE cdx_page_registry.page_id = mapping.old_id
        """))
        
        # Step 5: Update foreign key references in project_pages.page_id
        connection.execute(sa.text("""
            UPDATE project_pages 
            SET page_id = mapping.new_id
            FROM temp_pages_v2_uuid_mapping mapping
            WHERE project_pages.page_id = mapping.old_id
        """))
        
        # Step 6: Update foreign key reference in project_pages.duplicate_of_page_id
        connection.execute(sa.text("""
            UPDATE project_pages 
            SET duplicate_of_page_id = mapping.new_id
            FROM temp_pages_v2_uuid_mapping mapping
            WHERE project_pages.duplicate_of_page_id = mapping.old_id
        """))
        
        # Step 7: Update primary keys with new UUIDv7s
        # Update pages_v2 primary key
        connection.execute(sa.text("""
            UPDATE pages_v2 
            SET id = mapping.new_id
            FROM temp_pages_v2_uuid_mapping mapping
            WHERE pages_v2.id = mapping.old_id
        """))
        
        # Update project_pages primary key
        connection.execute(sa.text("""
            UPDATE project_pages 
            SET id = mapping.new_id
            FROM temp_project_pages_uuid_mapping mapping
            WHERE project_pages.id = mapping.old_id
        """))
        
        # Update cdx_page_registry primary key
        connection.execute(sa.text("""
            UPDATE cdx_page_registry 
            SET id = mapping.new_id
            FROM temp_cdx_registry_uuid_mapping mapping
            WHERE cdx_page_registry.id = mapping.old_id
        """))
        
        connection.commit()
        
    finally:
        # Clean up temporary tables
        op.drop_table('temp_pages_v2_uuid_mapping')
        op.drop_table('temp_project_pages_uuid_mapping')
        op.drop_table('temp_cdx_registry_uuid_mapping')


def downgrade() -> None:
    """
    Downgrade is not supported for this migration as we cannot
    reliably convert UUIDv7 back to UUIDv4 while maintaining
    the same values that existed before the upgrade.
    
    If rollback is needed, restore from backup.
    """
    raise NotImplementedError(
        "Downgrade not supported for UUID format conversion. "
        "Restore from backup if rollback is required."
    )