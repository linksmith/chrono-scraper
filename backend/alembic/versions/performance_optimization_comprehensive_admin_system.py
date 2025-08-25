"""
Comprehensive Database Performance Optimization for Admin System

This migration creates strategic indexes, performance optimizations, and monitoring
for the comprehensive admin system including audit logs, security events, backup
operations, and user management.

Revision ID: perf_admin_optimization
Revises: existing migrations
Create Date: 2025-01-XX XX:XX:XX.XXXXXX
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers
revision = 'perf_admin_optimization'
down_revision = None  # Will be set dynamically
branch_labels = None
depends_on = None

def upgrade():
    """Apply comprehensive performance optimizations"""
    
    print("🚀 Applying comprehensive database performance optimizations...")
    
    # ==========================================
    # AUDIT LOGS PERFORMANCE OPTIMIZATION
    # ==========================================
    print("📊 Optimizing audit_logs table...")
    
    # Time-based partitioning support indexes
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_created_at_month 
        ON audit_logs (DATE_TRUNC('month', created_at));
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_created_at_day 
        ON audit_logs (DATE_TRUNC('day', created_at));
    """))
    
    # Composite indexes for common admin dashboard queries
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_admin_activity 
        ON audit_logs (admin_user_id, created_at DESC, category) 
        WHERE admin_user_id IS NOT NULL;
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_security_events 
        ON audit_logs (category, severity, created_at DESC, success) 
        WHERE category = 'security_event';
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_bulk_operations 
        ON audit_logs (category, action, created_at DESC, affected_count) 
        WHERE category = 'bulk_operation';
    """))
    
    # Covering indexes for dashboard metrics
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_dashboard_metrics 
        ON audit_logs (created_at DESC, category, severity, success, affected_count)
        INCLUDE (action, resource_type, ip_address);
    """))
    
    # Partial indexes for active/important records
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_failed_operations 
        ON audit_logs (created_at DESC, action, resource_type, error_code) 
        WHERE success = false;
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_compliance_relevant 
        ON audit_logs (created_at DESC, category, gdpr_relevant, sox_relevant, hipaa_relevant) 
        WHERE gdpr_relevant = true OR sox_relevant = true OR hipaa_relevant = true;
    """))
    
    # JSONB indexes for details and tags
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_details_gin 
        ON audit_logs USING gin (details);
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_tags_gin 
        ON audit_logs USING gin (tags);
    """))
    
    # ==========================================
    # SECURITY EVENTS PERFORMANCE OPTIMIZATION
    # ==========================================
    print("🔐 Optimizing security_events table...")
    
    # Time-window analysis indexes
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_security_events_recent_by_ip 
        ON security_events (ip_address, created_at DESC) 
        WHERE created_at > NOW() - INTERVAL '24 hours';
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_security_events_recent_failures 
        ON security_events (created_at DESC, event_type, ip_address, risk_score) 
        WHERE success = false AND created_at > NOW() - INTERVAL '7 days';
    """))
    
    # Risk analysis indexes
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_security_events_high_risk 
        ON security_events (risk_score DESC, created_at DESC, event_type) 
        WHERE risk_score > 70;
    """))
    
    # User behavior analysis
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_security_events_user_behavior 
        ON security_events (user_id, event_type, created_at DESC) 
        WHERE user_id IS NOT NULL;
    """))
    
    # GIN index for threat indicators
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_security_events_threat_indicators_gin 
        ON security_events USING gin (threat_indicators);
    """))
    
    # ==========================================
    # USER MANAGEMENT OPTIMIZATION
    # ==========================================
    print("👥 Optimizing users table...")
    
    # Admin management indexes
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_admin_dashboard 
        ON users (approval_status, is_active, created_at DESC) 
        INCLUDE (email, full_name, last_login, login_count);
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_security_status 
        ON users (is_locked, mfa_enabled, risk_score DESC, last_failed_login) 
        WHERE is_active = true;
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_approval_queue 
        ON users (approval_status, created_at) 
        WHERE approval_status = 'pending';
    """))
    
    # Authentication performance indexes
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_auth_lookup 
        ON users (email, is_active, is_locked, is_verified) 
        INCLUDE (hashed_password, mfa_enabled, failed_login_attempts);
    """))
    
    # MFA and security indexes
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_mfa_status 
        ON users (mfa_enabled, mfa_enabled_at) 
        WHERE is_active = true;
    """))
    
    # ==========================================
    # BACKUP SYSTEM OPTIMIZATION
    # ==========================================
    print("💾 Optimizing backup system tables...")
    
    # Backup executions performance
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_backup_executions_status_time 
        ON backup_executions (status, created_at DESC) 
        INCLUDE (backup_id, backup_type, size_bytes, duration_seconds);
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_backup_executions_recent_by_schedule 
        ON backup_executions (schedule_id, created_at DESC, status) 
        WHERE schedule_id IS NOT NULL;
    """))
    
    # Backup health monitoring
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_backup_health_checks_status 
        ON backup_health_checks (status, checked_at DESC, target_type) 
        INCLUDE (health_score, check_type);
    """))
    
    # Cleanup history optimization
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_backup_cleanup_efficiency 
        ON backup_cleanup_history (started_at DESC, space_freed_bytes DESC, status) 
        INCLUDE (backups_deleted, duration_seconds);
    """))
    
    # ==========================================
    # SECURITY CONFIGURATION OPTIMIZATION
    # ==========================================
    print("⚙️ Optimizing security configuration tables...")
    
    # IP blocklist performance
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ip_blocklist_active_lookups 
        ON ip_blocklist (ip_address, is_active, expires_at) 
        WHERE is_active = true;
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_ip_blocklist_threat_analysis 
        ON ip_blocklist (threat_level, created_at DESC, incident_count) 
        WHERE is_active = true;
    """))
    
    # Security incidents optimization
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_security_incidents_active 
        ON security_incidents (status, priority, first_detected DESC) 
        WHERE status IN ('open', 'investigating');
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_security_incidents_impact_analysis 
        ON security_incidents (threat_level, data_compromised, created_at DESC) 
        INCLUDE (affected_systems, estimated_impact);
    """))
    
    # Session security tracking
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_session_security_active_admin 
        ON session_security (user_id, is_admin_session, login_at DESC) 
        WHERE logout_at IS NULL AND is_admin_session = true;
    """))
    
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_session_security_risk_monitoring 
        ON session_security (risk_score DESC, is_suspicious, login_at DESC) 
        WHERE logout_at IS NULL;
    """))
    
    # ==========================================
    # PROJECT AND PAGE OPTIMIZATION
    # ==========================================
    print("📄 Optimizing project and page tables...")
    
    # Check if tables exist before creating indexes
    op.execute(text("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'pages') THEN
                CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_pages_admin_overview 
                ON pages (created_at DESC, domain_id) 
                INCLUDE (url, title, word_count, status);
            END IF;
            
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'projects') THEN
                CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_projects_user_management 
                ON projects (owner_id, created_at DESC, is_active) 
                INCLUDE (name, description, domain_count);
            END IF;
            
            IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'domains') THEN
                CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_domains_project_overview 
                ON domains (project_id, is_active, created_at DESC) 
                INCLUDE (domain, scrape_frequency, last_scraped);
            END IF;
        END
        $$;
    """))
    
    # ==========================================
    # SPECIALIZED FUNCTIONAL INDEXES
    # ==========================================
    print("🎯 Creating specialized functional indexes...")
    
    # Text search optimization for audit logs
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_text_search 
        ON audit_logs USING gin (
            to_tsvector('english', 
                COALESCE(action, '') || ' ' || 
                COALESCE(resource_type, '') || ' ' || 
                COALESCE(error_message, '')
            )
        );
    """))
    
    # Email domain analysis for user management
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_email_domain 
        ON users (LOWER(SPLIT_PART(email, '@', 2)), approval_status) 
        WHERE is_active = true;
    """))
    
    # Time-based aggregation indexes
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_hourly_stats 
        ON audit_logs (DATE_TRUNC('hour', created_at), category);
    """))
    
    # ==========================================
    # PERFORMANCE MONITORING INDEXES
    # ==========================================
    print("📈 Creating performance monitoring indexes...")
    
    # Query performance tracking
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_performance_metrics 
        ON audit_logs (processing_time_ms DESC NULLS LAST, database_queries DESC NULLS LAST) 
        WHERE processing_time_ms IS NOT NULL;
    """))
    
    # Memory usage analysis
    op.execute(text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_audit_logs_memory_usage 
        ON audit_logs (memory_usage_mb DESC NULLS LAST, created_at DESC) 
        WHERE memory_usage_mb IS NOT NULL;
    """))
    
    # ==========================================
    # DATABASE STATISTICS UPDATE
    # ==========================================
    print("📊 Updating table statistics...")
    
    tables_to_analyze = [
        'audit_logs', 'security_events', 'users', 'backup_executions',
        'backup_health_checks', 'ip_blocklist', 'security_incidents',
        'session_security', 'pages', 'projects', 'domains'
    ]
    
    for table in tables_to_analyze:
        op.execute(text(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}') THEN
                    ANALYZE {table};
                END IF;
            END
            $$;
        """))
    
    print("✅ Database performance optimization completed successfully!")
    
    # Create a summary comment
    op.execute(text("""
        COMMENT ON SCHEMA public IS 
        'Admin system with comprehensive performance optimizations applied. 
         Includes strategic indexes for audit logs, security events, user management, 
         backup operations, and real-time monitoring. Optimized for high-volume 
         admin operations and real-time dashboards.';
    """))


def downgrade():
    """Remove performance optimizations"""
    
    print("🔄 Removing performance optimizations...")
    
    # List of indexes to remove (in reverse order of creation)
    indexes_to_drop = [
        'ix_audit_logs_memory_usage',
        'ix_audit_logs_performance_metrics',
        'ix_audit_logs_hourly_stats',
        'ix_users_email_domain',
        'ix_audit_logs_text_search',
        'ix_domains_project_overview',
        'ix_projects_user_management',
        'ix_pages_admin_overview',
        'ix_session_security_risk_monitoring',
        'ix_session_security_active_admin',
        'ix_security_incidents_impact_analysis',
        'ix_security_incidents_active',
        'ix_ip_blocklist_threat_analysis',
        'ix_ip_blocklist_active_lookups',
        'ix_backup_cleanup_efficiency',
        'ix_backup_health_checks_status',
        'ix_backup_executions_recent_by_schedule',
        'ix_backup_executions_status_time',
        'ix_users_mfa_status',
        'ix_users_auth_lookup',
        'ix_users_approval_queue',
        'ix_users_security_status',
        'ix_users_admin_dashboard',
        'ix_security_events_threat_indicators_gin',
        'ix_security_events_user_behavior',
        'ix_security_events_high_risk',
        'ix_security_events_recent_failures',
        'ix_security_events_recent_by_ip',
        'ix_audit_logs_tags_gin',
        'ix_audit_logs_details_gin',
        'ix_audit_logs_compliance_relevant',
        'ix_audit_logs_failed_operations',
        'ix_audit_logs_dashboard_metrics',
        'ix_audit_logs_bulk_operations',
        'ix_audit_logs_security_events',
        'ix_audit_logs_admin_activity',
        'ix_audit_logs_created_at_day',
        'ix_audit_logs_created_at_month'
    ]
    
    for index_name in indexes_to_drop:
        op.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name};"))
    
    print("✅ Performance optimization removal completed!")