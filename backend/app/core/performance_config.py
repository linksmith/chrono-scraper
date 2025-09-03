"""
Performance Optimization Configuration

This module provides configuration management for all performance optimization
components including database indexes, caching strategies, and monitoring settings.
"""

from typing import Dict, List, Any
from pydantic import BaseSettings, Field
from enum import Enum


class CacheLevel(str, Enum):
    """Cache levels with different TTL strategies"""
    MEMORY = "memory"        # In-process memory cache (fastest)
    REDIS_FAST = "redis_fast"     # Redis with short TTL (30-60s)
    REDIS_MEDIUM = "redis_medium"  # Redis with medium TTL (5-15 min)
    REDIS_PERSISTENT = "redis_persistent"  # Redis with long TTL (1+ hours)


class PerformanceSettings(BaseSettings):
    """Performance optimization settings"""
    
    # Database Performance Settings
    DB_QUERY_TIMEOUT_SECONDS: int = Field(30, description="Query timeout in seconds")
    DB_SLOW_QUERY_THRESHOLD_MS: int = Field(1000, description="Slow query threshold")
    DB_CRITICAL_QUERY_THRESHOLD_MS: int = Field(5000, description="Critical query threshold")
    DB_CONNECTION_POOL_SIZE: int = Field(20, description="Database connection pool size")
    DB_CONNECTION_POOL_MAX_OVERFLOW: int = Field(10, description="Max pool overflow")
    DB_CONNECTION_POOL_TIMEOUT: int = Field(30, description="Pool timeout in seconds")
    
    # Cache Configuration
    CACHE_DEFAULT_TTL_SECONDS: int = Field(300, description="Default cache TTL (5 minutes)")
    CACHE_MEMORY_SIZE: int = Field(2000, description="In-memory cache size")
    CACHE_COMPRESSION_ENABLED: bool = Field(True, description="Enable cache compression")
    CACHE_METRICS_ENABLED: bool = Field(True, description="Enable cache metrics tracking")
    
    # Redis Cache Settings
    REDIS_CACHE_DB: int = Field(1, description="Redis database for caching")
    REDIS_CACHE_MAX_CONNECTIONS: int = Field(50, description="Max Redis connections for cache")
    REDIS_CACHE_CONNECTION_TIMEOUT: int = Field(5, description="Redis connection timeout")
    
    # Performance Monitoring
    PERFORMANCE_MONITORING_ENABLED: bool = Field(True, description="Enable performance monitoring")
    PERFORMANCE_METRICS_RETENTION_HOURS: int = Field(24, description="Metrics retention period")
    PERFORMANCE_ANALYSIS_INTERVAL_MINUTES: int = Field(30, description="Analysis interval")
    PERFORMANCE_HEALTH_CHECK_INTERVAL_MINUTES: int = Field(5, description="Health check interval")
    
    # Background Task Settings
    CACHE_WARMUP_INTERVAL_MINUTES: int = Field(15, description="Cache warmup interval")
    CLEANUP_INTERVAL_HOURS: int = Field(6, description="Cleanup task interval")
    BACKGROUND_TASK_MAX_RETRIES: int = Field(3, description="Max retries for background tasks")
    
    # Query Optimization
    QUERY_OPTIMIZATION_ENABLED: bool = Field(True, description="Enable query optimization")
    QUERY_ANALYSIS_CACHE_SIZE: int = Field(1000, description="Query analysis cache size")
    N_PLUS_ONE_DETECTION_ENABLED: bool = Field(True, description="Enable N+1 detection")
    
    # Admin-Specific Settings
    ADMIN_CACHE_NAMESPACE_PREFIX: str = Field("admin", description="Cache namespace prefix")
    ADMIN_QUERY_MONITORING_ENABLED: bool = Field(True, description="Monitor admin queries")
    ADMIN_CACHE_WARMUP_ON_STARTUP: bool = Field(True, description="Warm cache on startup")
    
    # Performance Thresholds
    DATABASE_HEALTH_CACHE_HIT_RATIO_MIN: float = Field(85.0, description="Min cache hit ratio")
    DATABASE_HEALTH_INDEX_USAGE_RATIO_MIN: float = Field(95.0, description="Min index usage ratio")
    DATABASE_HEALTH_MAX_SLOW_QUERIES: int = Field(10, description="Max slow queries threshold")
    SYSTEM_HEALTH_SCORE_MIN: int = Field(80, description="Minimum health score")
    
    class Config:
        env_prefix = "PERF_"
        case_sensitive = True


