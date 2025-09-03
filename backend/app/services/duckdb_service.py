"""
DuckDB Analytics Service for FastAPI integration
Production-ready async wrapper with connection management and operational excellence
"""
import asyncio
import logging
import os
import psutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field

try:
    import duckdb
    from duckdb import DuckDBPyConnection
    DUCKDB_AVAILABLE = True
except ImportError:
    duckdb = None
    DuckDBPyConnection = None
    DUCKDB_AVAILABLE = False

from ..core.config import settings
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, circuit_registry

logger = logging.getLogger(__name__)


class DuckDBException(Exception):
    """Base exception for DuckDB operations"""
    pass


class DuckDBConnectionError(DuckDBException):
    """Connection-related errors"""
    pass


class DuckDBQueryError(DuckDBException):
    """Query execution errors"""
    pass


class DuckDBResourceError(DuckDBException):
    """Resource exhaustion errors"""
    pass


@dataclass
class ConnectionMetrics:
    """Metrics for connection monitoring"""
    total_connections: int = 0
    active_connections: int = 0
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    avg_query_time: float = 0.0
    memory_usage_mb: float = 0.0
    last_query_time: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def success_rate(self) -> float:
        """Calculate query success rate percentage"""
        if self.total_queries == 0:
            return 100.0
        return (self.successful_queries / self.total_queries) * 100.0


@dataclass
class QueryResult:
    """Query execution result with metadata"""
    data: Any
    execution_time: float
    memory_usage: float
    row_count: Optional[int] = None
    columns: Optional[List[str]] = None
    query_hash: Optional[str] = None


class ConnectionPool:
    """Thread-safe connection pool for DuckDB"""
    
    def __init__(self, database_path: str, max_connections: int = 10):
        self.database_path = database_path
        self.max_connections = max_connections
        self._connections: List['DuckDBPyConnection'] = []
        self._available_connections: List['DuckDBPyConnection'] = []
        self._connection_count = 0
        self._lock = threading.Lock()
        self._created_connections = set()
        
    def get_connection(self) -> 'DuckDBPyConnection':
        """Get a connection from the pool"""
        with self._lock:
            # Try to reuse available connection
            if self._available_connections:
                conn = self._available_connections.pop()
                logger.debug("Reusing pooled connection")
                return conn
            
            # Create new connection if under limit
            if self._connection_count < self.max_connections:
                conn = duckdb.connect(self.database_path)
                self._connections.append(conn)
                self._created_connections.add(id(conn))
                self._connection_count += 1
                logger.debug(f"Created new connection ({self._connection_count}/{self.max_connections})")
                return conn
            
            raise DuckDBResourceError(f"Connection pool exhausted ({self.max_connections} connections)")
    
    def return_connection(self, conn: 'DuckDBPyConnection'):
        """Return a connection to the pool"""
        with self._lock:
            if id(conn) in self._created_connections and conn not in self._available_connections:
                self._available_connections.append(conn)
                logger.debug("Returned connection to pool")
    
    def close_all(self):
        """Close all connections in the pool"""
        with self._lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")
            
            self._connections.clear()
            self._available_connections.clear()
            self._created_connections.clear()
            self._connection_count = 0
            logger.info("Closed all pooled connections")


