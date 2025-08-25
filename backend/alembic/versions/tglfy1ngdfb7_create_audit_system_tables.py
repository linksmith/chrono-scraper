"""Create audit system tables

Revision ID: tglfy1ngdfb7
Revises: 5e6f7d5e8ef0
Create Date: 2025-08-24 15:30:00.000000

This migration creates the comprehensive audit logging system tables with:
- audit_logs table with advanced security fields (checksums, signatures, geolocation)
- Comprehensive indexes for performance and security queries
- Support for compliance tracking (GDPR, SOX, HIPAA)
- Integrity and security features (checksums, signatures, encryption flags)
- Performance metrics and geolocation tracking
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'tglfy1ngdfb7'
down_revision: Union[str, None] = '5e6f7d5e8ef0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit system tables with comprehensive security features"""
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        # Primary key and relationships
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('admin_user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('session_id', sa.String(255), nullable=True, index=True),
        sa.Column('request_id', sa.String(100), nullable=True, index=True),
        
        # Action details
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('resource_type', sa.String(50), nullable=False, index=True),
        sa.Column('resource_id', sa.String(255), nullable=True),
        sa.Column('category', sa.String(50), nullable=False, index=True),
        sa.Column('severity', sa.String(20), nullable=False, default='medium', index=True),
        
        # Request context
        sa.Column('ip_address', sa.String(45), nullable=True, index=True),  # IPv6 support
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('request_method', sa.String(10), nullable=True),
        sa.Column('request_url', sa.String(2048), nullable=True),
        sa.Column('request_headers', postgresql.JSON, nullable=True),
        sa.Column('request_body', postgresql.JSON, nullable=True),
        
        # Response context
        sa.Column('response_status', sa.Integer, nullable=True),
        sa.Column('response_headers', postgresql.JSON, nullable=True),
        sa.Column('response_body', postgresql.JSON, nullable=True),
        
        # Operation details
        sa.Column('success', sa.Boolean, nullable=False, default=True, index=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('affected_count', sa.Integer, nullable=False, default=0),
        
        # Change tracking
        sa.Column('before_values', postgresql.JSON, nullable=True),
        sa.Column('after_values', postgresql.JSON, nullable=True),
        sa.Column('changed_fields', postgresql.JSON, nullable=True),
        
        # Additional context
        sa.Column('details', postgresql.JSON, nullable=True),
        sa.Column('tags', postgresql.JSON, nullable=True),
        
        # Security and compliance
        sa.Column('compliance_flags', postgresql.JSON, nullable=True),
        sa.Column('sensitive_data_accessed', sa.Boolean, nullable=False, default=False, index=True),
        sa.Column('gdpr_relevant', sa.Boolean, nullable=False, default=False, index=True),
        sa.Column('sox_relevant', sa.Boolean, nullable=False, default=False, index=True),
        sa.Column('hipaa_relevant', sa.Boolean, nullable=False, default=False, index=True),
        
        # Integrity and security
        sa.Column('checksum', sa.String(64), nullable=True),
        sa.Column('signature', sa.String(512), nullable=True),
        sa.Column('encrypted', sa.Boolean, nullable=False, default=False),
        
        # Performance metrics
        sa.Column('processing_time_ms', sa.Integer, nullable=True),
        sa.Column('database_queries', sa.Integer, nullable=True),
        sa.Column('memory_usage_mb', sa.Float, nullable=True),
        
        # Geolocation and device info
        sa.Column('country_code', sa.String(2), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('device_type', sa.String(50), nullable=True),
        sa.Column('browser_info', sa.String(255), nullable=True),
        
        # Temporal fields
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, 
                 server_default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True,
                 onupdate=sa.func.now()),
        
        # Retention and archival
        sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('archived', sa.Boolean, nullable=False, default=False, index=True),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create comprehensive indexes for performance and security
    
    # Performance indexes for common queries
    op.create_index('ix_audit_logs_user_created', 'audit_logs', ['user_id', 'created_at'])
    op.create_index('ix_audit_logs_admin_created', 'audit_logs', ['admin_user_id', 'created_at'])
    op.create_index('ix_audit_logs_category_severity', 'audit_logs', ['category', 'severity'])
    op.create_index('ix_audit_logs_ip_created', 'audit_logs', ['ip_address', 'created_at'])
    op.create_index('ix_audit_logs_action_resource', 'audit_logs', ['action', 'resource_type'])
    op.create_index('ix_audit_logs_session_created', 'audit_logs', ['session_id', 'created_at'])
    
    # Compliance and security indexes
    op.create_index('ix_audit_logs_compliance', 'audit_logs', ['gdpr_relevant', 'sox_relevant', 'hipaa_relevant'])
    op.create_index('ix_audit_logs_sensitive_data', 'audit_logs', ['sensitive_data_accessed', 'created_at'])
    
    # Retention and archival indexes
    op.create_index('ix_audit_logs_retention', 'audit_logs', ['retention_until', 'archived'])


def downgrade() -> None:
    """Drop audit system tables"""
    
    # Drop indexes first
    op.drop_index('ix_audit_logs_retention', table_name='audit_logs')
    op.drop_index('ix_audit_logs_sensitive_data', table_name='audit_logs')
    op.drop_index('ix_audit_logs_compliance', table_name='audit_logs')
    op.drop_index('ix_audit_logs_session_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action_resource', table_name='audit_logs')
    op.drop_index('ix_audit_logs_ip_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_category_severity', table_name='audit_logs')
    op.drop_index('ix_audit_logs_admin_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_user_created', table_name='audit_logs')
    
    # Drop table
    op.drop_table('audit_logs')