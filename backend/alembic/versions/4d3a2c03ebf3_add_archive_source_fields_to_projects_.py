"""Add archive source fields to projects table

Revision ID: 4d3a2c03ebf3
Revises: add_archive_source_change_log
Create Date: 2025-09-04 02:57:47.365286

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4d3a2c03ebf3'
down_revision: Union[str, None] = 'add_archive_source_change_log'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only add the required archive source columns to projects table
    op.drop_constraint('cdx_resume_states_domain_id_fkey', 'cdx_resume_states', type_='foreignkey')
    op.create_foreign_key(None, 'cdx_resume_states', 'domains', ['domain_id'], ['id'])
    op.alter_column('domains', 'incremental_mode',
               existing_type=sa.VARCHAR(length=20),
               nullable=True,
               existing_server_default=sa.text("'time_based'::character varying"))
    op.alter_column('domains', 'scraped_date_ranges',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=True,
               existing_server_default=sa.text("'[]'::json"))
    op.alter_column('domains', 'known_gaps',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=True,
               existing_server_default=sa.text("'[]'::json"))
    op.drop_constraint('domains_project_id_fkey', 'domains', type_='foreignkey')
    op.create_foreign_key(None, 'domains', 'projects', ['project_id'], ['id'])
    op.alter_column('entity_mentions', 'page_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('extracted_entities', 'page_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.drop_constraint('extracted_entities_project_id_fkey', 'extracted_entities', type_='foreignkey')
    op.create_foreign_key(None, 'extracted_entities', 'projects', ['project_id'], ['id'])
    op.alter_column('incremental_scraping_history', 'run_type',
               existing_type=sa.VARCHAR(length=20),
               nullable=True)
    op.alter_column('incremental_scraping_history', 'date_range_start',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('incremental_scraping_history', 'date_range_end',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True)
    op.alter_column('incremental_scraping_history', 'incremental_config',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=True)
    op.alter_column('incremental_scraping_history', 'gaps_detected',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=True)
    op.alter_column('incremental_scraping_history', 'gaps_filled',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=True)
    op.alter_column('incremental_scraping_history', 'status',
               existing_type=sa.VARCHAR(length=20),
               nullable=True)
    op.alter_column('incremental_scraping_history', 'started_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.alter_column('incremental_scraping_history', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.alter_column('incremental_scraping_history', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.drop_constraint('incremental_scraping_history_domain_id_fkey', 'incremental_scraping_history', type_='foreignkey')
    op.create_foreign_key(None, 'incremental_scraping_history', 'domains', ['domain_id'], ['id'])
    op.alter_column('page_comparisons', 'baseline_page_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('page_comparisons', 'target_page_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.create_foreign_key(None, 'page_comparisons', 'users', ['reviewed_by_user_id'], ['id'])
    op.create_foreign_key(None, 'page_comparisons', 'users', ['user_id'], ['id'])
    op.create_foreign_key(None, 'page_comparisons', 'investigations', ['investigation_id'], ['id'])
    op.create_foreign_key(None, 'page_error_logs', 'scrape_sessions', ['scrape_session_id'], ['id'])
    op.create_foreign_key(None, 'page_error_logs', 'scrape_pages', ['scrape_page_id'], ['id'])
    op.drop_constraint('project_shares_project_id_fkey', 'project_shares', type_='foreignkey')
    op.create_foreign_key(None, 'project_shares', 'projects', ['project_id'], ['id'])
    # Add archive source fields to projects table
    op.add_column('projects', sa.Column('archive_source', sa.String(length=20), nullable=True))
    op.add_column('projects', sa.Column('fallback_enabled', sa.Boolean(), nullable=False))
    op.add_column('projects', sa.Column('archive_config', sa.JSON(), nullable=True))
    op.drop_constraint('public_search_configs_project_id_fkey', 'public_search_configs', type_='foreignkey')
    op.create_foreign_key(None, 'public_search_configs', 'projects', ['project_id'], ['id'])
    op.alter_column('scrape_pages', 'is_manually_overridden',
               existing_type=sa.BOOLEAN(),
               nullable=False,
               existing_server_default=sa.text('false'))
    op.alter_column('scrape_pages', 'can_be_manually_processed',
               existing_type=sa.BOOLEAN(),
               nullable=False,
               existing_server_default=sa.text('true'))
    op.drop_index('ix_scrape_pages_filter_category', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_filter_confidence', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_filter_details_gin', table_name='scrape_pages', postgresql_ops={'filter_details': 'jsonb_path_ops'}, postgresql_using='gin', postgresql_where='(filter_details IS NOT NULL)')
    op.drop_index('ix_scrape_pages_filter_reason', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_filtering_dashboard', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_manual_override', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_matched_pattern', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_page_id', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_priority_score', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_related_page_id', table_name='scrape_pages')
    op.drop_index('ix_scrape_pages_status_filter_category', table_name='scrape_pages')
    op.create_foreign_key(None, 'scrape_pages', 'domains', ['domain_id'], ['id'])
    op.create_foreign_key(None, 'scrape_pages', 'scrape_sessions', ['scrape_session_id'], ['id'])
    op.alter_column('scrape_sessions', 'external_batch_id',
               existing_type=sa.TEXT(),
               type_=sa.String(length=128),
               existing_nullable=True)
    op.drop_constraint('scrape_sessions_project_id_fkey', 'scrape_sessions', type_='foreignkey')
    op.create_foreign_key(None, 'scrape_sessions', 'projects', ['project_id'], ['id'])
    op.drop_constraint('search_history_project_id_fkey', 'search_history', type_='foreignkey')
    op.create_foreign_key(None, 'search_history', 'projects', ['project_id'], ['id'])
    op.drop_constraint('starred_items_page_id_fkey', 'starred_items', type_='foreignkey')
    op.drop_constraint('starred_items_project_id_fkey', 'starred_items', type_='foreignkey')
    op.create_foreign_key(None, 'starred_items', 'projects', ['project_id'], ['id'])
    op.drop_column('starred_items', 'page_id')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('starred_items', sa.Column('page_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.drop_constraint(None, 'starred_items', type_='foreignkey')
    op.create_foreign_key('starred_items_project_id_fkey', 'starred_items', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('starred_items_page_id_fkey', 'starred_items', 'pages', ['page_id'], ['id'])
    op.drop_constraint(None, 'search_history', type_='foreignkey')
    op.create_foreign_key('search_history_project_id_fkey', 'search_history', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(None, 'scrape_sessions', type_='foreignkey')
    op.create_foreign_key('scrape_sessions_project_id_fkey', 'scrape_sessions', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.alter_column('scrape_sessions', 'external_batch_id',
               existing_type=sa.String(length=128),
               type_=sa.TEXT(),
               existing_nullable=True)
    op.drop_constraint(None, 'scrape_pages', type_='foreignkey')
    op.drop_constraint(None, 'scrape_pages', type_='foreignkey')
    op.create_index('ix_scrape_pages_status_filter_category', 'scrape_pages', ['status', 'filter_category'], unique=False)
    op.create_index('ix_scrape_pages_related_page_id', 'scrape_pages', ['related_page_id'], unique=False)
    op.create_index('ix_scrape_pages_priority_score', 'scrape_pages', ['priority_score'], unique=False)
    op.create_index('ix_scrape_pages_page_id', 'scrape_pages', ['page_id'], unique=False)
    op.create_index('ix_scrape_pages_matched_pattern', 'scrape_pages', ['matched_pattern'], unique=False)
    op.create_index('ix_scrape_pages_manual_override', 'scrape_pages', ['is_manually_overridden', 'can_be_manually_processed'], unique=False)
    op.create_index('ix_scrape_pages_filtering_dashboard', 'scrape_pages', ['domain_id', 'status', 'filter_category', 'priority_score'], unique=False)
    op.create_index('ix_scrape_pages_filter_reason', 'scrape_pages', ['filter_reason'], unique=False)
    op.create_index('ix_scrape_pages_filter_details_gin', 'scrape_pages', ['filter_details'], unique=False, postgresql_ops={'filter_details': 'jsonb_path_ops'}, postgresql_using='gin', postgresql_where='(filter_details IS NOT NULL)')
    op.create_index('ix_scrape_pages_filter_confidence', 'scrape_pages', ['filter_confidence'], unique=False)
    op.create_index('ix_scrape_pages_filter_category', 'scrape_pages', ['filter_category'], unique=False)
    op.alter_column('scrape_pages', 'can_be_manually_processed',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('true'))
    op.alter_column('scrape_pages', 'is_manually_overridden',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('false'))
    op.drop_constraint(None, 'public_search_configs', type_='foreignkey')
    op.create_foreign_key('public_search_configs_project_id_fkey', 'public_search_configs', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.drop_column('projects', 'archive_config')
    op.drop_column('projects', 'fallback_enabled')
    op.drop_column('projects', 'archive_source')
    op.drop_constraint(None, 'project_shares', type_='foreignkey')
    op.create_foreign_key('project_shares_project_id_fkey', 'project_shares', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(None, 'page_error_logs', type_='foreignkey')
    op.drop_constraint(None, 'page_error_logs', type_='foreignkey')
    op.drop_constraint(None, 'page_comparisons', type_='foreignkey')
    op.drop_constraint(None, 'page_comparisons', type_='foreignkey')
    op.drop_constraint(None, 'page_comparisons', type_='foreignkey')
    op.alter_column('page_comparisons', 'target_page_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('page_comparisons', 'baseline_page_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_constraint(None, 'incremental_scraping_history', type_='foreignkey')
    op.create_foreign_key('incremental_scraping_history_domain_id_fkey', 'incremental_scraping_history', 'domains', ['domain_id'], ['id'], ondelete='CASCADE')
    op.alter_column('incremental_scraping_history', 'updated_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('incremental_scraping_history', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('incremental_scraping_history', 'started_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('incremental_scraping_history', 'status',
               existing_type=sa.VARCHAR(length=20),
               nullable=False)
    op.alter_column('incremental_scraping_history', 'gaps_filled',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=False)
    op.alter_column('incremental_scraping_history', 'gaps_detected',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=False)
    op.alter_column('incremental_scraping_history', 'incremental_config',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=False)
    op.alter_column('incremental_scraping_history', 'date_range_end',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('incremental_scraping_history', 'date_range_start',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False)
    op.alter_column('incremental_scraping_history', 'run_type',
               existing_type=sa.VARCHAR(length=20),
               nullable=False)
    op.drop_constraint(None, 'extracted_entities', type_='foreignkey')
    op.create_foreign_key('extracted_entities_project_id_fkey', 'extracted_entities', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.alter_column('extracted_entities', 'page_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('entity_mentions', 'page_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_constraint(None, 'domains', type_='foreignkey')
    op.create_foreign_key('domains_project_id_fkey', 'domains', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.alter_column('domains', 'known_gaps',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=False,
               existing_server_default=sa.text("'[]'::json"))
    op.alter_column('domains', 'scraped_date_ranges',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=False,
               existing_server_default=sa.text("'[]'::json"))
    op.alter_column('domains', 'incremental_mode',
               existing_type=sa.VARCHAR(length=20),
               nullable=False,
               existing_server_default=sa.text("'time_based'::character varying"))
    op.drop_constraint(None, 'cdx_resume_states', type_='foreignkey')
    op.create_foreign_key('cdx_resume_states_domain_id_fkey', 'cdx_resume_states', 'domains', ['domain_id'], ['id'], ondelete='CASCADE')
    op.create_table('backup_cleanup_history',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('cleanup_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('retention_policy_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('storage_backend_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('triggered_by', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('duration_seconds', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('backups_evaluated', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('backups_deleted', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('backups_kept', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('space_freed_bytes', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('deleted_backup_ids', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('status', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('error_message', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('warnings', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['retention_policy_id'], ['backup_retention_policies.id'], name='backup_cleanup_history_retention_policy_id_fkey'),
    sa.ForeignKeyConstraint(['storage_backend_id'], ['storage_backend_configs.id'], name='backup_cleanup_history_storage_backend_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='backup_cleanup_history_pkey')
    )
    op.create_index('ix_backup_cleanup_history_storage_backend_id', 'backup_cleanup_history', ['storage_backend_id'], unique=False)
    op.create_index('ix_backup_cleanup_history_status', 'backup_cleanup_history', ['status'], unique=False)
    op.create_index('ix_backup_cleanup_history_retention_policy_id', 'backup_cleanup_history', ['retention_policy_id'], unique=False)
    op.create_index('ix_backup_cleanup_history_cleanup_id', 'backup_cleanup_history', ['cleanup_id'], unique=True)
    op.create_table('pages',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('domain_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('original_url', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('content_url', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('title', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.Column('unix_timestamp', sa.VARCHAR(length=14), autoincrement=False, nullable=True),
    sa.Column('mime_type', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('status_code', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('extracted_title', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.Column('extracted_text', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('meta_description', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('meta_keywords', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('author', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
    sa.Column('published_date', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('language', sa.VARCHAR(length=10), autoincrement=False, nullable=True),
    sa.Column('word_count', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('character_count', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('content_type', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('content_length', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('capture_date', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('review_status', sa.VARCHAR(length=20), server_default=sa.text("'unreviewed'::character varying"), autoincrement=False, nullable=False),
    sa.Column('page_category', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
    sa.Column('priority_level', sa.VARCHAR(length=20), server_default=sa.text("'medium'::character varying"), autoincrement=False, nullable=False),
    sa.Column('review_notes', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('quick_notes', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.Column('quality_score', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('is_duplicate', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('duplicate_of_page_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('content_hash', sa.VARCHAR(length=64), autoincrement=False, nullable=True),
    sa.Column('processed', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('indexed', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('error_message', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('retry_count', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.Column('last_retry_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('content_embedding', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('embedding_updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('reviewed_by', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('reviewed_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('scraped_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['domain_id'], ['domains.id'], name='pages_domain_id_fkey', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name='pages_reviewed_by_fkey'),
    sa.PrimaryKeyConstraint('id', name='pages_pkey'),
    sa.UniqueConstraint('domain_id', 'original_url', 'unix_timestamp', name='uq_pages_domain_url_ts', postgresql_include=[], postgresql_nulls_not_distinct=False)
    )
    op.create_table('backup_health_checks',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('check_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('check_type', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('target_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('target_type', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('checked_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('check_duration_seconds', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('status', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('health_score', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=True),
    sa.Column('check_results', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('issues_found', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('recommendations', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('metrics', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='backup_health_checks_pkey')
    )
    op.create_index('ix_backup_health_checks_target_id', 'backup_health_checks', ['target_id'], unique=False)
    op.create_index('ix_backup_health_checks_status', 'backup_health_checks', ['status'], unique=False)
    op.create_index('ix_backup_health_checks_check_type', 'backup_health_checks', ['check_type'], unique=False)
    op.create_index('ix_backup_health_checks_check_id', 'backup_health_checks', ['check_id'], unique=True)
    op.create_table('meilisearch_keys',
    sa.Column('id', sa.INTEGER(), server_default=sa.text("nextval('meilisearch_keys_id_seq'::regclass)"), autoincrement=True, nullable=False),
    sa.Column('project_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('key_uid', sa.VARCHAR(length=256), autoincrement=False, nullable=False),
    sa.Column('key_type', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('key_name', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
    sa.Column('key_description', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('actions', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('indexes', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('expires_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('is_active', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('revoked_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('revoked_reason', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
    sa.Column('usage_count', sa.INTEGER(), server_default=sa.text('0'), autoincrement=False, nullable=False),
    sa.Column('last_used_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='meilisearch_keys_project_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name='meilisearch_keys_pkey'),
    sa.UniqueConstraint('key_uid', name='meilisearch_keys_key_uid_key', postgresql_include=[], postgresql_nulls_not_distinct=False),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_meilisearch_keys_project_id', 'meilisearch_keys', ['project_id'], unique=False)
    op.create_index('ix_meilisearch_keys_key_type', 'meilisearch_keys', ['key_type'], unique=False)
    op.create_index('ix_meilisearch_keys_is_active', 'meilisearch_keys', ['is_active'], unique=False)
    op.create_index('ix_meilisearch_keys_expires_at', 'meilisearch_keys', ['expires_at'], unique=False)
    op.create_table('backup_executions',
    sa.Column('id', sa.INTEGER(), server_default=sa.text("nextval('backup_executions_id_seq'::regclass)"), autoincrement=True, nullable=False),
    sa.Column('backup_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('schedule_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('storage_backend_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('backup_type', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('triggered_by', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('trigger_user_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('status', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('duration_seconds', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('size_bytes', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('compressed_size_bytes', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('compression_ratio', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=False),
    sa.Column('included_components', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('storage_location', sa.VARCHAR(length=1000), autoincrement=False, nullable=True),
    sa.Column('checksum', sa.VARCHAR(length=128), autoincrement=False, nullable=True),
    sa.Column('encryption_key_hash', sa.VARCHAR(length=128), autoincrement=False, nullable=True),
    sa.Column('verification_status', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('verified_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('verification_checksum', sa.VARCHAR(length=128), autoincrement=False, nullable=True),
    sa.Column('error_message', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('error_details', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('warnings', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('backup_config', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('execution_metadata', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['schedule_id'], ['backup_schedules.id'], name='backup_executions_schedule_id_fkey'),
    sa.ForeignKeyConstraint(['storage_backend_id'], ['storage_backend_configs.id'], name='backup_executions_storage_backend_id_fkey'),
    sa.ForeignKeyConstraint(['trigger_user_id'], ['users.id'], name='backup_executions_trigger_user_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='backup_executions_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_backup_executions_storage_backend_id', 'backup_executions', ['storage_backend_id'], unique=False)
    op.create_index('ix_backup_executions_status', 'backup_executions', ['status'], unique=False)
    op.create_index('ix_backup_executions_schedule_id', 'backup_executions', ['schedule_id'], unique=False)
    op.create_index('ix_backup_executions_backup_type', 'backup_executions', ['backup_type'], unique=False)
    op.create_index('ix_backup_executions_backup_id', 'backup_executions', ['backup_id'], unique=True)
    op.create_table('meilisearch_usage_logs',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('key_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('operation', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('index_name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
    sa.Column('query', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('filters', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('result_count', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('response_time_ms', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('success', sa.BOOLEAN(), server_default=sa.text('true'), autoincrement=False, nullable=False),
    sa.Column('error_message', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('ip_address', sa.VARCHAR(length=45), autoincrement=False, nullable=True),
    sa.Column('user_agent', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('request_id', sa.VARCHAR(length=128), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['key_id'], ['meilisearch_keys.id'], name='meilisearch_usage_logs_key_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='meilisearch_usage_logs_pkey')
    )
    op.create_index('ix_meilisearch_usage_logs_success', 'meilisearch_usage_logs', ['success'], unique=False)
    op.create_index('ix_meilisearch_usage_logs_operation', 'meilisearch_usage_logs', ['operation'], unique=False)
    op.create_index('ix_meilisearch_usage_logs_key_id', 'meilisearch_usage_logs', ['key_id'], unique=False)
    op.create_index('ix_meilisearch_usage_logs_key_created', 'meilisearch_usage_logs', ['key_id', 'created_at'], unique=False)
    op.create_index('ix_meilisearch_usage_logs_created_at', 'meilisearch_usage_logs', ['created_at'], unique=False)
    op.create_table('storage_backend_configs',
    sa.Column('id', sa.INTEGER(), server_default=sa.text("nextval('storage_backend_configs_id_seq'::regclass)"), autoincrement=True, nullable=False),
    sa.Column('name', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('backend_type', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('config_data', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('is_healthy', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('last_health_check', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('health_check_message', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.Column('total_backups', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('total_size_bytes', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('description', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('id', name='storage_backend_configs_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_storage_backend_configs_name', 'storage_backend_configs', ['name'], unique=False)
    op.create_index('ix_storage_backend_configs_backend_type', 'storage_backend_configs', ['backend_type'], unique=False)
    op.create_table('backup_schedules',
    sa.Column('id', sa.INTEGER(), server_default=sa.text("nextval('backup_schedules_id_seq'::regclass)"), autoincrement=True, nullable=False),
    sa.Column('name', sa.VARCHAR(length=200), autoincrement=False, nullable=False),
    sa.Column('cron_expression', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('timezone', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('backup_type', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('storage_backend_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('compression_type', sa.VARCHAR(length=10), autoincrement=False, nullable=False),
    sa.Column('encrypt_backup', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('verify_integrity', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('retention_days', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('include_patterns', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('exclude_patterns', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('bandwidth_limit_mbps', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('max_parallel_uploads', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('last_run_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('next_run_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('last_status', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('total_runs', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('successful_runs', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('failed_runs', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('description', sa.VARCHAR(length=1000), autoincrement=False, nullable=True),
    sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['storage_backend_id'], ['storage_backend_configs.id'], name='backup_schedules_storage_backend_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='backup_schedules_pkey'),
    postgresql_ignore_search_path=False
    )
    op.create_index('ix_backup_schedules_storage_backend_id', 'backup_schedules', ['storage_backend_id'], unique=False)
    op.create_index('ix_backup_schedules_name', 'backup_schedules', ['name'], unique=False)
    op.create_index('ix_backup_schedules_is_active', 'backup_schedules', ['is_active'], unique=False)
    op.create_index('ix_backup_schedules_backup_type', 'backup_schedules', ['backup_type'], unique=False)
    op.create_table('recovery_executions',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('recovery_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('backup_execution_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('source_backup_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('recovery_type', sa.VARCHAR(length=30), autoincrement=False, nullable=False),
    sa.Column('restore_target', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('target_timestamp', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('target_system', sa.VARCHAR(length=200), autoincrement=False, nullable=False),
    sa.Column('custom_restore_path', sa.VARCHAR(length=1000), autoincrement=False, nullable=True),
    sa.Column('status', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('triggered_by', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('trigger_user_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('started_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False),
    sa.Column('completed_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('duration_seconds', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('restore_components', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('restored_components', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('pre_recovery_backup_id', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('validation_performed', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('validation_results', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('validation_passed', sa.BOOLEAN(), autoincrement=False, nullable=True),
    sa.Column('error_message', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('error_details', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('warnings', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('recovery_config', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['backup_execution_id'], ['backup_executions.id'], name='recovery_executions_backup_execution_id_fkey'),
    sa.ForeignKeyConstraint(['trigger_user_id'], ['users.id'], name='recovery_executions_trigger_user_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='recovery_executions_pkey')
    )
    op.create_index('ix_recovery_executions_status', 'recovery_executions', ['status'], unique=False)
    op.create_index('ix_recovery_executions_source_backup_id', 'recovery_executions', ['source_backup_id'], unique=False)
    op.create_index('ix_recovery_executions_recovery_type', 'recovery_executions', ['recovery_type'], unique=False)
    op.create_index('ix_recovery_executions_recovery_id', 'recovery_executions', ['recovery_id'], unique=True)
    op.create_index('ix_recovery_executions_backup_execution_id', 'recovery_executions', ['backup_execution_id'], unique=False)
    op.create_table('meilisearch_security_events',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('key_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('event_type', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('severity', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('description', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('event_metadata', postgresql.JSON(astext_type=sa.Text()), server_default=sa.text("'{}'::json"), autoincrement=False, nullable=False),
    sa.Column('source_ip', sa.VARCHAR(length=45), autoincrement=False, nullable=True),
    sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('automated', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['key_id'], ['meilisearch_keys.id'], name='meilisearch_security_events_key_id_fkey'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='meilisearch_security_events_user_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='meilisearch_security_events_pkey')
    )
    op.create_index('ix_meilisearch_security_events_user_id', 'meilisearch_security_events', ['user_id'], unique=False)
    op.create_index('ix_meilisearch_security_events_severity', 'meilisearch_security_events', ['severity'], unique=False)
    op.create_index('ix_meilisearch_security_events_key_id', 'meilisearch_security_events', ['key_id'], unique=False)
    op.create_index('ix_meilisearch_security_events_event_type', 'meilisearch_security_events', ['event_type'], unique=False)
    op.create_index('ix_meilisearch_security_events_created_at', 'meilisearch_security_events', ['created_at'], unique=False)
    op.create_table('backup_audit_logs',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('audit_id', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('event_type', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('event_category', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=True),
    sa.Column('username', sa.VARCHAR(length=200), autoincrement=False, nullable=True),
    sa.Column('user_ip', sa.VARCHAR(length=45), autoincrement=False, nullable=True),
    sa.Column('user_agent', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
    sa.Column('resource_type', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('resource_id', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('resource_name', sa.VARCHAR(length=200), autoincrement=False, nullable=True),
    sa.Column('action', sa.VARCHAR(length=100), autoincrement=False, nullable=False),
    sa.Column('status', sa.VARCHAR(length=50), autoincrement=False, nullable=False),
    sa.Column('event_data', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('before_state', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('after_state', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('risk_level', sa.VARCHAR(length=20), autoincrement=False, nullable=False),
    sa.Column('compliance_tags', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('session_id', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('correlation_id', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='backup_audit_logs_user_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='backup_audit_logs_pkey')
    )
    op.create_index('ix_backup_audit_logs_user_id', 'backup_audit_logs', ['user_id'], unique=False)
    op.create_index('ix_backup_audit_logs_event_type', 'backup_audit_logs', ['event_type'], unique=False)
    op.create_index('ix_backup_audit_logs_event_category', 'backup_audit_logs', ['event_category'], unique=False)
    op.create_index('ix_backup_audit_logs_audit_id', 'backup_audit_logs', ['audit_id'], unique=True)
    op.create_table('user_entity_config',
    sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('enabled', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('backend', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('language', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('backend_config', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('enable_wikidata', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('wikidata_language', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('confidence_threshold', sa.DOUBLE_PRECISION(precision=53), autoincrement=False, nullable=False),
    sa.Column('enable_entity_types', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('max_entities_per_page', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('enable_context_extraction', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='user_entity_config_user_id_fkey'),
    sa.PrimaryKeyConstraint('user_id', name='user_entity_config_pkey')
    )
    op.create_table('backup_retention_policies',
    sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('name', sa.VARCHAR(length=200), autoincrement=False, nullable=False),
    sa.Column('storage_backend_id', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('backup_type', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
    sa.Column('retention_days', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('keep_daily_for_days', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('keep_weekly_for_weeks', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('keep_monthly_for_months', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('keep_yearly_for_years', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('min_backups_to_keep', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('is_active', sa.BOOLEAN(), autoincrement=False, nullable=False),
    sa.Column('last_cleanup_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.Column('total_cleanups', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('total_backups_deleted', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('total_space_freed_bytes', sa.BIGINT(), autoincrement=False, nullable=False),
    sa.Column('policy_rules', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
    sa.ForeignKeyConstraint(['storage_backend_id'], ['storage_backend_configs.id'], name='backup_retention_policies_storage_backend_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='backup_retention_policies_pkey')
    )
    op.create_index('ix_backup_retention_policies_storage_backend_id', 'backup_retention_policies', ['storage_backend_id'], unique=False)
    op.create_index('ix_backup_retention_policies_name', 'backup_retention_policies', ['name'], unique=False)
    op.create_index('ix_backup_retention_policies_is_active', 'backup_retention_policies', ['is_active'], unique=False)
    op.create_index('ix_backup_retention_policies_backup_type', 'backup_retention_policies', ['backup_type'], unique=False)
    # ### end Alembic commands ###