class AdminCacheConfig:
    """Configuration for admin-specific caching patterns"""
    
    @staticmethod
    def get_cache_configurations() -> Dict[str, Dict[str, Any]]:
        """Get cache configurations for different admin operation types"""
        return {
            # Real-time admin dashboard metrics
            "admin:dashboard:*": {
                "ttl_seconds": 60,  # 1 minute for real-time feel
                "compression": True,
                "priority": "high",
                "auto_refresh": True,
                "refresh_threshold": 0.7  # Refresh when 70% of TTL expired
            },
            
            # User management operations
            "admin:users:*": {
                "ttl_seconds": 300,  # 5 minutes
                "compression": True,
                "priority": "high",
                "invalidate_on_update": True
            },
            
            # Audit log analytics (can be cached longer)
            "admin:audit:analytics:*": {
                "ttl_seconds": 900,  # 15 minutes
                "compression": True,
                "priority": "medium",
                "batch_invalidation": True
            },
            
            # Security monitoring (needs frequent updates)
            "admin:security:*": {
                "ttl_seconds": 30,  # 30 seconds
                "compression": False,  # Speed over space
                "priority": "critical",
                "auto_refresh": True,
                "refresh_threshold": 0.5
            },
            
            # System statistics and metrics
            "admin:system:*": {
                "ttl_seconds": 120,  # 2 minutes
                "compression": True,
                "priority": "medium",
                "background_refresh": True
            },
            
            # Backup and recovery data
            "admin:backup:*": {
                "ttl_seconds": 600,  # 10 minutes
                "compression": True,
                "priority": "low",
                "lazy_loading": True
            },
            
            # Query optimization and performance data
            "admin:performance:*": {
                "ttl_seconds": 180,  # 3 minutes
                "compression": True,
                "priority": "medium"
            }
        }


