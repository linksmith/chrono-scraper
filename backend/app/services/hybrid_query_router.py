"""
HybridQueryRouter - Intelligent Query Routing System
==================================================

Routes queries between PostgreSQL (OLTP) and DuckDB (OLAP) based on query
characteristics, performance optimization, and system load balancing.

Features:
- Intelligent query classification and routing
- Performance-based routing decisions  
- Circuit breaker protection and failover
- Multi-level caching integration
- Comprehensive monitoring and metrics
- Connection pooling for both databases
- Query optimization and rewriting
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..core.config import settings
from ..core.database import AsyncSessionLocal
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .duckdb_service import DuckDBService, get_duckdb_service

logger = logging.getLogger(__name__)


class DatabaseTarget(str, Enum):
    """Target database for query execution"""
    POSTGRESQL = "postgresql"
    DUCKDB = "duckdb"
    HYBRID = "hybrid"  # Requires both databases
    AUTO = "auto"  # Let router decide


class QueryType(str, Enum):
    """Classification of query types"""
    # OLTP Operations (PostgreSQL)
    USER_AUTH = "user_auth"
    USER_MANAGEMENT = "user_management"
    PROJECT_CRUD = "project_crud"
    PAGE_MANAGEMENT = "page_management"
    REAL_TIME_OPERATIONS = "real_time_operations"
    TRANSACTIONAL = "transactional"
    
    # OLAP Operations (DuckDB)
    ANALYTICS = "analytics"
    AGGREGATION = "aggregation"
    TIME_SERIES = "time_series"
    REPORTING = "reporting"
    SEARCH_COMPLEX = "search_complex"
    BULK_READ = "bulk_read"
    
    # Hybrid Operations (Both)
    CROSS_PROJECT_ANALYTICS = "cross_project_analytics"
    USER_ACTIVITY_ANALYSIS = "user_activity_analysis"
    PERFORMANCE_MONITORING = "performance_monitoring"
    
    # System Operations
    HEALTH_CHECK = "health_check"
    ADMIN_OPERATIONS = "admin_operations"
    MAINTENANCE = "maintenance"


class QueryPriority(str, Enum):
    """Query execution priority levels"""
    CRITICAL = "critical"      # Authentication, critical operations
    HIGH = "high"             # Real-time user operations
    NORMAL = "normal"         # Standard analytics, reports
    LOW = "low"               # Background processing, maintenance


@dataclass
class QueryMetadata:
    """Metadata about a query for routing decisions"""
    query_type: QueryType
    database_target: DatabaseTarget
    priority: QueryPriority
    estimated_rows: Optional[int] = None
    estimated_duration: Optional[float] = None
    memory_estimate: Optional[int] = None
    tables_involved: Set[str] = field(default_factory=set)
    operations: Set[str] = field(default_factory=set)
    has_joins: bool = False
    has_aggregations: bool = False
    has_window_functions: bool = False
    is_write_operation: bool = False
    cache_key: Optional[str] = None
    routing_reason: str = ""


@dataclass
class QueryResult:
    """Result of query execution with metadata"""
    data: Any
    execution_time: float
    database_used: DatabaseTarget
    rows_affected: Optional[int] = None
    memory_used: Optional[float] = None
    cache_hit: bool = False
    routing_metadata: Optional[QueryMetadata] = None
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "data": self.data,
            "execution_time": self.execution_time,
            "database_used": self.database_used.value,
            "rows_affected": self.rows_affected,
            "memory_used": self.memory_used,
            "cache_hit": self.cache_hit,
            "warnings": self.warnings,
            "routing_metadata": {
                "query_type": self.routing_metadata.query_type.value if self.routing_metadata else None,
                "routing_reason": self.routing_metadata.routing_reason if self.routing_metadata else None
            }
        }


@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring and optimization"""
    total_queries: int = 0
    postgresql_queries: int = 0
    duckdb_queries: int = 0
    hybrid_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_response_time: float = 0.0
    successful_queries: int = 0
    failed_queries: int = 0
    
    # Query type distribution
    query_type_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Performance tracking
    response_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    error_rates: Dict[str, float] = field(default_factory=dict)
    
    # Resource usage
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    
    def success_rate(self) -> float:
        """Calculate overall success rate"""
        if self.total_queries == 0:
            return 100.0
        return (self.successful_queries / self.total_queries) * 100.0
    
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total_cache_operations = self.cache_hits + self.cache_misses
        if total_cache_operations == 0:
            return 0.0
        return (self.cache_hits / total_cache_operations) * 100.0


