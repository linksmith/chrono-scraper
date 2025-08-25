"""Create backup system tables

Revision ID: scjegeph302r
Revises: tglfy1ngdfb7
Create Date: 2025-08-24 15:35:00.000000

This migration creates the comprehensive backup and recovery system tables:
- storage_backend_configs: Storage configuration for different backends (S3, GCS, local, etc.)
- backup_schedules: Automated backup scheduling with cron expressions
- backup_executions: Individual backup execution records and metadata
- recovery_executions: Recovery operation records and status tracking
- backup_retention_policies: Retention rules and cleanup policies
- backup_cleanup_history: History of backup cleanup operations
- backup_health_checks: System health monitoring and checks
- backup_audit_logs: Security audit log for backup operations
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'scjegeph302r'
down_revision: Union[str, None] = 'tglfy1ngdfb7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create backup system tables"""
    
    # Create storage_backend_configs table
    op.create_table(
        'storage_backend_configs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, index=True),
        sa.Column('backend_type', sa.String(20), nullable=False, index=True),  # local, aws_s3, gcs, azure_blob, ftp, sftp
        sa.Column('config_data', postgresql.JSON, nullable=False),  # Configuration as JSON (encrypted sensitive data)
        
        # Status and health
        sa.Column('is_active', sa.Boolean, nullable=False, default=True),
        sa.Column('is_healthy', sa.Boolean, nullable=False, default=True),
        sa.Column('last_health_check', sa.DateTime(timezone=True), nullable=True),
        sa.Column('health_check_message', sa.String(500), nullable=True),
        
        # Usage statistics
        sa.Column('total_backups', sa.Integer, nullable=False, default=0),
        sa.Column('total_size_bytes', sa.BigInteger, nullable=False, default=0),
        
        # Metadata
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('tags', postgresql.JSON, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.func.now()),
    )
    
    # Create backup_schedules table
    op.create_table(
        'backup_schedules',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(200), nullable=False, index=True),
        
        # Schedule configuration
        sa.Column('cron_expression', sa.String(100), nullable=False),  # Standard cron expression
        sa.Column('timezone', sa.String(50), nullable=False, default='UTC'),
        
        # Backup configuration
        sa.Column('backup_type', sa.String(20), nullable=False, index=True),  # full, incremental, differential, etc.
        sa.Column('storage_backend_id', sa.Integer, sa.ForeignKey('storage_backend_configs.id'), nullable=False, index=True),
        
        # Backup options
        sa.Column('compression_type', sa.String(10), nullable=False, default='gzip'),  # none, gzip, lz4, zstd
        sa.Column('encrypt_backup', sa.Boolean, nullable=False, default=True),
        sa.Column('verify_integrity', sa.Boolean, nullable=False, default=True),
        sa.Column('retention_days', sa.Integer, nullable=False, default=30),
        
        # Include/exclude patterns
        sa.Column('include_patterns', postgresql.JSON, nullable=True),
        sa.Column('exclude_patterns', postgresql.JSON, nullable=True),
        
        # Bandwidth and performance
        sa.Column('bandwidth_limit_mbps', sa.Integer, nullable=True),
        sa.Column('max_parallel_uploads', sa.Integer, nullable=False, default=3),
        
        # Schedule status
        sa.Column('is_active', sa.Boolean, nullable=False, default=True, index=True),
        sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_status', sa.String(50), nullable=True),
        
        # Statistics
        sa.Column('total_runs', sa.Integer, nullable=False, default=0),
        sa.Column('successful_runs', sa.Integer, nullable=False, default=0),
        sa.Column('failed_runs', sa.Integer, nullable=False, default=0),
        
        # Metadata
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('tags', postgresql.JSON, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.func.now()),
    )
    
    # Create backup_executions table
    op.create_table(
        'backup_executions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('backup_id', sa.String(100), nullable=False, unique=True, index=True),
        
        # Relationships
        sa.Column('schedule_id', sa.Integer, sa.ForeignKey('backup_schedules.id'), nullable=True, index=True),
        sa.Column('storage_backend_id', sa.Integer, sa.ForeignKey('storage_backend_configs.id'), nullable=False, index=True),
        
        # Backup configuration
        sa.Column('backup_type', sa.String(20), nullable=False, index=True),
        sa.Column('triggered_by', sa.String(100), nullable=False),  # "schedule", "manual", "api", "webhook"
        sa.Column('trigger_user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        
        # Execution details
        sa.Column('status', sa.String(20), nullable=False, index=True),  # scheduled, pending, running, completed, failed, cancelled, verifying, verified, corrupted
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer, nullable=True),
        
        # Backup details
        sa.Column('size_bytes', sa.BigInteger, nullable=False, default=0),
        sa.Column('compressed_size_bytes', sa.BigInteger, nullable=False, default=0),
        sa.Column('compression_ratio', sa.Float, nullable=False, default=1.0),
        
        # Components included
        sa.Column('included_components', postgresql.JSON, nullable=False),
        
        # Storage information
        sa.Column('storage_location', sa.String(1000), nullable=True),
        sa.Column('checksum', sa.String(128), nullable=True),
        sa.Column('encryption_key_hash', sa.String(128), nullable=True),
        
        # Verification
        sa.Column('verification_status', sa.String(50), nullable=False, default='pending'),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verification_checksum', sa.String(128), nullable=True),
        
        # Error handling
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_details', postgresql.JSON, nullable=True),
        sa.Column('warnings', postgresql.JSON, nullable=True),
        
        # Metadata
        sa.Column('backup_config', postgresql.JSON, nullable=True),
        sa.Column('execution_metadata', postgresql.JSON, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.func.now()),
    )
    
    # Create recovery_executions table
    op.create_table(
        'recovery_executions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('recovery_id', sa.String(100), nullable=False, unique=True, index=True),
        
        # Source backup
        sa.Column('backup_execution_id', sa.Integer, sa.ForeignKey('backup_executions.id'), nullable=True, index=True),
        sa.Column('source_backup_id', sa.String(100), nullable=False, index=True),
        
        # Recovery configuration
        sa.Column('recovery_type', sa.String(30), nullable=False, index=True),  # full_restore, database_only, files_only, etc.
        sa.Column('restore_target', sa.String(50), nullable=False),  # "same_system", "new_system", etc.
        
        # Target information
        sa.Column('target_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('target_system', sa.String(200), nullable=False),
        sa.Column('custom_restore_path', sa.String(1000), nullable=True),
        
        # Execution details
        sa.Column('status', sa.String(20), nullable=False, index=True),  # pending, preparing, downloading, extracting, restoring, validating, completed, failed, cancelled, rollback
        sa.Column('triggered_by', sa.String(100), nullable=False),  # "manual", "api", "disaster_recovery"
        sa.Column('trigger_user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True),
        
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer, nullable=True),
        
        # Recovery details
        sa.Column('restore_components', postgresql.JSON, nullable=False),
        sa.Column('restored_components', postgresql.JSON, nullable=False, default=[]),
        
        # Pre-recovery backup
        sa.Column('pre_recovery_backup_id', sa.String(100), nullable=True),
        
        # Validation
        sa.Column('validation_performed', sa.Boolean, nullable=False, default=False),
        sa.Column('validation_results', postgresql.JSON, nullable=True),
        sa.Column('validation_passed', sa.Boolean, nullable=True),
        
        # Error handling
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_details', postgresql.JSON, nullable=True),
        sa.Column('warnings', postgresql.JSON, nullable=True),
        
        # Configuration
        sa.Column('recovery_config', postgresql.JSON, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.func.now()),
    )
    
    # Create backup_retention_policies table
    op.create_table(
        'backup_retention_policies',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String(200), nullable=False, index=True),
        
        # Policy rules
        sa.Column('storage_backend_id', sa.Integer, sa.ForeignKey('storage_backend_configs.id'), nullable=False, index=True),
        sa.Column('backup_type', sa.String(20), nullable=True, index=True),  # None means all types
        
        # Retention settings
        sa.Column('retention_days', sa.Integer, nullable=False, default=30),
        sa.Column('keep_daily_for_days', sa.Integer, nullable=False, default=7),     # Keep daily backups for N days
        sa.Column('keep_weekly_for_weeks', sa.Integer, nullable=False, default=4),   # Keep weekly backups for N weeks  
        sa.Column('keep_monthly_for_months', sa.Integer, nullable=False, default=12), # Keep monthly backups for N months
        sa.Column('keep_yearly_for_years', sa.Integer, nullable=False, default=5),   # Keep yearly backups for N years
        
        # Minimum backups to keep
        sa.Column('min_backups_to_keep', sa.Integer, nullable=False, default=3),
        
        # Policy status
        sa.Column('is_active', sa.Boolean, nullable=False, default=True, index=True),
        
        # Statistics
        sa.Column('last_cleanup_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_cleanups', sa.Integer, nullable=False, default=0),
        sa.Column('total_backups_deleted', sa.Integer, nullable=False, default=0),
        sa.Column('total_space_freed_bytes', sa.BigInteger, nullable=False, default=0),
        
        # Configuration
        sa.Column('policy_rules', postgresql.JSON, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.func.now()),
    )
    
    # Create backup_cleanup_history table
    op.create_table(
        'backup_cleanup_history',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('cleanup_id', sa.String(100), nullable=False, unique=True, index=True),
        
        # Policy and execution
        sa.Column('retention_policy_id', sa.Integer, sa.ForeignKey('backup_retention_policies.id'), nullable=False, index=True),
        sa.Column('storage_backend_id', sa.Integer, sa.ForeignKey('storage_backend_configs.id'), nullable=False, index=True),
        
        # Execution details
        sa.Column('triggered_by', sa.String(100), nullable=False),  # "schedule", "manual", "storage_limit"
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer, nullable=True),
        
        # Cleanup results
        sa.Column('backups_evaluated', sa.Integer, nullable=False, default=0),
        sa.Column('backups_deleted', sa.Integer, nullable=False, default=0),
        sa.Column('backups_kept', sa.Integer, nullable=False, default=0),
        sa.Column('space_freed_bytes', sa.BigInteger, nullable=False, default=0),
        
        # Deleted backups
        sa.Column('deleted_backup_ids', postgresql.JSON, nullable=False, default=[]),
        
        # Status and errors
        sa.Column('status', sa.String(50), nullable=False, index=True),  # "completed", "failed", "partial"
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('warnings', postgresql.JSON, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.func.now()),
    )
    
    # Create backup_health_checks table
    op.create_table(
        'backup_health_checks',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('check_id', sa.String(100), nullable=False, unique=True, index=True),
        
        # Check configuration
        sa.Column('check_type', sa.String(50), nullable=False, index=True),  # "storage", "schedule", "integrity", "system"
        sa.Column('target_id', sa.Integer, nullable=True, index=True),  # ID of target (schedule, storage, etc.)
        sa.Column('target_type', sa.String(50), nullable=True),  # Type of target
        
        # Check execution
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('check_duration_seconds', sa.Float, nullable=True),
        
        # Results
        sa.Column('status', sa.String(50), nullable=False, index=True),  # "healthy", "warning", "critical", "error"
        sa.Column('health_score', sa.Float, nullable=True),  # 0.0 to 1.0
        
        # Details
        sa.Column('check_results', postgresql.JSON, nullable=True),
        sa.Column('issues_found', postgresql.JSON, nullable=True),
        sa.Column('recommendations', postgresql.JSON, nullable=True),
        
        # Metrics
        sa.Column('metrics', postgresql.JSON, nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.func.now()),
    )
    
    # Create backup_audit_logs table
    op.create_table(
        'backup_audit_logs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('audit_id', sa.String(100), nullable=False, unique=True, index=True),
        
        # Event details
        sa.Column('event_type', sa.String(100), nullable=False, index=True),  # "backup_created", "recovery_started", etc.
        sa.Column('event_category', sa.String(50), nullable=False, index=True),  # "backup", "recovery", "configuration", "access"
        
        # Actor information
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('username', sa.String(200), nullable=True),
        sa.Column('user_ip', sa.String(45), nullable=True),  # IPv6 support
        sa.Column('user_agent', sa.String(500), nullable=True),
        
        # Resource information
        sa.Column('resource_type', sa.String(50), nullable=True),  # "backup", "schedule", "storage"
        sa.Column('resource_id', sa.String(100), nullable=True),
        sa.Column('resource_name', sa.String(200), nullable=True),
        
        # Event details
        sa.Column('action', sa.String(100), nullable=False),  # "create", "update", "delete", "execute", "view"
        sa.Column('status', sa.String(50), nullable=False),   # "success", "failure", "warning"
        
        # Context and metadata
        sa.Column('event_data', postgresql.JSON, nullable=True),
        sa.Column('before_state', postgresql.JSON, nullable=True),
        sa.Column('after_state', postgresql.JSON, nullable=True),
        
        # Risk and compliance
        sa.Column('risk_level', sa.String(20), nullable=False, default='low'),  # "low", "medium", "high", "critical"
        sa.Column('compliance_tags', postgresql.JSON, nullable=True),
        
        # Additional context
        sa.Column('session_id', sa.String(100), nullable=True),
        sa.Column('correlation_id', sa.String(100), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, onupdate=sa.func.now()),
    )


def downgrade() -> None:
    """Drop backup system tables"""
    
    # Drop tables in reverse order (respecting foreign key dependencies)
    op.drop_table('backup_audit_logs')
    op.drop_table('backup_health_checks')
    op.drop_table('backup_cleanup_history')
    op.drop_table('backup_retention_policies')
    op.drop_table('recovery_executions')
    op.drop_table('backup_executions')
    op.drop_table('backup_schedules')
    op.drop_table('storage_backend_configs')