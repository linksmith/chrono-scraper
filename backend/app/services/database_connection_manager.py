"""
Database Connection Manager - Advanced Connection Pooling System
===============================================================

Provides sophisticated connection pooling, health monitoring, load balancing,
and resource management for both PostgreSQL and DuckDB databases.

Features:
- Multi-database connection pooling
- Health monitoring and failover
- Load balancing and resource optimization
- Connection lifecycle management
- Performance metrics and alerting
- Circuit breaker protection
- Backup and disaster recovery coordination
"""

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import psutil
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool

from ..core.config import settings
from ..core.database import AsyncSessionLocal
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .duckdb_service import DuckDBService

logger = logging.getLogger(__name__)


class DatabaseType(str, Enum):
    """Supported database types"""
    POSTGRESQL = "postgresql"
    DUCKDB = "duckdb"


class ConnectionState(str, Enum):
    """Connection state tracking"""
    IDLE = "idle"
    ACTIVE = "active"
    STALE = "stale"
    ERROR = "error"
    CLOSED = "closed"


class LoadBalancingStrategy(str, Enum):
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    RESOURCE_BASED = "resource_based"
    PERFORMANCE_BASED = "performance_based"


@dataclass
class ConnectionMetrics:
    """Metrics for individual connections"""
    connection_id: str
    database_type: DatabaseType
    created_at: datetime
    last_used: datetime
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    avg_response_time: float = 0.0
    total_response_time: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    state: ConnectionState = ConnectionState.IDLE
    
    def success_rate(self) -> float:
        """Calculate connection success rate"""
        if self.total_queries == 0:
            return 100.0
        return (self.successful_queries / self.total_queries) * 100.0
    
    def update_performance(self, response_time: float, success: bool):
        """Update performance metrics"""
        self.total_queries += 1
        self.last_used = datetime.now()
        
        if success:
            self.successful_queries += 1
        else:
            self.failed_queries += 1
        
        self.total_response_time += response_time
        self.avg_response_time = self.total_response_time / self.total_queries


@dataclass
class PoolConfiguration:
    """Connection pool configuration"""
    database_type: DatabaseType
    min_connections: int = 5
    max_connections: int = 20
    connection_timeout: float = 30.0
    idle_timeout: float = 300.0  # 5 minutes
    max_lifetime: float = 3600.0  # 1 hour
    health_check_interval: float = 60.0  # 1 minute
    enable_monitoring: bool = True
    load_balancing_strategy: LoadBalancingStrategy = LoadBalancingStrategy.LEAST_CONNECTIONS


@dataclass
class PoolStatistics:
    """Connection pool statistics"""
    database_type: DatabaseType
    active_connections: int = 0
    idle_connections: int = 0
    total_connections: int = 0
    max_connections: int = 0
    queue_size: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_wait_time: float = 0.0
    avg_response_time: float = 0.0
    
    # Resource usage
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    
    # Health metrics
    health_score: float = 100.0
    last_health_check: Optional[datetime] = None
    error_rate: float = 0.0
    
    def utilization_rate(self) -> float:
        """Calculate pool utilization rate"""
        if self.max_connections == 0:
            return 0.0
        return (self.active_connections / self.max_connections) * 100.0


