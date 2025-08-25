"""
Database Performance Monitoring Service

This service provides comprehensive database performance monitoring, query analysis,
and optimization recommendations specifically for the admin system.
"""

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import psutil
import statistics
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PerformanceLevel(str, Enum):
    """Performance level classifications"""
    EXCELLENT = "excellent"  # < 50ms
    GOOD = "good"  # 50ms - 200ms  
    ACCEPTABLE = "acceptable"  # 200ms - 1000ms
    SLOW = "slow"  # 1000ms - 5000ms
    CRITICAL = "critical"  # > 5000ms


class QueryType(str, Enum):
    """Types of database queries"""
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    BULK_OPERATION = "bulk_operation"
    ANALYTICS = "analytics"
    DASHBOARD = "dashboard"
    ADMIN_OPERATION = "admin_operation"


@dataclass
class QueryMetrics:
    """Metrics for a database query"""
    query_hash: str
    query_type: QueryType
    execution_time_ms: float
    cpu_time_ms: Optional[float]
    io_time_ms: Optional[float]
    rows_examined: Optional[int]
    rows_returned: Optional[int]
    memory_used_mb: Optional[float]
    temp_files_created: Optional[int]
    index_usage: List[str]
    table_scans: int
    performance_level: PerformanceLevel
    timestamp: datetime
    user_id: Optional[int] = None
    admin_operation: Optional[str] = None


class DatabaseStats(BaseModel):
    """Database performance statistics"""
    total_connections: int
    active_connections: int
    idle_connections: int
    slow_queries_count: int
    avg_query_time_ms: float
    queries_per_second: float
    cache_hit_ratio: float
    index_usage_ratio: float
    lock_contention_count: int
    deadlock_count: int
    memory_usage_mb: float
    cpu_usage_percent: float
    disk_io_ops: int
    buffer_hit_ratio: float


class TableStats(BaseModel):
    """Statistics for specific tables"""
    table_name: str
    total_size_mb: float
    index_size_mb: float
    row_count: int
    sequential_scans: int
    sequential_scan_rows: int
    index_scans: int
    index_scan_rows: int
    inserts: int
    updates: int
    deletes: int
    hot_updates: int
    vacuum_count: int
    analyze_count: int
    last_vacuum: Optional[datetime]
    last_analyze: Optional[datetime]


class IndexStats(BaseModel):
    """Statistics for database indexes"""
    schema_name: str
    table_name: str
    index_name: str
    size_mb: float
    scans: int
    tuples_read: int
    tuples_fetched: int
    usage_ratio: float
    last_used: Optional[datetime]
    is_unique: bool
    columns: List[str]


class SlowQuery(BaseModel):
    """Slow query analysis"""
    query_hash: str
    query_text: str
    avg_execution_time_ms: float
    max_execution_time_ms: float
    execution_count: int
    total_time_ms: float
    rows_examined_avg: Optional[int]
    rows_returned_avg: Optional[int]
    first_seen: datetime
    last_seen: datetime
    tables_involved: List[str]
    recommended_indexes: List[str]
    optimization_suggestions: List[str]


