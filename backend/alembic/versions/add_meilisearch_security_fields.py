"""Add Meilisearch security fields and audit table

Revision ID: add_meilisearch_security_fields
Revises: [latest_revision]
Create Date: 2025-01-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_meilisearch_security_fields'
down_revision = 'c2f4a7d1b9a0'  # Replace with actual latest revision
branch_labels = None
depends_on = None


def upgrade():
    """Add Meilisearch security fields and audit table"""
    
    # Add search key fields to public_search_configs table
    op.add_column('public_search_configs', sa.Column('search_key', sa.String(length=256), nullable=True))
    op.add_column('public_search_configs', sa.Column('search_key_uid', sa.String(length=256), nullable=True))
    op.add_column('public_search_configs', sa.Column('key_created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('public_search_configs', sa.Column('key_last_rotated', sa.DateTime(timezone=True), nullable=True))
    
    # Create MeilisearchKey audit table for key lifecycle tracking
    op.create_table('meilisearch_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('key_uid', sa.String(length=256), nullable=False),
        sa.Column('key_type', sa.String(length=50), nullable=False),  # 'project_owner', 'public', 'tenant'
        sa.Column('key_name', sa.String(length=255), nullable=True),
        sa.Column('key_description', sa.Text(), nullable=True),
        sa.Column('actions', sa.JSON(), nullable=True),  # List of allowed actions
        sa.Column('indexes', sa.JSON(), nullable=True),  # List of allowed indexes
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.String(length=255), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, default=0),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_uid')
    )
    
    # Create indexes for efficient querying
    op.create_index('ix_meilisearch_keys_project_id', 'meilisearch_keys', ['project_id'])
    op.create_index('ix_meilisearch_keys_key_type', 'meilisearch_keys', ['key_type'])
    op.create_index('ix_meilisearch_keys_is_active', 'meilisearch_keys', ['is_active'])
    op.create_index('ix_meilisearch_keys_expires_at', 'meilisearch_keys', ['expires_at'])
    
    # Add key rotation tracking fields to projects table
    op.add_column('projects', sa.Column('key_created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('projects', sa.Column('key_last_rotated', sa.DateTime(timezone=True), nullable=True))
    op.add_column('projects', sa.Column('key_rotation_enabled', sa.Boolean(), nullable=True))
    
    # Set default value for existing rows
    op.execute("UPDATE projects SET key_rotation_enabled = true WHERE key_rotation_enabled IS NULL")
    
    # Now make the column non-nullable
    op.alter_column('projects', 'key_rotation_enabled', nullable=False)
    
    # Add sharing permission enum values if not exist (defensive)
    # Note: This adds the new permission types we use for tenant tokens
    op.execute("ALTER TYPE sharepermission ADD VALUE IF NOT EXISTS 'LIMITED'")
    op.execute("ALTER TYPE sharepermission ADD VALUE IF NOT EXISTS 'RESTRICTED'")


def downgrade():
    """Remove Meilisearch security fields and audit table"""
    
    # Remove project key tracking fields
    op.drop_column('projects', 'key_rotation_enabled')
    op.drop_column('projects', 'key_last_rotated')
    op.drop_column('projects', 'key_created_at')
    
    # Drop indexes first
    op.drop_index('ix_meilisearch_keys_expires_at', table_name='meilisearch_keys')
    op.drop_index('ix_meilisearch_keys_is_active', table_name='meilisearch_keys')
    op.drop_index('ix_meilisearch_keys_key_type', table_name='meilisearch_keys')
    op.drop_index('ix_meilisearch_keys_project_id', table_name='meilisearch_keys')
    
    # Drop audit table
    op.drop_table('meilisearch_keys')
    
    # Remove search key fields from public_search_configs
    op.drop_column('public_search_configs', 'key_last_rotated')
    op.drop_column('public_search_configs', 'key_created_at')
    op.drop_column('public_search_configs', 'search_key_uid')
    op.drop_column('public_search_configs', 'search_key')