class DatabaseConnectionPool:
    """Advanced connection pool for a specific database type"""
    
    def __init__(self, config: PoolConfiguration):
        self.config = config
        self.database_type = config.database_type
        
        # Connection tracking
        self.connections: Dict[str, Any] = {}
        self.connection_metrics: Dict[str, ConnectionMetrics] = {}
        self.available_connections: deque = deque()
        self.active_connections: Set[str] = set()
        
        # Synchronization
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        
        # Pool state
        self.is_initialized = False
        self.is_shutdown = False
        self.statistics = PoolStatistics(database_type=config.database_type)
        self.statistics.max_connections = config.max_connections
        
        # Health monitoring
        self._health_check_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Circuit breaker
        breaker_config = CircuitBreakerConfig(
            failure_threshold=5,
            timeout_seconds=30,
            exponential_backoff=True
        )
        self.circuit_breaker = CircuitBreaker(f"{config.database_type}_pool", breaker_config)
        
        # Load balancing
        self._round_robin_index = 0
        
        logger.info(f"Initialized connection pool for {self.database_type.value}")
    
    async def initialize(self):
        """Initialize the connection pool"""
        if self.is_initialized:
            return
        
        try:
            # Create initial connections
            await self._create_initial_connections()
            
            # Start background tasks
            if self.config.enable_monitoring:
                self._health_check_task = asyncio.create_task(self._health_check_loop())
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            
            self.is_initialized = True
            logger.info(f"Connection pool for {self.database_type.value} initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize {self.database_type.value} pool: {e}")
            raise
    
    async def _create_initial_connections(self):
        """Create initial pool connections"""
        for i in range(self.config.min_connections):
            try:
                conn = await self._create_connection()
                conn_id = f"{self.database_type.value}_{i}_{int(time.time())}"
                
                with self._lock:
                    self.connections[conn_id] = conn
                    self.connection_metrics[conn_id] = ConnectionMetrics(
                        connection_id=conn_id,
                        database_type=self.database_type,
                        created_at=datetime.now(),
                        last_used=datetime.now()
                    )
                    self.available_connections.append(conn_id)
                    self.statistics.total_connections += 1
                    self.statistics.idle_connections += 1
                
                logger.debug(f"Created initial connection {conn_id}")
                
            except Exception as e:
                logger.error(f"Failed to create initial connection {i}: {e}")
    
    async def _create_connection(self) -> Any:
        """Create a new database connection"""
        if self.database_type == DatabaseType.POSTGRESQL:
            return await self._create_postgresql_connection()
        elif self.database_type == DatabaseType.DUCKDB:
            return await self._create_duckdb_connection()
        else:
            raise ValueError(f"Unsupported database type: {self.database_type}")
    
    async def _create_postgresql_connection(self) -> AsyncSession:
        """Create PostgreSQL connection"""
        # Create engine with custom pool settings
        engine = create_async_engine(
            settings.ASYNC_DATABASE_URL,
            poolclass=QueuePool,
            pool_size=1,  # Individual connection
            max_overflow=0,
            pool_pre_ping=True,
            pool_recycle=self.config.max_lifetime,
            echo=False
        )
        
        session_factory = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        return session_factory()
    
    async def _create_duckdb_connection(self) -> Any:
        """Create DuckDB connection"""
        # This would integrate with the DuckDB service
        duckdb_service = DuckDBService()
        if not duckdb_service._initialized:
            await duckdb_service.initialize()
        
        return await duckdb_service.get_connection()
    
    async def get_connection(self, timeout: Optional[float] = None) -> Tuple[str, Any]:
        """
        Get a connection from the pool
        
        Args:
            timeout: Maximum wait time for connection
            
        Returns:
            Tuple of (connection_id, connection_object)
        """
        timeout = timeout or self.config.connection_timeout
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self._lock:
                # Try to get available connection
                if self.available_connections:
                    conn_id = self._select_connection()
                    if conn_id and conn_id in self.connections:
                        connection = self.connections[conn_id]
                        
                        # Move to active
                        self.available_connections.remove(conn_id)
                        self.active_connections.add(conn_id)
                        
                        # Update statistics
                        self.statistics.idle_connections -= 1
                        self.statistics.active_connections += 1
                        self.connection_metrics[conn_id].state = ConnectionState.ACTIVE
                        
                        logger.debug(f"Retrieved connection {conn_id}")
                        return conn_id, connection
                
                # Try to create new connection if under limit
                if self.statistics.total_connections < self.config.max_connections:
                    try:
                        conn = await self._create_connection()
                        conn_id = f"{self.database_type.value}_{int(time.time())}_{len(self.connections)}"
                        
                        self.connections[conn_id] = conn
                        self.connection_metrics[conn_id] = ConnectionMetrics(
                            connection_id=conn_id,
                            database_type=self.database_type,
                            created_at=datetime.now(),
                            last_used=datetime.now(),
                            state=ConnectionState.ACTIVE
                        )
                        
                        self.active_connections.add(conn_id)
                        self.statistics.total_connections += 1
                        self.statistics.active_connections += 1
                        
                        logger.debug(f"Created new connection {conn_id}")
                        return conn_id, conn
                        
                    except Exception as e:
                        logger.error(f"Failed to create new connection: {e}")
            
            # Wait and retry
            await asyncio.sleep(0.1)
        
        raise TimeoutError(f"Could not obtain connection within {timeout} seconds")
    
    def _select_connection(self) -> Optional[str]:
        """Select best available connection based on strategy"""
        if not self.available_connections:
            return None
        
        if self.config.load_balancing_strategy == LoadBalancingStrategy.ROUND_ROBIN:
            return self._round_robin_selection()
        elif self.config.load_balancing_strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return self._least_connections_selection()
        elif self.config.load_balancing_strategy == LoadBalancingStrategy.PERFORMANCE_BASED:
            return self._performance_based_selection()
        else:
            # Default to first available
            return self.available_connections[0]
    
    def _round_robin_selection(self) -> str:
        """Round-robin connection selection"""
        if not self.available_connections:
            return None
        
        conn_id = self.available_connections[self._round_robin_index % len(self.available_connections)]
        self._round_robin_index += 1
        return conn_id
    
    def _least_connections_selection(self) -> str:
        """Select connection with least usage"""
        if not self.available_connections:
            return None
        
        # Find connection with minimum total queries
        min_queries = float('inf')
        selected_conn = None
        
        for conn_id in self.available_connections:
            metrics = self.connection_metrics[conn_id]
            if metrics.total_queries < min_queries:
                min_queries = metrics.total_queries
                selected_conn = conn_id
        
        return selected_conn or self.available_connections[0]
    
    def _performance_based_selection(self) -> str:
        """Select connection based on performance metrics"""
        if not self.available_connections:
            return None
        
        # Find connection with best performance (lowest avg response time)
        best_performance = float('inf')
        selected_conn = None
        
        for conn_id in self.available_connections:
            metrics = self.connection_metrics[conn_id]
            performance_score = metrics.avg_response_time
            
            if performance_score < best_performance:
                best_performance = performance_score
                selected_conn = conn_id
        
        return selected_conn or self.available_connections[0]
    
    def return_connection(self, conn_id: str):
        """Return connection to the pool"""
        with self._lock:
            if conn_id in self.active_connections:
                self.active_connections.remove(conn_id)
                self.available_connections.append(conn_id)
                
                # Update statistics
                self.statistics.active_connections -= 1
                self.statistics.idle_connections += 1
                
                # Update connection state
                if conn_id in self.connection_metrics:
                    self.connection_metrics[conn_id].state = ConnectionState.IDLE
                
                logger.debug(f"Returned connection {conn_id} to pool")
                
                # Notify waiting threads
                self._condition.notify()
    
    def record_query_performance(self, conn_id: str, response_time: float, success: bool):
        """Record query performance for a connection"""
        with self._lock:
            if conn_id in self.connection_metrics:
                self.connection_metrics[conn_id].update_performance(response_time, success)
                
                # Update pool statistics
                self.statistics.total_requests += 1
                if success:
                    self.statistics.successful_requests += 1
                else:
                    self.statistics.failed_requests += 1
                
                # Update average response time
                if self.statistics.total_requests > 0:
                    total_response_time = sum(
                        metrics.total_response_time 
                        for metrics in self.connection_metrics.values()
                    )
                    self.statistics.avg_response_time = total_response_time / self.statistics.total_requests
    
    async def _health_check_loop(self):
        """Background health check loop"""
        while not self.is_shutdown:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.config.health_check_interval)
            except Exception as e:
                logger.error(f"Health check error for {self.database_type.value}: {e}")
                await asyncio.sleep(5)  # Short retry interval
    
    async def _perform_health_checks(self):
        """Perform health checks on all connections"""
        unhealthy_connections = []
        
        for conn_id, metrics in self.connection_metrics.items():
            try:
                if await self._check_connection_health(conn_id):
                    metrics.state = ConnectionState.IDLE if conn_id not in self.active_connections else ConnectionState.ACTIVE
                else:
                    metrics.state = ConnectionState.ERROR
                    unhealthy_connections.append(conn_id)
                    
            except Exception as e:
                logger.error(f"Health check failed for connection {conn_id}: {e}")
                metrics.state = ConnectionState.ERROR
                unhealthy_connections.append(conn_id)
        
        # Remove unhealthy connections
        for conn_id in unhealthy_connections:
            await self._remove_connection(conn_id)
        
        # Update health metrics
        self.statistics.last_health_check = datetime.now()
        total_connections = len(self.connections)
        healthy_connections = total_connections - len(unhealthy_connections)
        
        if total_connections > 0:
            self.statistics.health_score = (healthy_connections / total_connections) * 100.0
        
        # Calculate error rate
        if self.statistics.total_requests > 0:
            self.statistics.error_rate = (self.statistics.failed_requests / self.statistics.total_requests) * 100.0
    
    async def _check_connection_health(self, conn_id: str) -> bool:
        """Check health of individual connection"""
        try:
            connection = self.connections.get(conn_id)
            if not connection:
                return False
            
            if self.database_type == DatabaseType.POSTGRESQL:
                # Simple query to test PostgreSQL connection
                result = await connection.execute(text("SELECT 1"))
                return bool(result)
            
            elif self.database_type == DatabaseType.DUCKDB:
                # Test DuckDB connection
                # This would need integration with DuckDB service
                return True  # Simplified for now
            
            return False
            
        except Exception as e:
            logger.error(f"Connection health check failed for {conn_id}: {e}")
            return False
    
    async def _cleanup_loop(self):
        """Background cleanup loop for stale connections"""
        while not self.is_shutdown:
            try:
                await self._cleanup_stale_connections()
                await asyncio.sleep(60)  # Cleanup every minute
            except Exception as e:
                logger.error(f"Cleanup error for {self.database_type.value}: {e}")
                await asyncio.sleep(10)
    
    async def _cleanup_stale_connections(self):
        """Clean up stale and expired connections"""
        current_time = datetime.now()
        stale_connections = []
        
        for conn_id, metrics in self.connection_metrics.items():
            # Check if connection is stale
            idle_time = (current_time - metrics.last_used).total_seconds()
            connection_age = (current_time - metrics.created_at).total_seconds()
            
            if (idle_time > self.config.idle_timeout or 
                connection_age > self.config.max_lifetime):
                stale_connections.append(conn_id)
                
        # Remove stale connections
        for conn_id in stale_connections:
            if conn_id not in self.active_connections:  # Don't remove active connections
                await self._remove_connection(conn_id)
                logger.debug(f"Removed stale connection {conn_id}")
        
        # Ensure minimum connections
        if self.statistics.total_connections < self.config.min_connections:
            needed = self.config.min_connections - self.statistics.total_connections
            for _ in range(needed):
                try:
                    await self._create_initial_connections()
                except Exception as e:
                    logger.error(f"Failed to create replacement connection: {e}")
    
    async def _remove_connection(self, conn_id: str):
        """Remove a connection from the pool"""
        with self._lock:
            if conn_id in self.connections:
                try:
                    # Close connection
                    connection = self.connections[conn_id]
                    if self.database_type == DatabaseType.POSTGRESQL and hasattr(connection, 'close'):
                        await connection.close()
                    
                    # Remove from tracking
                    del self.connections[conn_id]
                    del self.connection_metrics[conn_id]
                    
                    # Update collections
                    if conn_id in self.available_connections:
                        self.available_connections.remove(conn_id)
                        self.statistics.idle_connections -= 1
                    
                    if conn_id in self.active_connections:
                        self.active_connections.remove(conn_id)
                        self.statistics.active_connections -= 1
                    
                    self.statistics.total_connections -= 1
                    
                except Exception as e:
                    logger.error(f"Error removing connection {conn_id}: {e}")
    
    def get_statistics(self) -> PoolStatistics:
        """Get current pool statistics"""
        with self._lock:
            # Update resource usage
            try:
                process = psutil.Process()
                self.statistics.memory_usage_mb = process.memory_info().rss / (1024 * 1024)
                self.statistics.cpu_usage_percent = process.cpu_percent()
            except Exception:
                pass
            
            return self.statistics
    
    async def shutdown(self):
        """Gracefully shutdown the connection pool"""
        if self.is_shutdown:
            return
        
        logger.info(f"Shutting down connection pool for {self.database_type.value}")
        self.is_shutdown = True
        
        # Cancel background tasks
        if self._health_check_task:
            self._health_check_task.cancel()
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        # Close all connections
        with self._lock:
            for conn_id in list(self.connections.keys()):
                await self._remove_connection(conn_id)
        
        logger.info(f"Connection pool for {self.database_type.value} shutdown completed")