class QueryCache:
    """Multi-level caching system for query results"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client: Optional[aioredis.Redis] = None
        self.local_cache: Dict[str, Tuple[Any, datetime]] = {}
        self.cache_stats = {"hits": 0, "misses": 0}
        
    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = aioredis.from_url(self.redis_url)
            await self.redis_client.ping()
            logger.info("Redis cache initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            self.redis_client = None
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached result"""
        try:
            # Try local cache first (fastest)
            if key in self.local_cache:
                data, timestamp = self.local_cache[key]
                # Check if still valid (5 minutes for local cache)
                if datetime.now() - timestamp < timedelta(minutes=5):
                    self.cache_stats["hits"] += 1
                    return data
                else:
                    del self.local_cache[key]
            
            # Try Redis cache
            if self.redis_client:
                cached = await self.redis_client.get(f"query_cache:{key}")
                if cached:
                    self.cache_stats["hits"] += 1
                    data = json.loads(cached)
                    # Store in local cache for faster future access
                    self.local_cache[key] = (data, datetime.now())
                    return data
            
            self.cache_stats["misses"] += 1
            return None
            
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.cache_stats["misses"] += 1
            return None
    
    async def set(self, key: str, value: Any, ttl: int = 1800) -> None:
        """Set cached result with TTL"""
        try:
            # Store in local cache
            self.local_cache[key] = (value, datetime.now())
            
            # Store in Redis with TTL
            if self.redis_client:
                await self.redis_client.setex(
                    f"query_cache:{key}", 
                    ttl, 
                    json.dumps(value, default=str)
                )
            
            # Limit local cache size
            if len(self.local_cache) > 1000:
                # Remove oldest entries
                sorted_items = sorted(
                    self.local_cache.items(), 
                    key=lambda x: x[1][1]
                )
                for key_to_remove, _ in sorted_items[:100]:
                    del self.local_cache[key_to_remove]
                    
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    async def invalidate_pattern(self, pattern: str) -> None:
        """Invalidate cache entries matching pattern"""
        try:
            # Clear matching local cache entries
            keys_to_remove = [k for k in self.local_cache.keys() if re.search(pattern, k)]
            for key in keys_to_remove:
                del self.local_cache[key]
            
            # Clear Redis cache entries
            if self.redis_client:
                keys = await self.redis_client.keys(f"query_cache:{pattern}")
                if keys:
                    await self.redis_client.delete(*keys)
                    
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total * 100) if total > 0 else 0
        
        return {
            "hits": self.cache_stats["hits"],
            "misses": self.cache_stats["misses"],
            "hit_rate": round(hit_rate, 2),
            "local_cache_size": len(self.local_cache),
            "redis_connected": self.redis_client is not None
        }