class DatabaseIndexConfig:
    """Configuration for database index optimizations"""
    
    @staticmethod
    def get_recommended_indexes() -> List[Dict[str, Any]]:
        """Get list of recommended indexes for admin operations"""
        return [
            # User management indexes
            {
                "name": "idx_users_admin_dashboard",
                "table": "users",
                "columns": ["approval_status", "is_active", "created_at"],
                "type": "btree",
                "description": "Optimizes admin user dashboard queries",
                "estimated_improvement": "60-80% faster user listing",
                "priority": "high"
            },
            {
                "name": "idx_users_login_lookup",
                "table": "users",
                "columns": ["email", "is_active", "is_locked"],
                "type": "btree",
                "description": "Optimizes user authentication queries",
                "estimated_improvement": "40-60% faster login verification",
                "priority": "high"
            },
            {
                "name": "idx_users_security_monitoring",
                "table": "users",
                "columns": ["risk_score", "last_login", "failed_login_attempts"],
                "type": "btree",
                "description": "Optimizes security monitoring queries",
                "estimated_improvement": "50-70% faster security analysis",
                "priority": "medium"
            },
            
            # Audit log indexes
            {
                "name": "idx_audit_logs_admin_activity",
                "table": "audit_logs",
                "columns": ["admin_user_id", "created_at", "category"],
                "type": "btree",
                "where_clause": "admin_user_id IS NOT NULL",
                "description": "Optimizes admin activity tracking",
                "estimated_improvement": "70-90% faster admin audit queries",
                "priority": "high"
            },
            {
                "name": "idx_audit_logs_time_category",
                "table": "audit_logs",
                "columns": ["created_at", "category"],
                "type": "btree",
                "description": "Optimizes time-based audit queries",
                "estimated_improvement": "60-80% faster audit log filtering",
                "priority": "high"
            },
            {
                "name": "idx_audit_logs_security_events",
                "table": "audit_logs",
                "columns": ["category", "severity", "created_at"],
                "type": "btree",
                "where_clause": "category = 'security_event'",
                "description": "Optimizes security event audit queries",
                "estimated_improvement": "80-95% faster security audit queries",
                "priority": "high"
            },
            {
                "name": "idx_audit_logs_compliance",
                "table": "audit_logs",
                "columns": ["gdpr_relevant", "sox_relevant", "hipaa_relevant", "created_at"],
                "type": "btree",
                "where_clause": "gdpr_relevant = true OR sox_relevant = true OR hipaa_relevant = true",
                "description": "Optimizes compliance reporting queries",
                "estimated_improvement": "85-95% faster compliance queries",
                "priority": "medium"
            },
            
            # Security events indexes
            {
                "name": "idx_security_events_threat_analysis",
                "table": "security_events",
                "columns": ["ip_address", "event_type", "created_at"],
                "type": "btree",
                "description": "Optimizes threat analysis queries",
                "estimated_improvement": "70-90% faster security analysis",
                "priority": "high"
            },
            {
                "name": "idx_security_events_risk_monitoring",
                "table": "security_events",
                "columns": ["risk_score", "created_at", "success"],
                "type": "btree",
                "description": "Optimizes risk monitoring queries",
                "estimated_improvement": "60-80% faster risk analysis",
                "priority": "high"
            },
            {
                "name": "idx_security_events_recent_failures",
                "table": "security_events",
                "columns": ["created_at", "success", "event_type"],
                "type": "btree",
                "where_clause": "success = false AND created_at > NOW() - INTERVAL '7 days'",
                "description": "Optimizes recent failure analysis",
                "estimated_improvement": "90-95% faster failure analysis",
                "priority": "medium"
            },
            
            # Backup system indexes
            {
                "name": "idx_backup_executions_monitoring",
                "table": "backup_executions",
                "columns": ["status", "created_at", "backup_type"],
                "type": "btree",
                "description": "Optimizes backup monitoring queries",
                "estimated_improvement": "50-70% faster backup status queries",
                "priority": "medium"
            },
            {
                "name": "idx_backup_executions_schedule_history",
                "table": "backup_executions",
                "columns": ["schedule_id", "created_at", "status"],
                "type": "btree",
                "where_clause": "schedule_id IS NOT NULL",
                "description": "Optimizes backup history queries",
                "estimated_improvement": "60-80% faster backup history",
                "priority": "medium"
            },
            
            # IP blocklist indexes
            {
                "name": "idx_ip_blocklist_active_lookups",
                "table": "ip_blocklist",
                "columns": ["ip_address", "is_active", "expires_at"],
                "type": "btree",
                "where_clause": "is_active = true",
                "description": "Optimizes active IP blocking lookups",
                "estimated_improvement": "80-95% faster IP blocking checks",
                "priority": "high"
            },
            {
                "name": "idx_ip_blocklist_threat_analysis",
                "table": "ip_blocklist",
                "columns": ["threat_level", "created_at", "incident_count"],
                "type": "btree",
                "where_clause": "is_active = true",
                "description": "Optimizes threat level analysis",
                "estimated_improvement": "70-90% faster threat analysis",
                "priority": "medium"
            },
            
            # Session security indexes
            {
                "name": "idx_session_security_admin_monitoring",
                "table": "session_security",
                "columns": ["is_admin_session", "is_suspicious", "login_at"],
                "type": "btree",
                "where_clause": "logout_at IS NULL",
                "description": "Optimizes admin session monitoring",
                "estimated_improvement": "60-80% faster session monitoring",
                "priority": "high"
            },
            {
                "name": "idx_session_security_risk_tracking",
                "table": "session_security",
                "columns": ["risk_score", "user_id", "login_at"],
                "type": "btree",
                "description": "Optimizes risk-based session tracking",
                "estimated_improvement": "50-70% faster risk assessment",
                "priority": "medium"
            }
        ]
    
    @staticmethod
    def get_index_maintenance_config() -> Dict[str, Any]:
        """Get configuration for index maintenance operations"""
        return {
            "auto_analyze_threshold": 0.1,  # Analyze when 10% of table changes
            "auto_vacuum_threshold": 0.2,   # Vacuum when 20% of table changes
            "maintenance_window": {
                "start_hour": 2,  # 2 AM
                "end_hour": 4,    # 4 AM
                "timezone": "UTC"
            },
            "concurrent_operations": True,  # Use CONCURRENTLY when possible
            "monitor_index_bloat": True,
            "rebuild_threshold_ratio": 4.0,  # Rebuild when bloat ratio > 4x
            "unused_index_threshold_days": 30  # Report unused indexes after 30 days
        }


