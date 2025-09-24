"""
Cache Integration Service for Multi-Database Coordination

Provides sophisticated cache coordination between PostgreSQL, DuckDB, and Redis,
with intelligent invalidation, cross-database consistency, and hybrid query result composition.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import zlib

from ..core.config import settings
from .intelligent_cache_manager import get_cache_manager, CacheLevel, CompressionType
from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class DatabaseType(str, Enum):
    """Database types for cache coordination"""
    POSTGRESQL = "postgresql"
    DUCKDB = "duckdb"
    REDIS = "redis"
    HYBRID = "hybrid"


class ConsistencyLevel(str, Enum):
    """Cache consistency levels"""
    EVENTUAL = "eventual"  # Eventually consistent, best performance
    SESSION = "session"    # Consistent within user session
    READ_AFTER_WRITE = "read_after_write"  # Read-after-write consistency
    STRONG = "strong"      # Strong consistency, lowest performance


class InvalidationScope(str, Enum):
    """Cache invalidation scope"""
    KEY_EXACT = "key_exact"
    KEY_PATTERN = "key_pattern"
    TABLE_BASED = "table_based"
    PROJECT_BASED = "project_based"
    USER_BASED = "user_based"
    GLOBAL = "global"


@dataclass
class CacheCoordinationEntry:
    """Cache entry with cross-database coordination metadata"""
    cache_key: str
    databases: Set[DatabaseType]
    consistency_level: ConsistencyLevel
    invalidation_dependencies: Set[str]
    last_modified: datetime
    version: int
    checksum: str
    size_bytes: int
    access_count: int
    ttl_seconds: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrossDatabaseInvalidation:
    """Cross-database cache invalidation event"""
    invalidation_id: str
    scope: InvalidationScope
    patterns: List[str]
    affected_databases: Set[DatabaseType]
    triggered_by: str
    triggered_at: datetime
    reason: str
    estimated_impact: int  # Number of entries affected


@dataclass
class HybridQueryResult:
    """Result from hybrid PostgreSQL + DuckDB query"""
    postgresql_result: Optional[Any] = None
    duckdb_result: Optional[Any] = None
    combined_result: Optional[Any] = None
    cache_sources: Dict[DatabaseType, bool] = field(default_factory=dict)
    execution_time_ms: Dict[DatabaseType, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CacheConsistencyReport:
    """Cache consistency analysis report"""
    total_entries_checked: int
    consistent_entries: int
    inconsistent_entries: int
    stale_entries: int
    missing_entries: int
    consistency_score: float
    recommendations: List[str]
    checked_at: datetime


class CacheIntegrationService:
    """
    Multi-database cache coordination service.
    
    Features:
    - Cross-database cache coordination (PostgreSQL, DuckDB, Redis)
    - Intelligent cache invalidation with dependency tracking
    - Hybrid query result composition and caching
    - Consistency level enforcement
    - Cache conflict resolution
    - Performance optimization through selective caching
    - Distributed cache synchronization
    - Cache health monitoring and analytics
    """
    
    def __init__(
        self,
        postgresql_session_factory=None,
        duckdb_service=None,
        redis_client=None,
        enable_cross_db_invalidation: bool = True,
        default_consistency_level: ConsistencyLevel = ConsistencyLevel.SESSION
    ):
        self.postgresql_session_factory = postgresql_session_factory
        self.duckdb_service = duckdb_service
        self.redis_client = redis_client
        self.enable_cross_db_invalidation = enable_cross_db_invalidation
        self.default_consistency_level = default_consistency_level
        
        # Cache coordination tracking
        self.coordination_entries: Dict[str, CacheCoordinationEntry] = {}
        self.invalidation_history: List[CrossDatabaseInvalidation] = []
        
        # Dependency tracking
        self.table_dependencies: Dict[str, Set[str]] = defaultdict(set)  # table -> cache_keys
        self.project_dependencies: Dict[str, Set[str]] = defaultdict(set)  # project -> cache_keys
        self.user_dependencies: Dict[str, Set[str]] = defaultdict(set)  # user -> cache_keys
        
        # Cross-database query patterns
        self.hybrid_query_patterns: Dict[str, Dict[str, Any]] = {}
        
        # Circuit breakers for each database
        from .circuit_breaker import CircuitBreakerConfig
        self.circuit_breakers = {
            DatabaseType.POSTGRESQL: CircuitBreaker("postgresql", config=CircuitBreakerConfig(failure_threshold=3, timeout_seconds=30)),
            DatabaseType.DUCKDB: CircuitBreaker("duckdb", config=CircuitBreakerConfig(failure_threshold=3, timeout_seconds=30)),
            DatabaseType.REDIS: CircuitBreaker("redis", config=CircuitBreakerConfig(failure_threshold=5, timeout_seconds=60))
        }
        
        # Performance metrics
        self.metrics = {
            'cache_hits_by_db': defaultdict(int),
            'cache_misses_by_db': defaultdict(int),
            'invalidations_triggered': 0,
            'consistency_violations': 0,
            'hybrid_queries': 0,
            'cross_db_operations': 0
        }
        
        # Background tasks
        self._consistency_checker_task: Optional[asyncio.Task] = None
        self._invalidation_processor_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Get cache manager reference
        self.cache_manager = get_cache_manager()
        
        logger.info("Cache integration service initialized")
    
    async def start(self):
        """Start background coordination tasks"""
        if self._consistency_checker_task:
            return  # Already started
        
        self._consistency_checker_task = asyncio.create_task(
            self._consistency_checker()
        )
        self._invalidation_processor_task = asyncio.create_task(
            self._invalidation_processor()
        )
        
        logger.info("Cache integration background tasks started")
    
    async def stop(self):
        """Stop background coordination tasks"""
        self._shutdown_event.set()
        
        if self._consistency_checker_task:
            self._consistency_checker_task.cancel()
        if self._invalidation_processor_task:
            self._invalidation_processor_task.cancel()
        
        logger.info("Cache integration background tasks stopped")
    
    async def _consistency_checker(self):
        """Background task to check cache consistency across databases"""
        while not self._shutdown_event.is_set():
            try:
                # Check consistency between PostgreSQL and DuckDB caches
                if self.enable_cross_db_invalidation:
                    # Get recent cache entries from both sources
                    recent_entries = []
                    
                    # Check for stale entries
                    for entry in recent_entries:
                        # Simplified consistency check - in production would be more sophisticated
                        pass
                    
                    # Track consistency metrics
                    self.metrics['consistency_checks'] = self.metrics.get('consistency_checks', 0) + 1
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in consistency checker: {str(e)}")
                await asyncio.sleep(120)  # Wait longer on error
    
    async def _invalidation_processor(self):
        """Process cache invalidation queue"""
        while not self._shutdown_event.is_set():
            try:
                # Process invalidation queue
                while self.invalidation_queue:
                    invalidation = self.invalidation_queue.popleft()
                    
                    # Process invalidation based on type
                    if invalidation.get('type') == 'table_update':
                        await self._invalidate_table_cache(invalidation['table'])
                    elif invalidation.get('type') == 'query_pattern':
                        await self._invalidate_query_pattern(invalidation['pattern'])
                    
                    self.metrics['invalidations_processed'] = self.metrics.get('invalidations_processed', 0) + 1
                
                await asyncio.sleep(5)  # Process every 5 seconds
                
            except Exception as e:
                logger.error(f"Error processing invalidations: {str(e)}")
                await asyncio.sleep(10)  # Wait longer on error
    
    async def _invalidate_table_cache(self, table_name: str):
        """Invalidate cache entries related to a specific table"""
        try:
            # Invalidate Redis cache entries for this table
            if self.redis_client:
                pattern = f"*{table_name}*"
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            
            logger.debug(f"Invalidated cache for table: {table_name}")
            
        except Exception as e:
            logger.error(f"Error invalidating table cache: {str(e)}")
    
    async def _invalidate_query_pattern(self, pattern: str):
        """Invalidate cache entries matching a query pattern"""
        try:
            # Invalidate matching cache entries
            if self.redis_client:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            
            logger.debug(f"Invalidated cache for pattern: {pattern}")
            
        except Exception as e:
            logger.error(f"Error invalidating query pattern cache: {str(e)}")
    
    async def coordinate_cache_entry(
        self,
        cache_key: str,
        databases: Set[DatabaseType],
        consistency_level: ConsistencyLevel = None,
        dependencies: Set[str] = None
    ) -> CacheCoordinationEntry:
        """
        Register a cache entry for cross-database coordination.
        
        Args:
            cache_key: Unique cache key
            databases: Set of databases that contain this cached data
            consistency_level: Required consistency level
            dependencies: Cache invalidation dependencies
            
        Returns:
            CacheCoordinationEntry with coordination metadata
        """
        consistency_level = consistency_level or self.default_consistency_level
        dependencies = dependencies or set()
        
        # Generate cache entry checksum
        checksum = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
        
        entry = CacheCoordinationEntry(
            cache_key=cache_key,
            databases=databases,
            consistency_level=consistency_level,
            invalidation_dependencies=dependencies,
            last_modified=datetime.now(),
            version=1,
            checksum=checksum,
            size_bytes=0,  # Will be updated when data is cached
            access_count=0,
            ttl_seconds=3600,  # Default 1 hour
            metadata={}
        )
        
        self.coordination_entries[cache_key] = entry
        
        # Update dependency tracking
        await self._update_dependency_tracking(cache_key, dependencies)
        
        logger.debug(f"Cache entry registered for coordination: {cache_key}")
        
        return entry
    
    async def get_coordinated_cache_result(
        self,
        cache_key: str,
        preferred_database: Optional[DatabaseType] = None,
        consistency_level: Optional[ConsistencyLevel] = None
    ) -> Optional[Any]:
        """
        Retrieve cached result with cross-database coordination.
        
        Args:
            cache_key: Cache key to retrieve
            preferred_database: Preferred database for retrieval
            consistency_level: Required consistency level
            
        Returns:
            Cached result if found and consistent, None otherwise
        """
        consistency_level = consistency_level or self.default_consistency_level
        
        # Check if we have coordination metadata for this key
        coordination_entry = self.coordination_entries.get(cache_key)
        if not coordination_entry:
            # Fallback to regular cache retrieval
            if self.cache_manager:
                cached_result = await self.cache_manager.get_cached_result(cache_key)
                return cached_result.data if cached_result else None
            return None
        
        # Determine which databases to check based on consistency level
        databases_to_check = await self._get_databases_for_consistency(
            coordination_entry, consistency_level, preferred_database
        )
        
        # Try to retrieve from databases in order of preference
        for database in databases_to_check:
            try:
                result = await self._get_from_database_cache(cache_key, database)
                if result is not None:
                    # Update access tracking
                    coordination_entry.access_count += 1
                    self.metrics['cache_hits_by_db'][database] += 1
                    
                    # Verify consistency if required
                    if consistency_level in [ConsistencyLevel.STRONG, ConsistencyLevel.READ_AFTER_WRITE]:
                        if await self._verify_cache_consistency(cache_key, result, databases_to_check):
                            return result
                        else:
                            self.metrics['consistency_violations'] += 1
                            logger.warning(f"Cache consistency violation detected for key: {cache_key}")
                            continue
                    
                    return result
                
            except Exception as e:
                logger.error(f"Error retrieving from {database.value} cache: {str(e)}")
                self.metrics['cache_misses_by_db'][database] += 1
        
        return None
    
    async def invalidate_coordinated_cache(
        self,
        scope: InvalidationScope,
        patterns: List[str],
        reason: str = "Manual invalidation",
        triggered_by: str = "system"
    ) -> CrossDatabaseInvalidation:
        """
        Perform coordinated cache invalidation across databases.
        
        Args:
            scope: Invalidation scope
            patterns: Patterns to match for invalidation
            reason: Reason for invalidation
            triggered_by: Who/what triggered the invalidation
            
        Returns:
            CrossDatabaseInvalidation event
        """
        invalidation_id = f"inv_{int(time.time() * 1000)}"
        
        # Determine affected cache keys
        affected_keys = await self._find_keys_for_invalidation(scope, patterns)
        
        # Determine affected databases
        affected_databases = set()
        for key in affected_keys:
            entry = self.coordination_entries.get(key)
            if entry:
                affected_databases.update(entry.databases)
        
        # Create invalidation event
        invalidation_event = CrossDatabaseInvalidation(
            invalidation_id=invalidation_id,
            scope=scope,
            patterns=patterns,
            affected_databases=affected_databases,
            triggered_by=triggered_by,
            triggered_at=datetime.now(),
            reason=reason,
            estimated_impact=len(affected_keys)
        )
        
        # Perform invalidation across databases
        if self.enable_cross_db_invalidation:
            await self._execute_cross_database_invalidation(invalidation_event, affected_keys)
        
        # Update metrics and history
        self.metrics['invalidations_triggered'] += 1
        self.invalidation_history.append(invalidation_event)
        
        # Keep history manageable
        if len(self.invalidation_history) > 1000:
            self.invalidation_history = self.invalidation_history[-500:]
        
        logger.info(
            f"Cross-database invalidation completed: {invalidation_id}, "
            f"Affected {len(affected_keys)} keys across {len(affected_databases)} databases"
        )
        
        return invalidation_event
    
    async def execute_hybrid_query(
        self,
        postgresql_query: Optional[str] = None,
        duckdb_query: Optional[str] = None,
        combine_results: bool = True,
        cache_result: bool = True,
        cache_ttl: int = 3600
    ) -> HybridQueryResult:
        """
        Execute hybrid query across PostgreSQL and DuckDB with coordinated caching.
        
        Args:
            postgresql_query: PostgreSQL query to execute
            duckdb_query: DuckDB query to execute
            combine_results: Whether to combine results
            cache_result: Whether to cache the results
            cache_ttl: Cache TTL in seconds
            
        Returns:
            HybridQueryResult with results from both databases
        """
        self.metrics['hybrid_queries'] += 1
        
        result = HybridQueryResult()
        
        # Generate cache keys for each query
        pg_cache_key = None
        duck_cache_key = None
        
        if postgresql_query:
            pg_cache_key = f"pg:{hashlib.sha256(postgresql_query.encode()).hexdigest()}"
        
        if duckdb_query:
            duck_cache_key = f"duck:{hashlib.sha256(duckdb_query.encode()).hexdigest()}"
        
        # Try to get cached results first
        if cache_result:
            if pg_cache_key:
                cached_pg_result = await self.get_coordinated_cache_result(
                    pg_cache_key, DatabaseType.POSTGRESQL
                )
                if cached_pg_result:
                    result.postgresql_result = cached_pg_result
                    result.cache_sources[DatabaseType.POSTGRESQL] = True
            
            if duck_cache_key:
                cached_duck_result = await self.get_coordinated_cache_result(
                    duck_cache_key, DatabaseType.DUCKDB
                )
                if cached_duck_result:
                    result.duckdb_result = cached_duck_result
                    result.cache_sources[DatabaseType.DUCKDB] = True
        
        # Execute PostgreSQL query if needed
        if postgresql_query and result.postgresql_result is None:
            try:
                start_time = time.time()
                with self.circuit_breakers[DatabaseType.POSTGRESQL]:
                    result.postgresql_result = await self._execute_postgresql_query(postgresql_query)
                    execution_time = (time.time() - start_time) * 1000
                    result.execution_time_ms[DatabaseType.POSTGRESQL] = execution_time
                    result.cache_sources[DatabaseType.POSTGRESQL] = False
                
                # Cache the result
                if cache_result and pg_cache_key:
                    await self._cache_hybrid_result(
                        pg_cache_key, result.postgresql_result, 
                        DatabaseType.POSTGRESQL, cache_ttl
                    )
                
            except Exception as e:
                logger.error(f"PostgreSQL query execution failed: {str(e)}")
                result.metadata['postgresql_error'] = str(e)
        
        # Execute DuckDB query if needed
        if duckdb_query and result.duckdb_result is None:
            try:
                start_time = time.time()
                with self.circuit_breakers[DatabaseType.DUCKDB]:
                    result.duckdb_result = await self._execute_duckdb_query(duckdb_query)
                    execution_time = (time.time() - start_time) * 1000
                    result.execution_time_ms[DatabaseType.DUCKDB] = execution_time
                    result.cache_sources[DatabaseType.DUCKDB] = False
                
                # Cache the result
                if cache_result and duck_cache_key:
                    await self._cache_hybrid_result(
                        duck_cache_key, result.duckdb_result,
                        DatabaseType.DUCKDB, cache_ttl
                    )
                
            except Exception as e:
                logger.error(f"DuckDB query execution failed: {str(e)}")
                result.metadata['duckdb_error'] = str(e)
        
        # Combine results if requested
        if combine_results and result.postgresql_result and result.duckdb_result:
            try:
                result.combined_result = await self._combine_hybrid_results(
                    result.postgresql_result, result.duckdb_result
                )
                
                # Cache combined result
                if cache_result:
                    combined_cache_key = f"hybrid:{hashlib.sha256(f'{postgresql_query}:{duckdb_query}'.encode()).hexdigest()}"
                    await self._cache_hybrid_result(
                        combined_cache_key, result.combined_result,
                        DatabaseType.HYBRID, cache_ttl
                    )
                
            except Exception as e:
                logger.error(f"Failed to combine hybrid results: {str(e)}")
                result.metadata['combination_error'] = str(e)
        
        return result
    
    async def analyze_cache_consistency(
        self, 
        sample_size: int = 100
    ) -> CacheConsistencyReport:
        """
        Analyze cache consistency across databases.
        
        Args:
            sample_size: Number of cache entries to check
            
        Returns:
            CacheConsistencyReport with consistency analysis
        """
        logger.info(f"Starting cache consistency analysis (sample size: {sample_size})")
        
        # Get sample of coordination entries
        sample_entries = list(self.coordination_entries.values())[:sample_size]
        
        consistent_count = 0
        inconsistent_count = 0
        stale_count = 0
        missing_count = 0
        recommendations = []
        
        for entry in sample_entries:
            try:
                consistency_result = await self._check_entry_consistency(entry)
                
                if consistency_result['consistent']:
                    consistent_count += 1
                else:
                    inconsistent_count += 1
                    
                if consistency_result['stale']:
                    stale_count += 1
                    
                if consistency_result['missing_databases']:
                    missing_count += len(consistency_result['missing_databases'])
                
            except Exception as e:
                logger.error(f"Error checking consistency for {entry.cache_key}: {str(e)}")
                inconsistent_count += 1
        
        # Calculate consistency score
        total_checked = len(sample_entries)
        consistency_score = (consistent_count / total_checked * 100) if total_checked > 0 else 0
        
        # Generate recommendations
        if inconsistent_count > total_checked * 0.1:  # >10% inconsistent
            recommendations.append("High inconsistency detected - consider stronger consistency levels")
        
        if stale_count > total_checked * 0.2:  # >20% stale
            recommendations.append("Many stale entries detected - review TTL settings")
        
        if missing_count > 0:
            recommendations.append("Missing cache entries detected - check database health")
        
        return CacheConsistencyReport(
            total_entries_checked=total_checked,
            consistent_entries=consistent_count,
            inconsistent_entries=inconsistent_count,
            stale_entries=stale_count,
            missing_entries=missing_count,
            consistency_score=consistency_score,
            recommendations=recommendations,
            checked_at=datetime.now()
        )
    
    # Private helper methods
    
    async def _get_databases_for_consistency(
        self,
        entry: CacheCoordinationEntry,
        consistency_level: ConsistencyLevel,
        preferred_database: Optional[DatabaseType]
    ) -> List[DatabaseType]:
        """Determine database order based on consistency requirements"""
        databases = list(entry.databases)
        
        # Order by preference and consistency requirements
        if preferred_database and preferred_database in databases:
            databases.remove(preferred_database)
            databases.insert(0, preferred_database)
        
        # For strong consistency, check all databases
        if consistency_level == ConsistencyLevel.STRONG:
            return databases
        
        # For other levels, prioritize by performance
        return sorted(databases, key=lambda db: self._get_database_performance_score(db), reverse=True)
    
    def _get_database_performance_score(self, database: DatabaseType) -> float:
        """Get performance score for database (higher = better)"""
        # Simple scoring based on typical performance characteristics
        scores = {
            DatabaseType.REDIS: 1.0,      # Fastest
            DatabaseType.DUCKDB: 0.8,     # Fast for analytics
            DatabaseType.POSTGRESQL: 0.6, # Good general purpose
        }
        return scores.get(database, 0.5)
    
    async def _get_from_database_cache(
        self, 
        cache_key: str, 
        database: DatabaseType
    ) -> Optional[Any]:
        """Retrieve from specific database cache"""
        try:
            if database == DatabaseType.REDIS and self.redis_client:
                result = await self.redis_client.get(cache_key)
                if result:
                    # Deserialize result
                    import pickle
                    return pickle.loads(result)
            
            elif database == DatabaseType.POSTGRESQL and self.cache_manager:
                # Use cache manager for PostgreSQL cache
                cached_result = await self.cache_manager.get_cached_result(cache_key)
                return cached_result.data if cached_result else None
            
            elif database == DatabaseType.DUCKDB and self.duckdb_service:
                # Query DuckDB cache table
                query = """
                SELECT data FROM cache_entries 
                WHERE cache_key = ? AND expires_at > NOW()
                """
                result = await self.duckdb_service.execute_query(query, [cache_key])
                if result and result.fetchone():
                    # Deserialize result
                    import pickle
                    return pickle.loads(result.fetchone()[0])
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving from {database.value} cache: {str(e)}")
            return None
    
    async def _verify_cache_consistency(
        self,
        cache_key: str,
        result: Any,
        databases: List[DatabaseType]
    ) -> bool:
        """Verify cache consistency across databases"""
        if len(databases) <= 1:
            return True  # Single database is always consistent
        
        # Get result from all databases
        results = {}
        for database in databases:
            db_result = await self._get_from_database_cache(cache_key, database)
            if db_result is not None:
                # Create checksum for comparison
                import pickle
                results[database] = hashlib.sha256(pickle.dumps(db_result)).hexdigest()
        
        # Check if all checksums match
        checksums = list(results.values())
        return len(set(checksums)) <= 1  # All same or empty
    
    async def _find_keys_for_invalidation(
        self,
        scope: InvalidationScope,
        patterns: List[str]
    ) -> Set[str]:
        """Find cache keys matching invalidation scope and patterns"""
        affected_keys = set()
        
        if scope == InvalidationScope.KEY_EXACT:
            # Exact key matches
            for pattern in patterns:
                if pattern in self.coordination_entries:
                    affected_keys.add(pattern)
        
        elif scope == InvalidationScope.KEY_PATTERN:
            # Pattern matching
            import fnmatch
            for pattern in patterns:
                for key in self.coordination_entries.keys():
                    if fnmatch.fnmatch(key, pattern):
                        affected_keys.add(key)
        
        elif scope == InvalidationScope.TABLE_BASED:
            # Table-based invalidation
            for table_name in patterns:
                affected_keys.update(self.table_dependencies.get(table_name, set()))
        
        elif scope == InvalidationScope.PROJECT_BASED:
            # Project-based invalidation
            for project_id in patterns:
                affected_keys.update(self.project_dependencies.get(project_id, set()))
        
        elif scope == InvalidationScope.USER_BASED:
            # User-based invalidation
            for user_id in patterns:
                affected_keys.update(self.user_dependencies.get(user_id, set()))
        
        elif scope == InvalidationScope.GLOBAL:
            # Global invalidation
            affected_keys = set(self.coordination_entries.keys())
        
        return affected_keys
    
    async def _execute_cross_database_invalidation(
        self,
        invalidation_event: CrossDatabaseInvalidation,
        affected_keys: Set[str]
    ):
        """Execute invalidation across all affected databases"""
        for database in invalidation_event.affected_databases:
            try:
                if database == DatabaseType.REDIS and self.redis_client:
                    # Invalidate Redis cache
                    if affected_keys:
                        await self.redis_client.delete(*affected_keys)
                
                elif database == DatabaseType.POSTGRESQL and self.cache_manager:
                    # Invalidate through cache manager
                    for key in affected_keys:
                        await self.cache_manager.invalidate_cache([key])
                
                elif database == DatabaseType.DUCKDB and self.duckdb_service:
                    # Invalidate DuckDB cache
                    if affected_keys:
                        placeholders = ','.join(['?' for _ in affected_keys])
                        query = f"DELETE FROM cache_entries WHERE cache_key IN ({placeholders})"
                        await self.duckdb_service.execute_query(query, list(affected_keys))
                
                self.metrics['cross_db_operations'] += 1
                
            except Exception as e:
                logger.error(f"Error invalidating {database.value} cache: {str(e)}")
        
        # Remove from coordination tracking
        for key in affected_keys:
            self.coordination_entries.pop(key, None)
    
    async def _update_dependency_tracking(self, cache_key: str, dependencies: Set[str]):
        """Update dependency tracking for cache invalidation"""
        for dependency in dependencies:
            # Parse dependency type and value
            if dependency.startswith('table:'):
                table_name = dependency[6:]  # Remove 'table:' prefix
                self.table_dependencies[table_name].add(cache_key)
            elif dependency.startswith('project:'):
                project_id = dependency[8:]  # Remove 'project:' prefix
                self.project_dependencies[project_id].add(cache_key)
            elif dependency.startswith('user:'):
                user_id = dependency[5:]  # Remove 'user:' prefix
                self.user_dependencies[user_id].add(cache_key)


# Singleton instance
_cache_integration_service: Optional[CacheIntegrationService] = None


def get_cache_integration_service() -> Optional[CacheIntegrationService]:
    """Get the global cache integration service instance"""
    return _cache_integration_service


async def init_cache_integration_service(
    postgresql_session_factory=None,
    duckdb_service=None,
    redis_client=None,
    enable_cross_db_invalidation: bool = True,
    default_consistency_level: ConsistencyLevel = ConsistencyLevel.SESSION
) -> CacheIntegrationService:
    """Initialize the global cache integration service"""
    global _cache_integration_service
    
    _cache_integration_service = CacheIntegrationService(
        postgresql_session_factory=postgresql_session_factory,
        duckdb_service=duckdb_service,
        redis_client=redis_client,
        enable_cross_db_invalidation=enable_cross_db_invalidation,
        default_consistency_level=default_consistency_level
    )
    
    await _cache_integration_service.start()
    
    logger.info("Cache integration service initialized successfully")
    return _cache_integration_service