class PerformanceMonitoringService:
    """
    Comprehensive database performance monitoring service.
    
    Features:
    - Real-time query performance tracking
    - Slow query detection and analysis
    - Index usage monitoring
    - Connection pool monitoring
    - Resource utilization tracking
    - Performance trend analysis
    - Optimization recommendations
    """
    
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self.query_metrics: List[QueryMetrics] = []
        self.performance_thresholds = {
            PerformanceLevel.EXCELLENT: 50,
            PerformanceLevel.GOOD: 200,
            PerformanceLevel.ACCEPTABLE: 1000,
            PerformanceLevel.SLOW: 5000
        }
        self.monitoring_enabled = True
        
        # Admin-specific query patterns
        self.admin_query_patterns = {
            "user_management": [
                "SELECT.*FROM users.*approval_status",
                "UPDATE users SET.*approval_status",
                "SELECT.*COUNT.*FROM users.*GROUP BY"
            ],
            "audit_analysis": [
                "SELECT.*FROM audit_logs.*WHERE.*created_at",
                "SELECT.*COUNT.*FROM audit_logs.*GROUP BY.*category",
                "SELECT.*FROM audit_logs.*ORDER BY.*created_at.*DESC"
            ],
            "security_monitoring": [
                "SELECT.*FROM security_events",
                "SELECT.*FROM ip_blocklist",
                "UPDATE ip_blocklist SET.*is_active"
            ],
            "backup_operations": [
                "SELECT.*FROM backup_executions",
                "INSERT INTO backup_executions",
                "UPDATE backup_executions SET.*status"
            ]
        }
    
    @asynccontextmanager
    async def monitor_query(
        self, 
        query_type: QueryType = QueryType.SELECT,
        admin_operation: Optional[str] = None,
        user_id: Optional[int] = None
    ):
        """Context manager to monitor query performance"""
        if not self.monitoring_enabled:
            yield
            return
        
        start_time = time.time()
        start_cpu = time.process_time()
        
        # Get initial system stats
        process = psutil.Process()
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        try:
            yield
        finally:
            # Calculate metrics
            end_time = time.time()
            end_cpu = time.process_time()
            end_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            execution_time_ms = (end_time - start_time) * 1000
            cpu_time_ms = (end_cpu - start_cpu) * 1000
            memory_used_mb = max(0, end_memory - start_memory)
            
            # Determine performance level
            performance_level = self._classify_performance(execution_time_ms)
            
            # Create metrics record
            metrics = QueryMetrics(
                query_hash="generated_hash",  # Would be actual hash in real implementation
                query_type=query_type,
                execution_time_ms=execution_time_ms,
                cpu_time_ms=cpu_time_ms,
                io_time_ms=max(0, execution_time_ms - cpu_time_ms),
                rows_examined=None,  # Would be extracted from EXPLAIN ANALYZE
                rows_returned=None,
                memory_used_mb=memory_used_mb,
                temp_files_created=None,
                index_usage=[],
                table_scans=0,
                performance_level=performance_level,
                timestamp=datetime.now(),
                user_id=user_id,
                admin_operation=admin_operation
            )
            
            # Store metrics
            self.query_metrics.append(metrics)
            
            # Keep only recent metrics (last 1000 queries)
            if len(self.query_metrics) > 1000:
                self.query_metrics = self.query_metrics[-1000:]
            
            # Log slow queries
            if performance_level in [PerformanceLevel.SLOW, PerformanceLevel.CRITICAL]:
                logger.warning(
                    f"Slow query detected: {admin_operation or query_type.value} "
                    f"took {execution_time_ms:.2f}ms"
                )
    
    def _classify_performance(self, execution_time_ms: float) -> PerformanceLevel:
        """Classify query performance based on execution time"""
        if execution_time_ms < self.performance_thresholds[PerformanceLevel.EXCELLENT]:
            return PerformanceLevel.EXCELLENT
        elif execution_time_ms < self.performance_thresholds[PerformanceLevel.GOOD]:
            return PerformanceLevel.GOOD
        elif execution_time_ms < self.performance_thresholds[PerformanceLevel.ACCEPTABLE]:
            return PerformanceLevel.ACCEPTABLE
        elif execution_time_ms < self.performance_thresholds[PerformanceLevel.SLOW]:
            return PerformanceLevel.SLOW
        else:
            return PerformanceLevel.CRITICAL
    
    async def get_database_stats(self) -> DatabaseStats:
        """Get comprehensive database statistics"""
        async with self.db_session_factory() as session:
            try:
                # Connection stats
                connection_stats = await session.execute(text("""
                    SELECT 
                        count(*) as total_connections,
                        count(*) FILTER (WHERE state = 'active') as active_connections,
                        count(*) FILTER (WHERE state = 'idle') as idle_connections
                    FROM pg_stat_activity 
                    WHERE datname = current_database()
                """))
                conn_result = connection_stats.fetchone()
                
                # Cache hit ratio
                cache_stats = await session.execute(text("""
                    SELECT 
                        sum(heap_blks_hit) / NULLIF(sum(heap_blks_hit) + sum(heap_blks_read), 0) * 100 as cache_hit_ratio
                    FROM pg_statio_user_tables
                """))
                cache_result = cache_stats.fetchone()
                
                # Buffer hit ratio
                buffer_stats = await session.execute(text("""
                    SELECT 
                        round(
                            100.0 * sum(blks_hit) / NULLIF(sum(blks_hit) + sum(blks_read), 0), 
                            2
                        ) as buffer_hit_ratio
                    FROM pg_stat_database 
                    WHERE datname = current_database()
                """))
                buffer_result = buffer_stats.fetchone()
                
                # Index usage ratio
                index_stats = await session.execute(text("""
                    SELECT 
                        round(
                            100.0 * sum(idx_scan) / NULLIF(sum(seq_scan) + sum(idx_scan), 0), 
                            2
                        ) as index_usage_ratio
                    FROM pg_stat_user_tables
                """))
                index_result = index_stats.fetchone()
                
                # Database size
                db_size_stats = await session.execute(text("""
                    SELECT pg_size_pretty(pg_database_size(current_database())) as db_size
                """))
                db_size_result = db_size_stats.fetchone()
                
                # Lock information
                lock_stats = await session.execute(text("""
                    SELECT count(*) as lock_count
                    FROM pg_locks 
                    WHERE NOT granted
                """))
                lock_result = lock_stats.fetchone()
                
                # Get system stats
                memory_usage = psutil.virtual_memory().used / 1024 / 1024  # MB
                cpu_usage = psutil.cpu_percent(interval=1)
                
                # Calculate metrics from recent queries
                recent_queries = [q for q in self.query_metrics if q.timestamp > datetime.now() - timedelta(minutes=5)]
                avg_query_time = statistics.mean([q.execution_time_ms for q in recent_queries]) if recent_queries else 0
                queries_per_second = len(recent_queries) / 300 if recent_queries else 0  # 5 minutes = 300 seconds
                slow_queries = [q for q in recent_queries if q.performance_level in [PerformanceLevel.SLOW, PerformanceLevel.CRITICAL]]
                
                return DatabaseStats(
                    total_connections=conn_result.total_connections or 0,
                    active_connections=conn_result.active_connections or 0,
                    idle_connections=conn_result.idle_connections or 0,
                    slow_queries_count=len(slow_queries),
                    avg_query_time_ms=avg_query_time,
                    queries_per_second=queries_per_second,
                    cache_hit_ratio=float(cache_result.cache_hit_ratio or 0),
                    index_usage_ratio=float(index_result.index_usage_ratio or 0),
                    lock_contention_count=lock_result.lock_count or 0,
                    deadlock_count=0,  # Would need pg_stat_database for accurate count
                    memory_usage_mb=memory_usage,
                    cpu_usage_percent=cpu_usage,
                    disk_io_ops=0,  # Would need system monitoring
                    buffer_hit_ratio=float(buffer_result.buffer_hit_ratio or 0)
                )
                
            except Exception as e:
                logger.error(f"Error getting database stats: {str(e)}")
                # Return minimal stats on error
                return DatabaseStats(
                    total_connections=0,
                    active_connections=0,
                    idle_connections=0,
                    slow_queries_count=0,
                    avg_query_time_ms=0,
                    queries_per_second=0,
                    cache_hit_ratio=0,
                    index_usage_ratio=0,
                    lock_contention_count=0,
                    deadlock_count=0,
                    memory_usage_mb=0,
                    cpu_usage_percent=0,
                    disk_io_ops=0,
                    buffer_hit_ratio=0
                )
    
    async def get_table_stats(self) -> List[TableStats]:
        """Get statistics for all tables"""
        async with self.db_session_factory() as session:
            try:
                # Focus on admin-related tables
                admin_tables = [
                    'users', 'audit_logs', 'security_events', 'ip_blocklist',
                    'backup_executions', 'backup_schedules', 'security_incidents',
                    'session_security', 'pages', 'projects', 'domains'
                ]
                
                stats_query = text("""
                    SELECT 
                        schemaname,
                        tablename,
                        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
                        pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) as index_size,
                        n_tup_ins as inserts,
                        n_tup_upd as updates,
                        n_tup_del as deletes,
                        n_tup_hot_upd as hot_updates,
                        seq_scan,
                        seq_tup_read,
                        idx_scan,
                        idx_tup_fetch,
                        vacuum_count,
                        autovacuum_count,
                        analyze_count,
                        autoanalyze_count,
                        last_vacuum,
                        last_autovacuum,
                        last_analyze,
                        last_autoanalyze
                    FROM pg_stat_user_tables 
                    WHERE tablename = ANY(:table_names)
                    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                """)
                
                result = await session.execute(stats_query, {"table_names": admin_tables})
                
                table_stats = []
                for row in result:
                    # Get row count estimate
                    row_count_query = text(f"""
                        SELECT reltuples::bigint as estimate 
                        FROM pg_class 
                        WHERE relname = :table_name
                    """)
                    row_count_result = await session.execute(row_count_query, {"table_name": row.tablename})
                    row_count = row_count_result.scalar() or 0
                    
                    # Parse sizes (remove units for numeric comparison)
                    total_size_mb = self._parse_postgres_size(row.total_size)
                    index_size_mb = self._parse_postgres_size(row.index_size)
                    
                    table_stats.append(TableStats(
                        table_name=row.tablename,
                        total_size_mb=total_size_mb,
                        index_size_mb=index_size_mb,
                        row_count=int(row_count),
                        sequential_scans=row.seq_scan or 0,
                        sequential_scan_rows=row.seq_tup_read or 0,
                        index_scans=row.idx_scan or 0,
                        index_scan_rows=row.idx_tup_fetch or 0,
                        inserts=row.inserts or 0,
                        updates=row.updates or 0,
                        deletes=row.deletes or 0,
                        hot_updates=row.hot_updates or 0,
                        vacuum_count=(row.vacuum_count or 0) + (row.autovacuum_count or 0),
                        analyze_count=(row.analyze_count or 0) + (row.autoanalyze_count or 0),
                        last_vacuum=row.last_vacuum or row.last_autovacuum,
                        last_analyze=row.last_analyze or row.last_autoanalyze
                    ))
                
                return table_stats
                
            except Exception as e:
                logger.error(f"Error getting table stats: {str(e)}")
                return []
    
    async def get_index_stats(self) -> List[IndexStats]:
        """Get statistics for database indexes"""
        async with self.db_session_factory() as session:
            try:
                index_query = text("""
                    SELECT 
                        schemaname,
                        tablename,
                        indexname,
                        pg_size_pretty(pg_relation_size(schemaname||'.'||indexname)) as size,
                        idx_scan,
                        idx_tup_read,
                        idx_tup_fetch,
                        indisunique,
                        string_agg(att.attname, ',' ORDER BY att.attnum) as columns
                    FROM pg_stat_user_indexes pgsui
                    JOIN pg_index pgi ON pgsui.indexrelid = pgi.indexrelid
                    JOIN pg_attribute att ON att.attrelid = pgi.indrelid 
                        AND att.attnum = ANY(pgi.indkey)
                    WHERE schemaname = 'public'
                        AND tablename IN ('users', 'audit_logs', 'security_events', 
                                         'backup_executions', 'pages', 'projects')
                    GROUP BY schemaname, tablename, indexname, idx_scan, 
                             idx_tup_read, idx_tup_fetch, indisunique,
                             pg_relation_size(schemaname||'.'||indexname)
                    ORDER BY pg_relation_size(schemaname||'.'||indexname) DESC
                """)
                
                result = await session.execute(index_query)
                
                index_stats = []
                for row in result:
                    size_mb = self._parse_postgres_size(row.size)
                    usage_ratio = 0.0
                    
                    if row.idx_tup_read and row.idx_tup_read > 0:
                        usage_ratio = (row.idx_tup_fetch or 0) / row.idx_tup_read * 100
                    
                    index_stats.append(IndexStats(
                        schema_name=row.schemaname,
                        table_name=row.tablename,
                        index_name=row.indexname,
                        size_mb=size_mb,
                        scans=row.idx_scan or 0,
                        tuples_read=row.idx_tup_read or 0,
                        tuples_fetched=row.idx_tup_fetch or 0,
                        usage_ratio=usage_ratio,
                        last_used=None,  # PostgreSQL doesn't track this by default
                        is_unique=row.indisunique,
                        columns=row.columns.split(',') if row.columns else []
                    ))
                
                return index_stats
                
            except Exception as e:
                logger.error(f"Error getting index stats: {str(e)}")
                return []
    
    def _parse_postgres_size(self, size_str: str) -> float:
        """Parse PostgreSQL size string to MB"""
        if not size_str:
            return 0.0
        
        size_str = size_str.replace(' ', '').upper()
        
        if 'TB' in size_str:
            return float(size_str.replace('TB', '')) * 1024 * 1024
        elif 'GB' in size_str:
            return float(size_str.replace('GB', '')) * 1024
        elif 'MB' in size_str:
            return float(size_str.replace('MB', ''))
        elif 'KB' in size_str:
            return float(size_str.replace('KB', '')) / 1024
        elif 'BYTES' in size_str:
            return float(size_str.replace('BYTES', '')) / 1024 / 1024
        else:
            # Try to parse as numeric bytes
            try:
                return float(size_str) / 1024 / 1024
            except:
                return 0.0
    
    async def analyze_slow_queries(self, hours: int = 24) -> List[SlowQuery]:
        """Analyze slow queries from recent metrics"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Group queries by type and operation
        slow_queries_dict = {}
        
        for metric in self.query_metrics:
            if metric.timestamp < cutoff_time:
                continue
            
            if metric.performance_level not in [PerformanceLevel.SLOW, PerformanceLevel.CRITICAL]:
                continue
            
            key = f"{metric.query_type.value}_{metric.admin_operation or 'unknown'}"
            
            if key not in slow_queries_dict:
                slow_queries_dict[key] = {
                    'execution_times': [],
                    'first_seen': metric.timestamp,
                    'last_seen': metric.timestamp,
                    'query_type': metric.query_type,
                    'admin_operation': metric.admin_operation
                }
            
            slow_queries_dict[key]['execution_times'].append(metric.execution_time_ms)
            slow_queries_dict[key]['last_seen'] = max(slow_queries_dict[key]['last_seen'], metric.timestamp)
            slow_queries_dict[key]['first_seen'] = min(slow_queries_dict[key]['first_seen'], metric.timestamp)
        
        # Generate slow query analysis
        slow_queries = []
        for key, data in slow_queries_dict.items():
            execution_times = data['execution_times']
            
            # Generate optimization suggestions based on query type
            suggestions = self._generate_optimization_suggestions(
                data['query_type'], 
                data['admin_operation']
            )
            
            slow_query = SlowQuery(
                query_hash=key,
                query_text=f"{data['query_type'].value} operation: {data['admin_operation'] or 'unknown'}",
                avg_execution_time_ms=statistics.mean(execution_times),
                max_execution_time_ms=max(execution_times),
                execution_count=len(execution_times),
                total_time_ms=sum(execution_times),
                rows_examined_avg=None,
                rows_returned_avg=None,
                first_seen=data['first_seen'],
                last_seen=data['last_seen'],
                tables_involved=self._infer_tables_from_operation(data['admin_operation']),
                recommended_indexes=suggestions['indexes'],
                optimization_suggestions=suggestions['general']
            )
            
            slow_queries.append(slow_query)
        
        # Sort by total time impact
        slow_queries.sort(key=lambda x: x.total_time_ms, reverse=True)
        
        return slow_queries
    
    def _generate_optimization_suggestions(
        self, 
        query_type: QueryType, 
        admin_operation: Optional[str]
    ) -> Dict[str, List[str]]:
        """Generate optimization suggestions for slow queries"""
        suggestions = {
            'indexes': [],
            'general': []
        }
        
        if not admin_operation:
            return suggestions
        
        # User management optimizations
        if 'user' in admin_operation.lower():
            suggestions['indexes'].extend([
                'CREATE INDEX CONCURRENTLY idx_users_approval_status_active ON users (approval_status, is_active);',
                'CREATE INDEX CONCURRENTLY idx_users_email_verification ON users (email, is_verified, is_active);'
            ])
            suggestions['general'].extend([
                'Consider using LIMIT for large user lists',
                'Cache user counts and statistics',
                'Use bulk operations for mass user updates'
            ])
        
        # Audit log optimizations
        elif 'audit' in admin_operation.lower():
            suggestions['indexes'].extend([
                'CREATE INDEX CONCURRENTLY idx_audit_logs_time_category ON audit_logs (created_at DESC, category);',
                'CREATE INDEX CONCURRENTLY idx_audit_logs_user_time ON audit_logs (user_id, created_at DESC);'
            ])
            suggestions['general'].extend([
                'Implement time-based partitioning for audit_logs',
                'Archive old audit records periodically',
                'Use materialized views for audit analytics'
            ])
        
        # Security monitoring optimizations
        elif 'security' in admin_operation.lower():
            suggestions['indexes'].extend([
                'CREATE INDEX CONCURRENTLY idx_security_events_recent_failures ON security_events (created_at DESC, success) WHERE success = false;',
                'CREATE INDEX CONCURRENTLY idx_ip_blocklist_active ON ip_blocklist (is_active, threat_level);'
            ])
            suggestions['general'].extend([
                'Use partial indexes for active security events',
                'Consider Redis for real-time IP blocking',
                'Implement connection pooling for high-frequency security checks'
            ])
        
        # Backup operations optimizations
        elif 'backup' in admin_operation.lower():
            suggestions['indexes'].extend([
                'CREATE INDEX CONCURRENTLY idx_backup_executions_status_time ON backup_executions (status, created_at DESC);'
            ])
            suggestions['general'].extend([
                'Use background jobs for backup status updates',
                'Cache backup statistics',
                'Implement backup metadata compression'
            ])
        
        # General optimizations for all slow queries
        suggestions['general'].extend([
            'Monitor query execution plans with EXPLAIN ANALYZE',
            'Consider increasing shared_buffers if memory allows',
            'Review and update table statistics with ANALYZE',
            'Consider read replicas for heavy reporting queries'
        ])
        
        return suggestions
    
    def _infer_tables_from_operation(self, admin_operation: Optional[str]) -> List[str]:
        """Infer which tables are involved based on admin operation"""
        if not admin_operation:
            return []
        
        table_mapping = {
            'user': ['users'],
            'audit': ['audit_logs'],
            'security': ['security_events', 'ip_blocklist', 'security_incidents'],
            'backup': ['backup_executions', 'backup_schedules'],
            'project': ['projects', 'domains', 'pages'],
            'dashboard': ['users', 'audit_logs', 'security_events', 'projects']
        }
        
        tables = []
        for keyword, table_list in table_mapping.items():
            if keyword in admin_operation.lower():
                tables.extend(table_list)
        
        return list(set(tables))  # Remove duplicates
    
    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        try:
            # Get recent metrics
            recent_metrics = [
                q for q in self.query_metrics 
                if q.timestamp > datetime.now() - timedelta(hours=1)
            ]
            
            # Calculate performance distribution
            performance_distribution = {level.value: 0 for level in PerformanceLevel}
            for metric in recent_metrics:
                performance_distribution[metric.performance_level.value] += 1
            
            # Get database stats
            db_stats = await self.get_database_stats()
            
            # Get slow queries
            slow_queries = await self.analyze_slow_queries(hours=24)
            
            # Calculate health score (0-100)
            health_score = self._calculate_health_score(db_stats, performance_distribution)
            
            return {
                "timestamp": datetime.now().isoformat(),
                "health_score": health_score,
                "database_stats": db_stats.dict(),
                "performance_distribution": performance_distribution,
                "recent_query_count": len(recent_metrics),
                "slow_queries_count": len(slow_queries),
                "top_slow_queries": [sq.dict() for sq in slow_queries[:5]],
                "recommendations": self._generate_general_recommendations(db_stats, slow_queries)
            }
            
        except Exception as e:
            logger.error(f"Error generating performance summary: {str(e)}")
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "health_score": 0
            }
    
    def _calculate_health_score(
        self, 
        db_stats: DatabaseStats, 
        performance_dist: Dict[str, int]
    ) -> int:
        """Calculate overall database health score (0-100)"""
        score = 100
        
        # Penalize based on slow queries
        total_queries = sum(performance_dist.values())
        if total_queries > 0:
            slow_ratio = (performance_dist['slow'] + performance_dist['critical']) / total_queries
            score -= min(50, slow_ratio * 100)
        
        # Penalize based on connection usage
        if db_stats.total_connections > 0:
            connection_usage = db_stats.active_connections / db_stats.total_connections
            if connection_usage > 0.8:
                score -= 20
            elif connection_usage > 0.6:
                score -= 10
        
        # Penalize low cache hit ratio
        if db_stats.cache_hit_ratio < 90:
            score -= (90 - db_stats.cache_hit_ratio) * 0.5
        
        # Penalize low index usage
        if db_stats.index_usage_ratio < 95:
            score -= (95 - db_stats.index_usage_ratio) * 0.3
        
        # Penalize lock contention
        if db_stats.lock_contention_count > 0:
            score -= min(15, db_stats.lock_contention_count * 5)
        
        return max(0, min(100, int(score)))
    
    def _generate_general_recommendations(
        self, 
        db_stats: DatabaseStats, 
        slow_queries: List[SlowQuery]
    ) -> List[str]:
        """Generate general performance recommendations"""
        recommendations = []
        
        # Cache hit ratio recommendations
        if db_stats.cache_hit_ratio < 90:
            recommendations.append(
                f"Cache hit ratio is {db_stats.cache_hit_ratio:.1f}%. "
                "Consider increasing shared_buffers or reviewing query patterns."
            )
        
        # Index usage recommendations
        if db_stats.index_usage_ratio < 95:
            recommendations.append(
                f"Index usage ratio is {db_stats.index_usage_ratio:.1f}%. "
                "Review queries for missing indexes or table scans."
            )
        
        # Connection recommendations
        if db_stats.active_connections > db_stats.total_connections * 0.8:
            recommendations.append(
                "High connection utilization detected. "
                "Consider connection pooling or increasing max_connections."
            )
        
        # Slow query recommendations
        if len(slow_queries) > 10:
            recommendations.append(
                f"Found {len(slow_queries)} slow query patterns. "
                "Prioritize optimization of queries with highest total time impact."
            )
        
        # Memory recommendations
        if db_stats.memory_usage_mb > 8192:  # 8GB
            recommendations.append(
                "High memory usage detected. Monitor for memory leaks or consider scaling."
            )
        
        # Lock contention recommendations
        if db_stats.lock_contention_count > 5:
            recommendations.append(
                "Lock contention detected. Review transaction patterns and consider optimization."
            )
        
        if not recommendations:
            recommendations.append("Database performance is within acceptable parameters.")
        
        return recommendations
    
    async def cleanup_old_metrics(self, hours: int = 24):
        """Clean up old performance metrics"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        self.query_metrics = [
            metric for metric in self.query_metrics 
            if metric.timestamp > cutoff_time
        ]
        logger.info(f"Cleaned up metrics older than {hours} hours")


# Global performance monitoring service instance
performance_monitor: Optional[PerformanceMonitoringService] = None


def get_performance_monitor() -> Optional[PerformanceMonitoringService]:
    """Get the global performance monitoring service instance"""
    return performance_monitor


def init_performance_monitor(db_session_factory) -> PerformanceMonitoringService:
    """Initialize the global performance monitoring service"""
    global performance_monitor
    
    performance_monitor = PerformanceMonitoringService(db_session_factory)
    logger.info("Performance monitoring service initialized successfully")
    
    return performance_monitor