class QueryOptimizationConfig:
    """Configuration for query optimization features"""
    
    @staticmethod
    def get_optimization_patterns() -> Dict[str, Any]:
        """Get query optimization pattern configurations"""
        return {
            "n_plus_one_detection": {
                "enabled": True,
                "min_repetitions": 3,
                "time_window_ms": 1000,
                "track_patterns": [
                    "SELECT.*FROM users WHERE id = ?",
                    "SELECT.*FROM projects WHERE user_id = ?",
                    "SELECT.*FROM pages WHERE project_id = ?",
                    "SELECT.*FROM audit_logs WHERE user_id = ?"
                ]
            },
            "full_table_scan_detection": {
                "enabled": True,
                "large_table_threshold": 10000,  # Rows
                "monitor_tables": [
                    "users", "audit_logs", "security_events", 
                    "pages", "backup_executions"
                ]
            },
            "missing_index_suggestions": {
                "enabled": True,
                "analyze_frequency_hours": 6,
                "suggestion_confidence_threshold": 0.7
            },
            "query_rewrite_suggestions": {
                "enabled": True,
                "patterns": {
                    "select_star": {
                        "detect": "SELECT \\* FROM (users|audit_logs|pages)",
                        "suggest": "Use specific column selection for large tables"
                    },
                    "missing_limit": {
                        "detect": "SELECT.*FROM (users|audit_logs).*ORDER BY.*(?!LIMIT)",
                        "suggest": "Add LIMIT clause for pagination"
                    },
                    "inefficient_like": {
                        "detect": "WHERE.*LIKE '%.*%'",
                        "suggest": "Consider full-text search for pattern matching"
                    }
                }
            }
        }


class MonitoringConfig:
    """Configuration for performance monitoring"""
    
    @staticmethod
    def get_monitoring_thresholds() -> Dict[str, Any]:
        """Get performance monitoring thresholds and alerts"""
        return {
            "query_performance": {
                "excellent_threshold_ms": 50,
                "good_threshold_ms": 200,
                "acceptable_threshold_ms": 1000,
                "slow_threshold_ms": 5000,
                "critical_threshold_ms": 10000
            },
            "cache_performance": {
                "excellent_hit_ratio": 95.0,
                "good_hit_ratio": 90.0,
                "acceptable_hit_ratio": 80.0,
                "poor_hit_ratio": 70.0
            },
            "database_health": {
                "connection_usage_warning": 0.8,  # 80% of pool
                "connection_usage_critical": 0.95,  # 95% of pool
                "lock_count_warning": 5,
                "lock_count_critical": 20,
                "slow_queries_warning": 10,
                "slow_queries_critical": 50
            },
            "system_resources": {
                "memory_usage_warning": 0.85,  # 85% of available
                "memory_usage_critical": 0.95,  # 95% of available
                "cpu_usage_warning": 80.0,     # 80% CPU
                "cpu_usage_critical": 95.0     # 95% CPU
            }
        }
    
    @staticmethod
    def get_alert_configuration() -> Dict[str, Any]:
        """Get alerting configuration for performance issues"""
        return {
            "alert_channels": ["log", "email"],  # Could extend to Slack, etc.
            "alert_throttling": {
                "max_alerts_per_hour": 10,
                "cooldown_minutes": 15
            },
            "severity_levels": {
                "info": {"log_level": "INFO", "notify": False},
                "warning": {"log_level": "WARNING", "notify": True},
                "error": {"log_level": "ERROR", "notify": True},
                "critical": {"log_level": "ERROR", "notify": True, "escalate": True}
            },
            "performance_alerts": {
                "slow_query_burst": {
                    "threshold": 5,  # 5 slow queries in window
                    "window_minutes": 5,
                    "severity": "warning"
                },
                "cache_hit_ratio_drop": {
                    "threshold": 0.1,  # 10% drop
                    "window_minutes": 10,
                    "severity": "warning"
                },
                "database_connection_exhaustion": {
                    "threshold": 0.9,  # 90% of pool
                    "severity": "critical"
                }
            }
        }


# Global settings instance
performance_settings = PerformanceSettings()