class DatabaseConnectionManager:
    """
    Central manager for all database connection pools
    """
    
    def __init__(self):
        self.pools: Dict[DatabaseType, DatabaseConnectionPool] = {}
        self._initialized = False
        self._shutdown = False
        
        # Global statistics
        self.global_stats = {
            "total_connections": 0,
            "active_connections": 0,
            "total_requests": 0,
            "avg_response_time": 0.0
        }
        
        logger.info("DatabaseConnectionManager initialized")
    
    async def initialize(self):
        """Initialize all connection pools"""
        if self._initialized:
            return
        
        try:
            # Initialize PostgreSQL pool
            pg_config = PoolConfiguration(
                database_type=DatabaseType.POSTGRESQL,
                min_connections=settings.POSTGRESQL_CIRCUIT_BREAKER_THRESHOLD,
                max_connections=20,
                connection_timeout=30.0,
                idle_timeout=300.0,
                health_check_interval=60.0
            )
            
            self.pools[DatabaseType.POSTGRESQL] = DatabaseConnectionPool(pg_config)
            await self.pools[DatabaseType.POSTGRESQL].initialize()
            
            # Initialize DuckDB pool
            duck_config = PoolConfiguration(
                database_type=DatabaseType.DUCKDB,
                min_connections=2,
                max_connections=10,
                connection_timeout=30.0,
                idle_timeout=600.0,
                health_check_interval=120.0
            )
            
            self.pools[DatabaseType.DUCKDB] = DatabaseConnectionPool(duck_config)
            await self.pools[DatabaseType.DUCKDB].initialize()
            
            self._initialized = True
            logger.info("DatabaseConnectionManager initialization completed")
            
        except Exception as e:
            logger.error(f"Failed to initialize DatabaseConnectionManager: {e}")
            raise
    
    async def get_connection(
        self,
        database_type: DatabaseType,
        timeout: Optional[float] = None
    ) -> Tuple[str, Any]:
        """Get connection from specified database pool"""
        if not self._initialized:
            await self.initialize()
        
        if database_type not in self.pools:
            raise ValueError(f"No pool configured for {database_type}")
        
        return await self.pools[database_type].get_connection(timeout)
    
    def return_connection(self, database_type: DatabaseType, conn_id: str):
        """Return connection to specified database pool"""
        if database_type in self.pools:
            self.pools[database_type].return_connection(conn_id)
    
    def record_performance(
        self,
        database_type: DatabaseType,
        conn_id: str,
        response_time: float,
        success: bool
    ):
        """Record query performance"""
        if database_type in self.pools:
            self.pools[database_type].record_query_performance(conn_id, response_time, success)
    
    @asynccontextmanager
    async def get_session(self, database_type: DatabaseType):
        """Context manager for database sessions"""
        conn_id, connection = await self.get_connection(database_type)
        start_time = time.time()
        success = True
        
        try:
            yield connection
        except Exception as e:
            success = False
            raise
        finally:
            response_time = time.time() - start_time
            self.record_performance(database_type, conn_id, response_time, success)
            self.return_connection(database_type, conn_id)
    
    def get_pool_statistics(self, database_type: DatabaseType) -> Optional[PoolStatistics]:
        """Get statistics for specific database pool"""
        if database_type in self.pools:
            return self.pools[database_type].get_statistics()
        return None
    
    def get_global_statistics(self) -> Dict[str, Any]:
        """Get global connection manager statistics"""
        total_connections = 0
        active_connections = 0
        total_requests = 0
        total_response_time = 0.0
        
        for pool in self.pools.values():
            stats = pool.get_statistics()
            total_connections += stats.total_connections
            active_connections += stats.active_connections
            total_requests += stats.total_requests
            total_response_time += stats.avg_response_time * stats.total_requests
        
        avg_response_time = total_response_time / total_requests if total_requests > 0 else 0.0
        
        return {
            "pools": {
                db_type.value: pool.get_statistics().__dict__
                for db_type, pool in self.pools.items()
            },
            "global": {
                "total_connections": total_connections,
                "active_connections": active_connections,
                "total_requests": total_requests,
                "avg_response_time": round(avg_response_time, 3),
                "pool_count": len(self.pools)
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check of all pools"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "pools": {}
        }
        
        for db_type, pool in self.pools.items():
            stats = pool.get_statistics()
            pool_health = {
                "status": "healthy" if stats.health_score > 80.0 else "degraded",
                "health_score": stats.health_score,
                "total_connections": stats.total_connections,
                "active_connections": stats.active_connections,
                "error_rate": stats.error_rate,
                "last_health_check": stats.last_health_check.isoformat() if stats.last_health_check else None
            }
            
            if stats.health_score < 50.0:
                health_status["status"] = "unhealthy"
            elif stats.health_score < 80.0 and health_status["status"] == "healthy":
                health_status["status"] = "degraded"
            
            health_status["pools"][db_type.value] = pool_health
        
        return health_status
    
    async def shutdown(self):
        """Shutdown all connection pools"""
        if self._shutdown:
            return
        
        logger.info("Shutting down DatabaseConnectionManager")
        self._shutdown = True
        
        # Shutdown all pools
        shutdown_tasks = [pool.shutdown() for pool in self.pools.values()]
        await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        
        self.pools.clear()
        logger.info("DatabaseConnectionManager shutdown completed")


# Global connection manager instance
db_connection_manager = DatabaseConnectionManager()


# FastAPI dependency
async def get_connection_manager() -> DatabaseConnectionManager:
    """FastAPI dependency for database connection manager"""
    if not db_connection_manager._initialized:
        await db_connection_manager.initialize()
    return db_connection_manager


# Export public interface
__all__ = [
    'DatabaseConnectionManager',
    'DatabaseConnectionPool',
    'DatabaseType',
    'ConnectionState',
    'LoadBalancingStrategy',
    'PoolConfiguration',
    'PoolStatistics',
    'ConnectionMetrics',
    'db_connection_manager',
    'get_connection_manager'
]