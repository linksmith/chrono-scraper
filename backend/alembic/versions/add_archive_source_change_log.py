"""Add archive source change log table

Revision ID: add_archive_source_change_log
Revises: replace_proxy_api_key
Create Date: 2025-09-03 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_archive_source_change_log'
down_revision: Union[str, None] = 'replace_proxy_api_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the archive_source_change_logs table for audit logging"""
    op.create_table('archive_source_change_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('old_archive_source', sa.String(length=20), nullable=True),
        sa.Column('new_archive_source', sa.String(length=20), nullable=True),
        sa.Column('old_fallback_enabled', sa.Boolean(), nullable=False),
        sa.Column('new_fallback_enabled', sa.Boolean(), nullable=False),
        sa.Column('old_config', sa.JSON(), nullable=True),
        sa.Column('new_config', sa.JSON(), nullable=True),
        sa.Column('change_reason', sa.String(length=500), nullable=True),
        sa.Column('impact_acknowledged', sa.Boolean(), nullable=False),
        sa.Column('change_timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('rollback_available', sa.Boolean(), nullable=False),
        sa.Column('rollback_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rollback_applied', sa.Boolean(), nullable=False),
        sa.Column('rollback_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rollback_reason', sa.String(length=500), nullable=True),
        sa.Column('session_id', sa.String(length=255), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for better query performance
    op.create_index('ix_archive_changes_project_user', 'archive_source_change_logs', ['project_id', 'user_id'])
    op.create_index('ix_archive_changes_timestamp', 'archive_source_change_logs', ['change_timestamp'])
    op.create_index('ix_archive_changes_success', 'archive_source_change_logs', ['success'])


def downgrade() -> None:
    """Remove the archive_source_change_logs table"""
    op.drop_index('ix_archive_changes_success', table_name='archive_source_change_logs')
    op.drop_index('ix_archive_changes_timestamp', table_name='archive_source_change_logs')
    op.drop_index('ix_archive_changes_project_user', table_name='archive_source_change_logs')
    op.drop_table('archive_source_change_logs')