"""Create Meilisearch audit tables

Revision ID: 8uzlxf9x22sb
Revises: scjegeph302r
Create Date: 2025-08-24 15:40:00.000000

This migration creates the Meilisearch key audit and tracking system:
- meilisearch_keys: Comprehensive audit trail and lifecycle tracking for API keys
- meilisearch_usage_logs: Detailed usage logging for API key operations
- meilisearch_security_events: Security event logging for monitoring

These tables enable:
- Security monitoring of API key usage
- Usage analytics and performance tracking  
- Key rotation management and lifecycle tracking
- Audit compliance for search operations
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8uzlxf9x22sb'
down_revision: Union[str, None] = 'scjegeph302r'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Meilisearch audit system tables"""
    
    # Create meilisearch_keys table
    op.create_table(
        'meilisearch_keys',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('project_id', sa.Integer, sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('key_uid', sa.String(256), nullable=False, unique=True),
        sa.Column('key_type', sa.String(50), nullable=False),  # project_owner, public, tenant, admin
        sa.Column('key_name', sa.String(255), nullable=True),
        sa.Column('key_description', sa.Text, nullable=True),
        
        # Key configuration
        sa.Column('actions', postgresql.JSON, nullable=True),  # List of allowed actions
        sa.Column('indexes', postgresql.JSON, nullable=True),  # List of allowed indexes
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        
        # Status tracking
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.String(255), nullable=True),
        
        # Usage tracking
        sa.Column('usage_count', sa.Integer, nullable=False, default=0),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, 
                 server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create meilisearch_usage_logs table
    op.create_table(
        'meilisearch_usage_logs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('key_id', sa.Integer, sa.ForeignKey('meilisearch_keys.id'), nullable=False, index=True),
        sa.Column('operation', sa.String(100), nullable=False),  # 'search', 'documents.get', etc.
        sa.Column('index_name', sa.String(255), nullable=False),
        sa.Column('query', sa.Text, nullable=True),
        sa.Column('filters', postgresql.JSON, nullable=True),
        sa.Column('result_count', sa.Integer, nullable=True),
        sa.Column('response_time_ms', sa.Integer, nullable=True),
        sa.Column('success', sa.Boolean, nullable=False, default=True),
        sa.Column('error_message', sa.Text, nullable=True),
        
        # Request metadata
        sa.Column('ip_address', sa.String(45), nullable=True),  # IPv6 support
        sa.Column('user_agent', sa.Text, nullable=True),
        sa.Column('request_id', sa.String(128), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    # Create meilisearch_security_events table
    op.create_table(
        'meilisearch_security_events',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('key_id', sa.Integer, sa.ForeignKey('meilisearch_keys.id'), nullable=True, index=True),
        sa.Column('event_type', sa.String(100), nullable=False),  # 'key_created', 'key_revoked', 'suspicious_usage', etc.
        sa.Column('severity', sa.String(20), nullable=False),  # 'info', 'warning', 'critical'
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('event_metadata', postgresql.JSON, nullable=False, default={}),
        
        # Event source
        sa.Column('source_ip', sa.String(45), nullable=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        sa.Column('automated', sa.Boolean, nullable=False, default=False),  # True if event was triggered by automation
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    # Create indexes for performance
    
    # meilisearch_keys indexes
    op.create_index('ix_meilisearch_keys_project_id', 'meilisearch_keys', ['project_id'])
    op.create_index('ix_meilisearch_keys_key_type', 'meilisearch_keys', ['key_type'])
    op.create_index('ix_meilisearch_keys_is_active', 'meilisearch_keys', ['is_active'])
    op.create_index('ix_meilisearch_keys_expires_at', 'meilisearch_keys', ['expires_at'])
    
    # meilisearch_usage_logs indexes
    op.create_index('ix_meilisearch_usage_logs_key_id', 'meilisearch_usage_logs', ['key_id'])
    op.create_index('ix_meilisearch_usage_logs_operation', 'meilisearch_usage_logs', ['operation'])
    op.create_index('ix_meilisearch_usage_logs_created_at', 'meilisearch_usage_logs', ['created_at'])
    op.create_index('ix_meilisearch_usage_logs_success', 'meilisearch_usage_logs', ['success'])
    op.create_index('ix_meilisearch_usage_logs_key_created', 'meilisearch_usage_logs', ['key_id', 'created_at'])
    
    # meilisearch_security_events indexes
    op.create_index('ix_meilisearch_security_events_key_id', 'meilisearch_security_events', ['key_id'])
    op.create_index('ix_meilisearch_security_events_event_type', 'meilisearch_security_events', ['event_type'])
    op.create_index('ix_meilisearch_security_events_severity', 'meilisearch_security_events', ['severity'])
    op.create_index('ix_meilisearch_security_events_created_at', 'meilisearch_security_events', ['created_at'])
    op.create_index('ix_meilisearch_security_events_user_id', 'meilisearch_security_events', ['user_id'])


def downgrade() -> None:
    """Drop Meilisearch audit system tables"""
    
    # Drop indexes first
    # meilisearch_security_events indexes
    op.drop_index('ix_meilisearch_security_events_user_id', table_name='meilisearch_security_events')
    op.drop_index('ix_meilisearch_security_events_created_at', table_name='meilisearch_security_events')
    op.drop_index('ix_meilisearch_security_events_severity', table_name='meilisearch_security_events')
    op.drop_index('ix_meilisearch_security_events_event_type', table_name='meilisearch_security_events')
    op.drop_index('ix_meilisearch_security_events_key_id', table_name='meilisearch_security_events')
    
    # meilisearch_usage_logs indexes  
    op.drop_index('ix_meilisearch_usage_logs_key_created', table_name='meilisearch_usage_logs')
    op.drop_index('ix_meilisearch_usage_logs_success', table_name='meilisearch_usage_logs')
    op.drop_index('ix_meilisearch_usage_logs_created_at', table_name='meilisearch_usage_logs')
    op.drop_index('ix_meilisearch_usage_logs_operation', table_name='meilisearch_usage_logs')
    op.drop_index('ix_meilisearch_usage_logs_key_id', table_name='meilisearch_usage_logs')
    
    # meilisearch_keys indexes
    op.drop_index('ix_meilisearch_keys_expires_at', table_name='meilisearch_keys')
    op.drop_index('ix_meilisearch_keys_is_active', table_name='meilisearch_keys')
    op.drop_index('ix_meilisearch_keys_key_type', table_name='meilisearch_keys')
    op.drop_index('ix_meilisearch_keys_project_id', table_name='meilisearch_keys')
    
    # Drop tables in reverse order (respecting foreign key dependencies)
    op.drop_table('meilisearch_security_events')
    op.drop_table('meilisearch_usage_logs')
    op.drop_table('meilisearch_keys')