class DuckDBService:
    """
    Production-ready DuckDB service with async operations and operational excellence
    
    Features:
    - Thread-safe async operations via ThreadPoolExecutor
    - Connection pooling and lifecycle management
    - Circuit breaker pattern for resilience
    - Comprehensive error handling and monitoring
    - Memory and performance optimization
    - Extension management (parquet, httpfs, json, S3)
    - Health checks and diagnostics
    """
    
    _instance: Optional['DuckDBService'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'DuckDBService':
        """Singleton pattern for service instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize DuckDB service with configuration"""
        if hasattr(self, '_initialized'):
            return
        
        if not DUCKDB_AVAILABLE:
            raise DuckDBException("DuckDB not available. Install with: pip install duckdb")
        
        # Configuration from settings
        self.database_path = settings.DUCKDB_DATABASE_PATH
        self.memory_limit = settings.DUCKDB_MEMORY_LIMIT
        self.worker_threads = settings.DUCKDB_WORKER_THREADS
        self.temp_directory = settings.DUCKDB_TEMP_DIRECTORY
        self.max_memory_percentage = settings.DUCKDB_MAX_MEMORY_PERCENTAGE
        self.enable_s3 = settings.DUCKDB_ENABLE_S3
        
        # Runtime state
        self._connection_pool: Optional[ConnectionPool] = None
        self._thread_pool: Optional[ThreadPoolExecutor] = None
        self._thread_local = threading.local()
        self._initialized = False
        self._shutdown = False
        
        # Metrics and monitoring
        self.metrics = ConnectionMetrics()
        self._query_times = []
        self._max_query_history = 1000
        
        # Circuit breaker for resilience
        self.circuit_breaker = self._get_circuit_breaker()
        
        logger.info(f"Initializing DuckDBService with database: {self.database_path}")
    
    def _get_circuit_breaker(self) -> CircuitBreaker:
        """Get or create circuit breaker for DuckDB operations"""
        config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=30,
            max_timeout_seconds=300,
            exponential_backoff=True,
            sliding_window_size=10
        )
        return circuit_registry.get_breaker("duckdb", config)
    
    async def initialize(self) -> None:
        """Initialize the DuckDB service and create necessary resources"""
        if self._initialized:
            logger.info("DuckDBService already initialized")
            return
        
        try:
            # Validate and prepare environment
            await self._prepare_environment()
            
            # Initialize thread pool for async operations
            self._thread_pool = ThreadPoolExecutor(
                max_workers=self.worker_threads,
                thread_name_prefix="duckdb-worker"
            )
            
            # Calculate optimal memory settings
            memory_limit_bytes = self._calculate_memory_limit()
            
            # Initialize connection pool
            self._connection_pool = ConnectionPool(
                database_path=self.database_path,
                max_connections=self.worker_threads * 2
            )
            
            # Create initial connection and configure extensions
            await self._initialize_database(memory_limit_bytes)
            
            # Validate installation
            await self._validate_setup()
            
            self._initialized = True
            logger.info(f"DuckDBService initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize DuckDBService: {e}")
            await self.shutdown()
            raise DuckDBException(f"Initialization failed: {e}") from e
    
    async def _prepare_environment(self) -> None:
        """Prepare file system and environment for DuckDB operations"""
        # Create database directory
        db_dir = Path(self.database_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        
        # Create temp directory
        temp_dir = Path(self.temp_directory)
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Check permissions
        if not os.access(db_dir, os.W_OK):
            raise DuckDBException(f"No write permission to database directory: {db_dir}")
        
        if not os.access(temp_dir, os.W_OK):
            raise DuckDBException(f"No write permission to temp directory: {temp_dir}")
        
        logger.info(f"Environment prepared: db={db_dir}, temp={temp_dir}")
    
    def _calculate_memory_limit(self) -> int:
        """Calculate optimal memory limit based on system resources"""
        try:
            # Get total system memory
            total_memory = psutil.virtual_memory().total
            
            # Calculate percentage-based limit
            calculated_limit = int(total_memory * (self.max_memory_percentage / 100))
            
            # Parse configured memory limit
            if self.memory_limit.upper().endswith('GB'):
                configured_limit = int(float(self.memory_limit[:-2]) * 1024 * 1024 * 1024)
            elif self.memory_limit.upper().endswith('MB'):
                configured_limit = int(float(self.memory_limit[:-2]) * 1024 * 1024)
            else:
                configured_limit = int(self.memory_limit)
            
            # Use the smaller of calculated and configured limits
            final_limit = min(calculated_limit, configured_limit)
            
            logger.info(f"Memory limit: {final_limit / (1024**3):.1f}GB "
                       f"(system: {total_memory / (1024**3):.1f}GB, "
                       f"percentage: {self.max_memory_percentage}%)")
            
            return final_limit
            
        except Exception as e:
            logger.warning(f"Could not calculate memory limit, using default: {e}")
            return 4 * 1024 * 1024 * 1024  # 4GB default
    
    async def _initialize_database(self, memory_limit_bytes: int) -> None:
        """Initialize database with extensions and configuration"""
        def _init_db():
            conn = duckdb.connect(self.database_path)
            
            try:
                # Set memory limit
                memory_mb = memory_limit_bytes // (1024 * 1024)
                conn.execute(f"SET memory_limit='{memory_mb}MB'")
                
                # Set temp directory
                conn.execute(f"SET temp_directory='{self.temp_directory}'")
                
                # Enable parallel processing
                conn.execute(f"SET threads={self.worker_threads}")
                
                # Install and load required extensions
                extensions = ['parquet', 'httpfs', 'json']
                
                for ext in extensions:
                    try:
                        conn.execute(f"INSTALL {ext}")
                        conn.execute(f"LOAD {ext}")
                        logger.info(f"Loaded DuckDB extension: {ext}")
                    except Exception as e:
                        logger.warning(f"Could not load extension {ext}: {e}")
                
                # Configure S3 if enabled
                if self.enable_s3 and settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                    try:
                        conn.execute(f"SET s3_region='{settings.AWS_DEFAULT_REGION}'")
                        conn.execute(f"SET s3_access_key_id='{settings.AWS_ACCESS_KEY_ID}'")
                        conn.execute(f"SET s3_secret_access_key='{settings.AWS_SECRET_ACCESS_KEY}'")
                        logger.info("Configured S3 access for DuckDB")
                    except Exception as e:
                        logger.warning(f"Could not configure S3: {e}")
                
                return conn
                
            except Exception:
                conn.close()
                raise
        
        # Initialize in thread pool
        conn = await asyncio.get_event_loop().run_in_executor(
            self._thread_pool, _init_db
        )
        
        # Return connection to pool
        self._connection_pool.return_connection(conn)
        
        logger.info("Database initialized with extensions and configuration")
    
    async def _validate_setup(self) -> None:
        """Validate that DuckDB is properly configured"""
        # Test basic functionality by directly using thread pool
        def _test_query():
            conn = self._connection_pool.get_connection()
            try:
                cursor = conn.execute("SELECT 'DuckDB setup validation' as status")
                result = cursor.fetchall()
                return result
            finally:
                self._connection_pool.return_connection(conn)
        
        result = await asyncio.get_event_loop().run_in_executor(
            self._thread_pool, _test_query
        )
        
        if not result:
            raise DuckDBException("Setup validation failed: no query result")
        
        # Test parquet support
        def _test_parquet():
            conn = self._connection_pool.get_connection()
            try:
                conn.execute("SELECT * FROM parquet_metadata('non_existent_file.parquet')")
            except Exception as e:
                if "No such file" not in str(e):
                    logger.warning(f"Parquet extension may not be working: {e}")
            finally:
                self._connection_pool.return_connection(conn)
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                self._thread_pool, _test_parquet
            )
        except Exception:
            pass  # Expected for non-existent file
        
        logger.info("DuckDB setup validation completed successfully")
    
    async def get_connection(self) -> 'DuckDBPyConnection':
        """Get a database connection (async wrapper)"""
        if not self._initialized:
            raise DuckDBException("Service not initialized. Call initialize() first.")
        
        def _get_conn():
            return self._connection_pool.get_connection()
        
        return await asyncio.get_event_loop().run_in_executor(
            self._thread_pool, _get_conn
        )
    
    def return_connection(self, conn: 'DuckDBPyConnection') -> None:
        """Return a connection to the pool"""
        if self._connection_pool:
            self._connection_pool.return_connection(conn)
    
    async def execute_query(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None,
        fetch_mode: str = "all"
    ) -> Optional[QueryResult]:
        """
        Execute a SQL query with comprehensive error handling and monitoring
        
        Args:
            query: SQL query string
            params: Query parameters (optional)
            fetch_mode: 'all', 'one', 'many', or 'none'
            
        Returns:
            QueryResult with data and metadata
        """
        if not self._initialized:
            raise DuckDBException("Service not initialized")
        
        start_time = time.time()
        
        def _execute():
            conn = None
            try:
                conn = self._connection_pool.get_connection()
                
                # Monitor memory before query
                process = psutil.Process()
                memory_before = process.memory_info().rss / (1024 * 1024)  # MB
                
                # Execute query with parameters
                if params:
                    cursor = conn.execute(query, params)
                else:
                    cursor = conn.execute(query)
                
                # Fetch results based on mode
                if fetch_mode == "none":
                    data = None
                    row_count = None
                elif fetch_mode == "one":
                    data = cursor.fetchone()
                    row_count = 1 if data else 0
                elif fetch_mode == "many":
                    data = cursor.fetchmany()
                    row_count = len(data) if data else 0
                else:  # "all"
                    data = cursor.fetchall()
                    row_count = len(data) if data else 0
                
                # Get column information
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                
                # Monitor memory after query
                memory_after = process.memory_info().rss / (1024 * 1024)  # MB
                memory_usage = memory_after - memory_before
                
                execution_time = time.time() - start_time
                
                return QueryResult(
                    data=data,
                    execution_time=execution_time,
                    memory_usage=memory_usage,
                    row_count=row_count,
                    columns=columns,
                    query_hash=str(hash(query))
                )
                
            finally:
                if conn:
                    self._connection_pool.return_connection(conn)
        
        try:
            # Execute with circuit breaker protection
            result = await self.circuit_breaker.execute(_execute)
            
            # Update metrics
            self._update_query_metrics(result.execution_time, success=True)
            self.metrics.successful_queries += 1
            
            logger.debug(f"Query executed successfully in {result.execution_time:.3f}s, "
                        f"memory: {result.memory_usage:.1f}MB, rows: {result.row_count}")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            self._update_query_metrics(execution_time, success=False)
            self.metrics.failed_queries += 1
            
            logger.error(f"Query execution failed after {execution_time:.3f}s: {e}")
            
            # Classify error type
            if "memory" in str(e).lower():
                raise DuckDBResourceError(f"Memory limit exceeded: {e}") from e
            elif "connection" in str(e).lower():
                raise DuckDBConnectionError(f"Connection error: {e}") from e
            else:
                raise DuckDBQueryError(f"Query error: {e}") from e
    
    async def execute_batch(self, queries: List[str]) -> List[Optional[QueryResult]]:
        """
        Execute multiple queries in batch with transaction support
        
        Args:
            queries: List of SQL query strings
            
        Returns:
            List of QueryResult objects
        """
        if not queries:
            return []
        
        results = []
        
        def _execute_batch():
            conn = None
            try:
                conn = self._connection_pool.get_connection()
                conn.execute("BEGIN TRANSACTION")
                
                batch_results = []
                for i, query in enumerate(queries):
                    try:
                        start_time = time.time()
                        cursor = conn.execute(query)
                        data = cursor.fetchall()
                        execution_time = time.time() - start_time
                        
                        result = QueryResult(
                            data=data,
                            execution_time=execution_time,
                            memory_usage=0.0,  # Not tracked per query in batch
                            row_count=len(data) if data else 0,
                            columns=[desc[0] for desc in cursor.description] if cursor.description else []
                        )
                        batch_results.append(result)
                        
                    except Exception as e:
                        logger.error(f"Query {i+1} in batch failed: {e}")
                        conn.execute("ROLLBACK")
                        raise DuckDBQueryError(f"Batch query {i+1} failed: {e}") from e
                
                conn.execute("COMMIT")
                return batch_results
                
            except Exception:
                if conn:
                    try:
                        conn.execute("ROLLBACK")
                    except Exception:
                        pass
                raise
            finally:
                if conn:
                    self._connection_pool.return_connection(conn)
        
        try:
            results = await self.circuit_breaker.execute(_execute_batch)
            self.metrics.successful_queries += len(queries)
            logger.info(f"Batch of {len(queries)} queries executed successfully")
            
        except Exception as e:
            self.metrics.failed_queries += len(queries)
            logger.error(f"Batch execution failed: {e}")
            raise
        
        return results
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Comprehensive health check with system diagnostics
        
        Returns:
            Health status dictionary
        """
        health_status = {
            "status": "unknown",
            "timestamp": datetime.now().isoformat(),
            "service_initialized": self._initialized,
            "database_path": self.database_path,
            "database_exists": Path(self.database_path).exists() if self._initialized else False,
            "circuit_breaker": self.circuit_breaker.get_status(),
            "metrics": self._get_metrics_dict(),
            "system": self._get_system_metrics(),
            "errors": []
        }
        
        try:
            if not self._initialized:
                health_status["status"] = "not_initialized"
                health_status["errors"].append("Service not initialized")
                return health_status
            
            # Test basic connectivity
            result = await self.execute_query("SELECT 1 as health_check")
            
            if result and result.data:
                health_status["status"] = "healthy"
                health_status["query_test"] = {
                    "success": True,
                    "execution_time": result.execution_time,
                    "memory_usage": result.memory_usage
                }
            else:
                health_status["status"] = "unhealthy"
                health_status["errors"].append("Query test failed: no result")
            
            # Check database file size
            if Path(self.database_path).exists():
                health_status["database_size_mb"] = Path(self.database_path).stat().st_size / (1024 * 1024)
            
            # Check connection pool status
            if self._connection_pool:
                health_status["connection_pool"] = {
                    "total_connections": self._connection_pool._connection_count,
                    "available_connections": len(self._connection_pool._available_connections),
                    "max_connections": self._connection_pool.max_connections
                }
            
        except Exception as e:
            health_status["status"] = "unhealthy"
            health_status["errors"].append(f"Health check failed: {str(e)}")
            logger.error(f"Health check failed: {e}")
        
        return health_status
    
    async def get_statistics(self) -> Dict[str, Any]:
        """
        Get detailed service statistics and performance metrics
        
        Returns:
            Statistics dictionary
        """
        stats = {
            "service": {
                "initialized": self._initialized,
                "uptime_seconds": (datetime.now() - self.metrics.created_at).total_seconds(),
                "database_path": self.database_path,
                "memory_limit": self.memory_limit,
                "worker_threads": self.worker_threads
            },
            "metrics": self._get_metrics_dict(),
            "performance": {
                "avg_query_time": self.metrics.avg_query_time,
                "recent_query_times": self._query_times[-10:] if self._query_times else [],
                "success_rate": self.metrics.success_rate()
            },
            "system": self._get_system_metrics(),
            "circuit_breaker": self.circuit_breaker.get_status()
        }
        
        # Add database file information
        if Path(self.database_path).exists():
            stat = Path(self.database_path).stat()
            stats["database_file"] = {
                "size_mb": stat.st_size / (1024 * 1024),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            }
        
        # Add query history analysis
        if self._query_times:
            times = self._query_times
            stats["query_analysis"] = {
                "total_queries": len(times),
                "min_time": min(times),
                "max_time": max(times),
                "median_time": sorted(times)[len(times)//2] if times else 0,
                "queries_over_1s": len([t for t in times if t > 1.0]),
                "queries_over_5s": len([t for t in times if t > 5.0])
            }
        
        return stats
    
    def _get_metrics_dict(self) -> Dict[str, Any]:
        """Get metrics as dictionary"""
        return {
            "total_connections": self.metrics.total_connections,
            "active_connections": self.metrics.active_connections,
            "total_queries": self.metrics.total_queries,
            "successful_queries": self.metrics.successful_queries,
            "failed_queries": self.metrics.failed_queries,
            "success_rate": round(self.metrics.success_rate(), 2),
            "avg_query_time": round(self.metrics.avg_query_time, 3),
            "memory_usage_mb": round(self.metrics.memory_usage_mb, 1),
            "last_query_time": self.metrics.last_query_time.isoformat() if self.metrics.last_query_time else None
        }
    
    def _get_system_metrics(self) -> Dict[str, Any]:
        """Get system resource metrics"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return {
                "process_memory_mb": memory_info.rss / (1024 * 1024),
                "process_memory_percent": process.memory_percent(),
                "cpu_percent": process.cpu_percent(),
                "system_memory_percent": psutil.virtual_memory().percent,
                "system_cpu_percent": psutil.cpu_percent(),
                "disk_usage_percent": psutil.disk_usage(Path(self.database_path).parent).percent
            }
        except Exception as e:
            logger.warning(f"Could not get system metrics: {e}")
            return {"error": str(e)}
    
    def _update_query_metrics(self, execution_time: float, success: bool):
        """Update internal query metrics"""
        self.metrics.total_queries += 1
        self.metrics.last_query_time = datetime.now()
        
        # Update query times history
        self._query_times.append(execution_time)
        if len(self._query_times) > self._max_query_history:
            self._query_times = self._query_times[-self._max_query_history:]
        
        # Update average query time
        if self._query_times:
            self.metrics.avg_query_time = sum(self._query_times) / len(self._query_times)
        
        # Update memory usage
        try:
            process = psutil.Process()
            self.metrics.memory_usage_mb = process.memory_info().rss / (1024 * 1024)
        except Exception:
            pass
    
    @asynccontextmanager
    async def transaction(self):
        """
        Async context manager for database transactions
        
        Usage:
            async with service.transaction() as conn:
                await conn.execute("INSERT ...")
                await conn.execute("UPDATE ...")
        """
        conn = await self.get_connection()
        try:
            await asyncio.get_event_loop().run_in_executor(
                self._thread_pool, 
                lambda: conn.execute("BEGIN TRANSACTION")
            )
            yield conn
            await asyncio.get_event_loop().run_in_executor(
                self._thread_pool, 
                lambda: conn.execute("COMMIT")
            )
        except Exception:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    self._thread_pool, 
                    lambda: conn.execute("ROLLBACK")
                )
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
            raise
        finally:
            self.return_connection(conn)
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the service and cleanup resources"""
        if self._shutdown:
            return
        
        logger.info("Shutting down DuckDBService...")
        self._shutdown = True
        
        # Close connection pool
        if self._connection_pool:
            await asyncio.get_event_loop().run_in_executor(
                self._thread_pool,
                self._connection_pool.close_all
            )
        
        # Shutdown thread pool
        if self._thread_pool:
            self._thread_pool.shutdown(wait=True)
        
        self._initialized = False
        logger.info("DuckDBService shutdown completed")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.shutdown()


# Global service instance
duckdb_service = DuckDBService()


# FastAPI dependency
async def get_duckdb_service() -> DuckDBService:
    """
    FastAPI dependency for DuckDB service
    
    Usage:
        @app.get("/analytics")
        async def analytics(service: DuckDBService = Depends(get_duckdb_service)):
            result = await service.execute_query("SELECT * FROM analytics")
            return result.data
    """
    if not duckdb_service._initialized:
        await duckdb_service.initialize()
    return duckdb_service


# Utility functions for common operations
async def execute_analytics_query(query: str, params: Optional[Dict] = None) -> Any:
    """
    Convenience function for executing analytics queries
    
    Args:
        query: SQL query string
        params: Optional query parameters
        
    Returns:
        Query result data
    """
    service = await get_duckdb_service()
    result = await service.execute_query(query, params)
    return result.data if result else None


async def get_service_health() -> Dict[str, Any]:
    """Get DuckDB service health status for monitoring"""
    service = await get_duckdb_service()
    return await service.health_check()


# Export public interface
__all__ = [
    'DuckDBService',
    'DuckDBException',
    'DuckDBConnectionError',
    'DuckDBQueryError',
    'DuckDBResourceError',
    'QueryResult',
    'ConnectionMetrics',
    'duckdb_service',
    'get_duckdb_service',
    'execute_analytics_query',
    'get_service_health'
]