class HybridQueryRouter:
    """
    Intelligent query router for PostgreSQL and DuckDB
    
    Features:
    - Query classification and routing
    - Performance optimization
    - Circuit breaker protection
    - Multi-level caching
    - Comprehensive monitoring
    """
    
    _instance: Optional['HybridQueryRouter'] = None
    
    def __new__(cls) -> 'HybridQueryRouter':
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self._initialized = True
        
        # Core services
        self.duckdb_service: Optional[DuckDBService] = None
        self.cache = QueryCache(settings.REDIS_URL)
        
        # Circuit breakers for each database
        self.postgresql_breaker = CircuitBreaker(
            "postgresql",
            CircuitBreakerConfig(
                failure_threshold=settings.POSTGRESQL_CIRCUIT_BREAKER_THRESHOLD,
                timeout_seconds=settings.POSTGRESQL_CIRCUIT_BREAKER_TIMEOUT
            )
        )
        
        self.duckdb_breaker = CircuitBreaker(
            "duckdb", 
            CircuitBreakerConfig(
                failure_threshold=settings.DUCKDB_CIRCUIT_BREAKER_THRESHOLD,
                timeout_seconds=settings.DUCKDB_CIRCUIT_BREAKER_TIMEOUT
            )
        )
        
        # Performance metrics
        self.metrics = PerformanceMetrics()
        
        # Query patterns for classification
        self._initialize_query_patterns()
        
        # Routing rules cache
        self._routing_rules_cache: Dict[str, QueryMetadata] = {}
        
        logger.info("HybridQueryRouter initialized")
    
    def _initialize_query_patterns(self):
        """Initialize regex patterns for query classification"""
        self.query_patterns = {
            # OLTP patterns (PostgreSQL)
            QueryType.USER_AUTH: [
                r"SELECT.*FROM\s+users\s+WHERE.*email",
                r"SELECT.*FROM\s+users\s+WHERE.*password",
                r"UPDATE\s+users\s+SET.*last_login"
            ],
            QueryType.PROJECT_CRUD: [
                r"INSERT\s+INTO\s+projects",
                r"UPDATE\s+projects\s+SET",
                r"DELETE\s+FROM\s+projects",
                r"SELECT.*FROM\s+projects\s+WHERE.*id\s*="
            ],
            QueryType.PAGE_MANAGEMENT: [
                r"INSERT\s+INTO\s+pages_v2",
                r"UPDATE\s+pages_v2\s+SET",
                r"SELECT.*FROM\s+pages_v2\s+WHERE.*id\s*="
            ],
            QueryType.REAL_TIME_OPERATIONS: [
                r"UPDATE.*SET\s+status\s*=",
                r"SELECT.*FOR\s+UPDATE",
                r"INSERT.*RETURNING"
            ],
            
            # OLAP patterns (DuckDB)
            QueryType.ANALYTICS: [
                r"SELECT.*COUNT\(.*\).*GROUP\s+BY",
                r"SELECT.*AVG\(.*\).*FROM",
                r"SELECT.*SUM\(.*\).*GROUP\s+BY"
            ],
            QueryType.TIME_SERIES: [
                r"SELECT.*date_trunc\(",
                r"SELECT.*EXTRACT\(.*FROM",
                r"SELECT.*WHERE.*timestamp.*BETWEEN"
            ],
            QueryType.AGGREGATION: [
                r"GROUP\s+BY.*HAVING",
                r"SELECT.*DISTINCT.*COUNT",
                r"WITH.*AS.*SELECT.*COUNT"
            ],
            
            # Hybrid patterns
            QueryType.CROSS_PROJECT_ANALYTICS: [
                r"SELECT.*users.*projects.*COUNT",
                r"SELECT.*FROM\s+users.*JOIN.*projects"
            ]
        }
    
    async def initialize(self) -> None:
        """Initialize the hybrid query router"""
        try:
            # Initialize DuckDB service
            self.duckdb_service = await get_duckdb_service()
            
            # Initialize cache
            await self.cache.initialize()
            
            logger.info("HybridQueryRouter initialization completed")
            
        except Exception as e:
            logger.error(f"Failed to initialize HybridQueryRouter: {e}")
            raise
    
    async def route_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        query_type: Optional[QueryType] = None,
        priority: QueryPriority = QueryPriority.NORMAL,
        use_cache: bool = True
    ) -> QueryResult:
        """
        Route and execute a query intelligently
        
        Args:
            query: SQL query string
            params: Query parameters
            query_type: Explicit query type (optional)
            priority: Query priority level
            use_cache: Whether to use caching
            
        Returns:
            QueryResult with execution metadata
        """
        start_time = time.time()
        
        try:
            # Classify query if not explicitly provided
            metadata = await self.classify_query(query, params, query_type)
            metadata.priority = priority
            
            # Check cache first
            if use_cache:
                cache_key = self._generate_cache_key(query, params)
                cached_result = await self.cache.get(cache_key)
                if cached_result:
                    result = QueryResult(
                        data=cached_result,
                        execution_time=time.time() - start_time,
                        database_used=DatabaseTarget.AUTO,  # Cache hit
                        cache_hit=True,
                        routing_metadata=metadata
                    )
                    self.metrics.cache_hits += 1
                    return result
                else:
                    self.metrics.cache_misses += 1
            
            # Route to appropriate database
            if metadata.database_target == DatabaseTarget.POSTGRESQL:
                result = await self._execute_postgresql_query(query, params, metadata)
            elif metadata.database_target == DatabaseTarget.DUCKDB:
                result = await self._execute_duckdb_query(query, params, metadata)
            elif metadata.database_target == DatabaseTarget.HYBRID:
                result = await self._execute_hybrid_query(query, params, metadata)
            else:
                # Auto-route based on performance characteristics
                result = await self._auto_route_query(query, params, metadata)
            
            # Cache result if appropriate
            if use_cache and self._should_cache_result(metadata, result):
                cache_key = self._generate_cache_key(query, params)
                ttl = self._get_cache_ttl(metadata)
                await self.cache.set(cache_key, result.data, ttl)
            
            # Update metrics
            self._update_metrics(result, metadata)
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self.metrics.failed_queries += 1
            
            logger.error(f"Query routing failed after {execution_time:.3f}s: {e}")
            raise
    
    async def classify_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        explicit_type: Optional[QueryType] = None
    ) -> QueryMetadata:
        """
        Classify a query to determine optimal routing
        
        Args:
            query: SQL query string
            params: Query parameters
            explicit_type: Explicitly provided query type
            
        Returns:
            QueryMetadata with routing information
        """
        if explicit_type:
            metadata = QueryMetadata(
                query_type=explicit_type,
                database_target=self._get_default_target_for_type(explicit_type),
                priority=QueryPriority.NORMAL,
                routing_reason=f"Explicit type: {explicit_type.value}"
            )
        else:
            metadata = await self._analyze_query_automatically(query)
        
        # Additional analysis
        metadata.tables_involved = self._extract_table_names(query)
        metadata.operations = self._extract_operations(query)
        metadata.has_joins = "JOIN" in query.upper()
        metadata.has_aggregations = any(
            op in query.upper() 
            for op in ["COUNT(", "SUM(", "AVG(", "MIN(", "MAX(", "GROUP BY"]
        )
        metadata.has_window_functions = any(
            fn in query.upper()
            for fn in ["ROW_NUMBER(", "RANK(", "DENSE_RANK(", "LAG(", "LEAD("]
        )
        metadata.is_write_operation = any(
            op in query.upper().strip()[:10]
            for op in ["INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"]
        )
        
        # Estimate query characteristics
        metadata.estimated_rows = self._estimate_result_size(query, metadata)
        metadata.estimated_duration = self._estimate_duration(query, metadata)
        metadata.memory_estimate = self._estimate_memory_usage(query, metadata)
        
        return metadata
    
    async def _analyze_query_automatically(self, query: str) -> QueryMetadata:
        """Automatically analyze and classify a query"""
        query_upper = query.upper()
        
        # Check cached classification first
        query_hash = hashlib.md5(query.encode()).hexdigest()
        if query_hash in self._routing_rules_cache:
            cached_metadata = self._routing_rules_cache[query_hash]
            return QueryMetadata(
                query_type=cached_metadata.query_type,
                database_target=cached_metadata.database_target,
                priority=cached_metadata.priority,
                routing_reason=f"Cached classification: {cached_metadata.routing_reason}"
            )
        
        # Pattern-based classification
        for query_type, patterns in self.query_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_upper):
                    target = self._get_default_target_for_type(query_type)
                    metadata = QueryMetadata(
                        query_type=query_type,
                        database_target=target,
                        priority=QueryPriority.NORMAL,
                        routing_reason=f"Pattern match: {pattern}"
                    )
                    
                    # Cache the result
                    self._routing_rules_cache[query_hash] = metadata
                    return metadata
        
        # Default classification based on query structure
        if any(op in query_upper for op in ["INSERT", "UPDATE", "DELETE"]):
            # Write operations -> PostgreSQL
            metadata = QueryMetadata(
                query_type=QueryType.TRANSACTIONAL,
                database_target=DatabaseTarget.POSTGRESQL,
                priority=QueryPriority.HIGH,
                routing_reason="Write operation detected"
            )
        elif any(keyword in query_upper for keyword in ["GROUP BY", "HAVING", "WINDOW"]):
            # Complex analytics -> DuckDB
            metadata = QueryMetadata(
                query_type=QueryType.ANALYTICS,
                database_target=DatabaseTarget.DUCKDB,
                priority=QueryPriority.NORMAL,
                routing_reason="Analytics pattern detected"
            )
        elif "COUNT(*)" in query_upper and "WHERE" not in query_upper:
            # Large aggregations -> DuckDB
            metadata = QueryMetadata(
                query_type=QueryType.AGGREGATION,
                database_target=DatabaseTarget.DUCKDB,
                priority=QueryPriority.NORMAL,
                routing_reason="Large aggregation detected"
            )
        else:
            # Default to PostgreSQL for unknown patterns
            metadata = QueryMetadata(
                query_type=QueryType.REAL_TIME_OPERATIONS,
                database_target=DatabaseTarget.POSTGRESQL,
                priority=QueryPriority.NORMAL,
                routing_reason="Default PostgreSQL routing"
            )
        
        # Cache the result
        self._routing_rules_cache[query_hash] = metadata
        return metadata
    
    def _get_default_target_for_type(self, query_type: QueryType) -> DatabaseTarget:
        """Get default database target for a query type"""
        oltp_types = {
            QueryType.USER_AUTH,
            QueryType.USER_MANAGEMENT,
            QueryType.PROJECT_CRUD,
            QueryType.PAGE_MANAGEMENT,
            QueryType.REAL_TIME_OPERATIONS,
            QueryType.TRANSACTIONAL,
            QueryType.HEALTH_CHECK,
            QueryType.ADMIN_OPERATIONS
        }
        
        olap_types = {
            QueryType.ANALYTICS,
            QueryType.AGGREGATION,
            QueryType.TIME_SERIES,
            QueryType.REPORTING,
            QueryType.SEARCH_COMPLEX,
            QueryType.BULK_READ
        }
        
        hybrid_types = {
            QueryType.CROSS_PROJECT_ANALYTICS,
            QueryType.USER_ACTIVITY_ANALYSIS,
            QueryType.PERFORMANCE_MONITORING
        }
        
        if query_type in oltp_types:
            return DatabaseTarget.POSTGRESQL
        elif query_type in olap_types:
            return DatabaseTarget.DUCKDB
        elif query_type in hybrid_types:
            return DatabaseTarget.HYBRID
        else:
            return DatabaseTarget.POSTGRESQL  # Default to OLTP
    
    def _extract_table_names(self, query: str) -> Set[str]:
        """Extract table names from SQL query"""
        # Simple regex-based extraction (could be enhanced with SQL parser)
        table_patterns = [
            r"FROM\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            r"JOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            r"INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)",
            r"UPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)"
        ]
        
        tables = set()
        query_upper = query.upper()
        
        for pattern in table_patterns:
            matches = re.findall(pattern, query_upper)
            tables.update(matches)
        
        return tables
    
    def _extract_operations(self, query: str) -> Set[str]:
        """Extract SQL operations from query"""
        operations = set()
        query_upper = query.upper()
        
        sql_keywords = [
            "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER",
            "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "OUTER JOIN",
            "GROUP BY", "ORDER BY", "HAVING", "WHERE", "UNION", "DISTINCT",
            "COUNT", "SUM", "AVG", "MIN", "MAX", "ROW_NUMBER", "RANK"
        ]
        
        for keyword in sql_keywords:
            if keyword in query_upper:
                operations.add(keyword.lower())
        
        return operations
    
    def _estimate_result_size(self, query: str, metadata: QueryMetadata) -> Optional[int]:
        """Estimate number of rows that will be returned"""
        # Simple heuristics (could be enhanced with statistics)
        if "COUNT(*)" in query.upper():
            return 1
        elif metadata.has_aggregations and "GROUP BY" in query.upper():
            return 100  # Estimate for grouped results
        elif any(table in ["pages_v2", "scrape_pages"] for table in metadata.tables_involved):
            return 10000  # Large tables
        elif "LIMIT" in query.upper():
            # Try to extract LIMIT value
            limit_match = re.search(r"LIMIT\s+(\d+)", query.upper())
            if limit_match:
                return int(limit_match.group(1))
        
        return None  # Unknown
    
    def _estimate_duration(self, query: str, metadata: QueryMetadata) -> Optional[float]:
        """Estimate query execution duration in seconds"""
        # Base estimates by query type
        duration_estimates = {
            QueryType.USER_AUTH: 0.01,
            QueryType.PROJECT_CRUD: 0.05,
            QueryType.ANALYTICS: 2.0,
            QueryType.AGGREGATION: 5.0,
            QueryType.TIME_SERIES: 10.0,
            QueryType.REPORTING: 15.0
        }
        
        base_duration = duration_estimates.get(metadata.query_type, 1.0)
        
        # Adjust based on complexity
        if metadata.has_joins:
            base_duration *= 2
        if metadata.has_aggregations:
            base_duration *= 1.5
        if metadata.has_window_functions:
            base_duration *= 3
        
        # Adjust based on estimated result size
        if metadata.estimated_rows:
            if metadata.estimated_rows > 100000:
                base_duration *= 3
            elif metadata.estimated_rows > 10000:
                base_duration *= 2
        
        return base_duration
    
    def _estimate_memory_usage(self, query: str, metadata: QueryMetadata) -> Optional[int]:
        """Estimate memory usage in MB"""
        # Base memory by query type
        memory_estimates = {
            QueryType.USER_AUTH: 1,
            QueryType.PROJECT_CRUD: 5,
            QueryType.ANALYTICS: 50,
            QueryType.AGGREGATION: 100,
            QueryType.TIME_SERIES: 200,
            QueryType.REPORTING: 500
        }
        
        base_memory = memory_estimates.get(metadata.query_type, 10)
        
        # Adjust based on complexity and result size
        if metadata.estimated_rows:
            # Rough estimate: 1KB per row
            estimated_mb = (metadata.estimated_rows * 1024) // (1024 * 1024)
            base_memory = max(base_memory, estimated_mb)
        
        return base_memory
    
    async def _execute_postgresql_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]],
        metadata: QueryMetadata
    ) -> QueryResult:
        """Execute query on PostgreSQL with circuit breaker protection"""
        start_time = time.time()
        
        async def _execute():
            async with AsyncSessionLocal() as session:
                if params:
                    result = await session.execute(text(query), params)
                else:
                    result = await session.execute(text(query))
                
                if metadata.is_write_operation:
                    await session.commit()
                
                # Fetch results based on operation type
                if query.upper().strip().startswith(('INSERT', 'UPDATE', 'DELETE')):
                    return {"rows_affected": result.rowcount}
                else:
                    return result.fetchall()
        
        try:
            data = await self.postgresql_breaker.execute(_execute)
            execution_time = time.time() - start_time
            
            self.metrics.postgresql_queries += 1
            
            return QueryResult(
                data=data,
                execution_time=execution_time,
                database_used=DatabaseTarget.POSTGRESQL,
                routing_metadata=metadata
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"PostgreSQL query failed after {execution_time:.3f}s: {e}")
            raise
    
    async def _execute_duckdb_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]],
        metadata: QueryMetadata
    ) -> QueryResult:
        """Execute query on DuckDB with circuit breaker protection"""
        if not self.duckdb_service:
            raise RuntimeError("DuckDB service not initialized")
        
        start_time = time.time()
        
        async def _execute():
            result = await self.duckdb_service.execute_query(query, params)
            return result
        
        try:
            duck_result = await self.duckdb_breaker.execute(_execute)
            execution_time = time.time() - start_time
            
            self.metrics.duckdb_queries += 1
            
            return QueryResult(
                data=duck_result.data,
                execution_time=execution_time,
                database_used=DatabaseTarget.DUCKDB,
                memory_used=duck_result.memory_usage,
                routing_metadata=metadata
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"DuckDB query failed after {execution_time:.3f}s: {e}")
            raise
    
    async def _execute_hybrid_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]],
        metadata: QueryMetadata
    ) -> QueryResult:
        """Execute hybrid query that requires both databases"""
        start_time = time.time()
        
        # For now, hybrid queries are executed on PostgreSQL with a warning
        # This can be enhanced to actually split queries or use federation
        
        result = await self._execute_postgresql_query(query, params, metadata)
        result.database_used = DatabaseTarget.HYBRID
        result.warnings.append("Hybrid query executed on PostgreSQL only")
        
        self.metrics.hybrid_queries += 1
        return result
    
    async def _auto_route_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]],
        metadata: QueryMetadata
    ) -> QueryResult:
        """Auto-route query based on current performance characteristics"""
        # Simple auto-routing logic (can be enhanced with ML)
        
        # Check circuit breaker states
        postgresql_available = self.postgresql_breaker.can_execute()
        duckdb_available = self.duckdb_breaker.can_execute()
        
        if not postgresql_available and not duckdb_available:
            raise RuntimeError("Both databases are unavailable")
        
        # Route based on estimated characteristics
        if metadata.estimated_duration and metadata.estimated_duration > 5.0:
            # Long-running queries -> DuckDB if available
            if duckdb_available:
                metadata.database_target = DatabaseTarget.DUCKDB
                metadata.routing_reason = "Auto-route: long duration -> DuckDB"
                return await self._execute_duckdb_query(query, params, metadata)
        
        if metadata.estimated_rows and metadata.estimated_rows > 10000:
            # Large result sets -> DuckDB if available
            if duckdb_available:
                metadata.database_target = DatabaseTarget.DUCKDB
                metadata.routing_reason = "Auto-route: large result set -> DuckDB"
                return await self._execute_duckdb_query(query, params, metadata)
        
        # Default to PostgreSQL
        if postgresql_available:
            metadata.database_target = DatabaseTarget.POSTGRESQL
            metadata.routing_reason = "Auto-route: default -> PostgreSQL"
            return await self._execute_postgresql_query(query, params, metadata)
        else:
            metadata.database_target = DatabaseTarget.DUCKDB
            metadata.routing_reason = "Auto-route: PostgreSQL unavailable -> DuckDB"
            return await self._execute_duckdb_query(query, params, metadata)
    
    def _generate_cache_key(self, query: str, params: Optional[Dict[str, Any]]) -> str:
        """Generate cache key for query and parameters"""
        content = query
        if params:
            content += json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    def _should_cache_result(self, metadata: QueryMetadata, result: QueryResult) -> bool:
        """Determine if result should be cached"""
        # Don't cache write operations or failed queries
        if metadata.is_write_operation:
            return False
        
        # Don't cache real-time or high-priority queries
        if metadata.priority in [QueryPriority.CRITICAL, QueryPriority.HIGH]:
            return False
        
        # Don't cache very fast queries (overhead not worth it)
        if result.execution_time < 0.1:
            return False
        
        # Cache analytics and reporting queries
        if metadata.query_type in [
            QueryType.ANALYTICS,
            QueryType.REPORTING,
            QueryType.AGGREGATION,
            QueryType.TIME_SERIES
        ]:
            return True
        
        return False
    
    def _get_cache_ttl(self, metadata: QueryMetadata) -> int:
        """Get cache TTL in seconds based on query type"""
        ttl_map = {
            QueryType.ANALYTICS: 1800,  # 30 minutes
            QueryType.REPORTING: 3600,  # 1 hour
            QueryType.AGGREGATION: 900,  # 15 minutes
            QueryType.TIME_SERIES: 600,  # 10 minutes
            QueryType.SEARCH_COMPLEX: 300,  # 5 minutes
        }
        
        return ttl_map.get(metadata.query_type, 600)  # Default 10 minutes
    
    def _update_metrics(self, result: QueryResult, metadata: QueryMetadata):
        """Update performance metrics"""
        self.metrics.total_queries += 1
        self.metrics.successful_queries += 1
        
        # Update response times
        self.metrics.response_times.append(result.execution_time)
        if self.metrics.response_times:
            self.metrics.avg_response_time = sum(self.metrics.response_times) / len(self.metrics.response_times)
        
        # Update query type counts
        self.metrics.query_type_counts[metadata.query_type.value] += 1
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics"""
        cache_stats = self.cache.get_stats()
        
        return {
            "overview": {
                "total_queries": self.metrics.total_queries,
                "success_rate": round(self.metrics.success_rate(), 2),
                "avg_response_time": round(self.metrics.avg_response_time, 3),
                "cache_hit_rate": cache_stats.get("hit_rate", 0)
            },
            "database_distribution": {
                "postgresql": self.metrics.postgresql_queries,
                "duckdb": self.metrics.duckdb_queries,
                "hybrid": self.metrics.hybrid_queries
            },
            "query_types": dict(self.metrics.query_type_counts),
            "circuit_breakers": {
                "postgresql": self.postgresql_breaker.get_status(),
                "duckdb": self.duckdb_breaker.get_status()
            },
            "cache": cache_stats,
            "response_times": {
                "recent": list(self.metrics.response_times)[-10:],
                "p50": self._calculate_percentile(50),
                "p95": self._calculate_percentile(95),
                "p99": self._calculate_percentile(99)
            }
        }
    
    def _calculate_percentile(self, percentile: int) -> float:
        """Calculate response time percentile"""
        if not self.metrics.response_times:
            return 0.0
        
        sorted_times = sorted(self.metrics.response_times)
        index = int((percentile / 100) * len(sorted_times))
        index = min(index, len(sorted_times) - 1)
        return sorted_times[index]
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {},
            "circuit_breakers": {},
            "cache": {},
            "metrics": {}
        }
        
        try:
            # Check PostgreSQL
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
                health["services"]["postgresql"] = "healthy"
        except Exception as e:
            health["services"]["postgresql"] = f"unhealthy: {str(e)}"
            health["status"] = "degraded"
        
        try:
            # Check DuckDB
            if self.duckdb_service:
                duck_health = await self.duckdb_service.health_check()
                health["services"]["duckdb"] = duck_health["status"]
            else:
                health["services"]["duckdb"] = "not_initialized"
        except Exception as e:
            health["services"]["duckdb"] = f"unhealthy: {str(e)}"
            health["status"] = "degraded"
        
        # Circuit breaker status
        health["circuit_breakers"] = {
            "postgresql": self.postgresql_breaker.get_status(),
            "duckdb": self.duckdb_breaker.get_status()
        }
        
        # Cache status
        health["cache"] = self.cache.get_stats()
        
        # Basic metrics
        health["metrics"] = {
            "total_queries": self.metrics.total_queries,
            "success_rate": self.metrics.success_rate()
        }
        
        return health
    
    @asynccontextmanager
    async def transaction(self, database_target: DatabaseTarget = DatabaseTarget.POSTGRESQL):
        """Context manager for database transactions"""
        if database_target == DatabaseTarget.POSTGRESQL:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    yield session
        elif database_target == DatabaseTarget.DUCKDB and self.duckdb_service:
            async with self.duckdb_service.transaction() as conn:
                yield conn
        else:
            raise ValueError(f"Unsupported transaction target: {database_target}")


# Global router instance
hybrid_router = HybridQueryRouter()


# FastAPI dependency
async def get_hybrid_router() -> HybridQueryRouter:
    """FastAPI dependency for hybrid query router"""
    if not hasattr(hybrid_router, '_initialized') or not hybrid_router._initialized:
        await hybrid_router.initialize()
    return hybrid_router


# Export public interface
__all__ = [
    'HybridQueryRouter',
    'QueryType',
    'DatabaseTarget',
    'QueryPriority',
    'QueryMetadata',
    'QueryResult',
    'PerformanceMetrics',
    'hybrid_router',
    'get_hybrid_router'
]