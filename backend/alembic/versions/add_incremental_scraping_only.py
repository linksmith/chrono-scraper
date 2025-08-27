"""Add incremental scraping fields only

Revision ID: add_incremental_scraping_only
Revises: enhance_filtering_individual
Create Date: 2025-08-27 07:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_incremental_scraping_only'
down_revision: Union[str, None] = 'enhance_filtering_individual'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Add incremental scraping table ###
    op.create_table('incremental_scraping_history',
        sa.Column('run_type', sa.String(length=20), nullable=False),
        sa.Column('trigger_reason', sa.String(length=200), nullable=True),
        sa.Column('date_range_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('date_range_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('incremental_config', sa.JSON(), nullable=False, default={}),
        sa.Column('pages_discovered', sa.Integer(), nullable=False, default=0),
        sa.Column('pages_processed', sa.Integer(), nullable=False, default=0),
        sa.Column('pages_failed', sa.Integer(), nullable=False, default=0),
        sa.Column('pages_skipped', sa.Integer(), nullable=False, default=0),
        sa.Column('new_content_found', sa.Integer(), nullable=False, default=0),
        sa.Column('duplicates_filtered', sa.Integer(), nullable=False, default=0),
        sa.Column('gaps_detected', sa.JSON(), nullable=False, default=[]),
        sa.Column('gaps_filled', sa.JSON(), nullable=False, default=[]),
        sa.Column('coverage_before', sa.Float(), nullable=True),
        sa.Column('coverage_after', sa.Float(), nullable=True),
        sa.Column('coverage_improvement', sa.Float(), nullable=True),
        sa.Column('runtime_seconds', sa.Float(), nullable=True),
        sa.Column('avg_processing_time', sa.Float(), nullable=True),
        sa.Column('success_rate', sa.Float(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_details', sa.JSON(), nullable=True),
        sa.Column('detailed_results', sa.JSON(), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain_id', sa.Integer(), nullable=False),
        sa.Column('scrape_session_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], ),
        sa.ForeignKeyConstraint(['scrape_session_id'], ['scrape_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for incremental scraping history
    op.create_index('ix_incremental_history_date_range', 'incremental_scraping_history', ['date_range_start', 'date_range_end'], unique=False)
    op.create_index('ix_incremental_history_domain_id', 'incremental_scraping_history', ['domain_id'], unique=False)
    op.create_index('ix_incremental_history_domain_status', 'incremental_scraping_history', ['domain_id', 'status'], unique=False)
    op.create_index('ix_incremental_history_run_type', 'incremental_scraping_history', ['run_type'], unique=False)
    op.create_index('ix_incremental_history_started_at', 'incremental_scraping_history', ['started_at'], unique=False)
    op.create_index('ix_incremental_history_status', 'incremental_scraping_history', ['status'], unique=False)

    # ### Add incremental scraping fields to domains table ###
    op.add_column('domains', sa.Column('incremental_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('domains', sa.Column('incremental_mode', sa.String(length=20), nullable=False, server_default=sa.text("'time_based'")))
    op.add_column('domains', sa.Column('overlap_days', sa.Integer(), nullable=False, server_default=sa.text('7')))
    op.add_column('domains', sa.Column('max_gap_days', sa.Integer(), nullable=False, server_default=sa.text('30')))
    op.add_column('domains', sa.Column('backfill_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')))
    op.add_column('domains', sa.Column('scraped_date_ranges', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column('domains', sa.Column('coverage_percentage', sa.Float(), nullable=True))
    op.add_column('domains', sa.Column('known_gaps', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))
    op.add_column('domains', sa.Column('last_incremental_check', sa.DateTime(timezone=True), nullable=True))
    op.add_column('domains', sa.Column('next_incremental_check', sa.DateTime(timezone=True), nullable=True))
    op.add_column('domains', sa.Column('total_incremental_runs', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('domains', sa.Column('successful_incremental_runs', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('domains', sa.Column('failed_incremental_runs', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('domains', sa.Column('gaps_detected', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('domains', sa.Column('gaps_filled', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('domains', sa.Column('new_content_discovered', sa.Integer(), nullable=False, server_default=sa.text('0')))
    op.add_column('domains', sa.Column('avg_incremental_runtime', sa.Float(), nullable=True))
    op.add_column('domains', sa.Column('last_incremental_runtime', sa.Float(), nullable=True))
    
    # Create indexes for domains incremental fields
    op.create_index('ix_domains_incremental_enabled', 'domains', ['incremental_enabled'], unique=False)
    op.create_index('ix_domains_last_incremental_check', 'domains', ['last_incremental_check'], unique=False)
    op.create_index('ix_domains_next_incremental_check', 'domains', ['next_incremental_check'], unique=False)
    op.create_index('ix_domains_project_incremental', 'domains', ['project_id', 'incremental_enabled'], unique=False)


def downgrade() -> None:
    # ### Remove indexes and columns from domains table ###
    op.drop_index('ix_domains_project_incremental', table_name='domains')
    op.drop_index('ix_domains_next_incremental_check', table_name='domains')
    op.drop_index('ix_domains_last_incremental_check', table_name='domains')
    op.drop_index('ix_domains_incremental_enabled', table_name='domains')
    
    op.drop_column('domains', 'last_incremental_runtime')
    op.drop_column('domains', 'avg_incremental_runtime')
    op.drop_column('domains', 'new_content_discovered')
    op.drop_column('domains', 'gaps_filled')
    op.drop_column('domains', 'gaps_detected')
    op.drop_column('domains', 'failed_incremental_runs')
    op.drop_column('domains', 'successful_incremental_runs')
    op.drop_column('domains', 'total_incremental_runs')
    op.drop_column('domains', 'next_incremental_check')
    op.drop_column('domains', 'last_incremental_check')
    op.drop_column('domains', 'known_gaps')
    op.drop_column('domains', 'coverage_percentage')
    op.drop_column('domains', 'scraped_date_ranges')
    op.drop_column('domains', 'backfill_enabled')
    op.drop_column('domains', 'max_gap_days')
    op.drop_column('domains', 'overlap_days')
    op.drop_column('domains', 'incremental_mode')
    op.drop_column('domains', 'incremental_enabled')

    # ### Remove incremental scraping history table ###
    op.drop_index('ix_incremental_history_status', table_name='incremental_scraping_history')
    op.drop_index('ix_incremental_history_started_at', table_name='incremental_scraping_history')
    op.drop_index('ix_incremental_history_run_type', table_name='incremental_scraping_history')
    op.drop_index('ix_incremental_history_domain_status', table_name='incremental_scraping_history')
    op.drop_index('ix_incremental_history_domain_id', table_name='incremental_scraping_history')
    op.drop_index('ix_incremental_history_date_range', table_name='incremental_scraping_history')
    op.drop_table('incremental_scraping_history')