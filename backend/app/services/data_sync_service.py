"""
DataSyncService for maintaining data consistency between PostgreSQL (OLTP) and DuckDB (OLAP)

This service implements comprehensive dual-write patterns, change data capture,
and eventual consistency mechanisms to synchronize data between transactional
and analytical databases while maintaining high availability and reliability.
"""
import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Tuple, Set, AsyncGenerator
from uuid import UUID, uuid4

import aiofiles
import duckdb
from sqlalchemy import text, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, SQLModel

from app.core.config import settings
from app.core.database import AsyncSessionLocal, sync_engine


# Logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SyncStrategy(str, Enum):
    """Data synchronization strategies"""
    REAL_TIME = "real_time"          # Immediate sync (<100ms)
    NEAR_REAL_TIME = "near_real_time"  # Batch sync (5-min intervals)
    BATCH = "batch"                  # Scheduled sync (hourly/daily)
    RECOVERY = "recovery"            # Full recovery synchronization
    INCREMENTAL = "incremental"      # Only changed records since last sync


class ConsistencyLevel(str, Enum):
    """Data consistency level requirements"""
    STRONG = "strong"                # Synchronous dual-write
    EVENTUAL = "eventual"            # Asynchronous sync
    WEAK = "weak"                    # Best-effort sync


class SyncOperationType(str, Enum):
    """Types of synchronization operations"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BULK_INSERT = "bulk_insert"
    BULK_UPDATE = "bulk_update"
    BULK_DELETE = "bulk_delete"


class SyncStatus(str, Enum):
    """Synchronization operation status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    COMPENSATED = "compensated"      # Rolled back due to failure


@dataclass
class SyncOperation:
    """Represents a single synchronization operation"""
    operation_id: str
    operation_type: SyncOperationType
    table_name: str
    primary_key: Any
    data: Dict[str, Any]
    consistency_level: ConsistencyLevel = ConsistencyLevel.EVENTUAL
    strategy: SyncStrategy = SyncStrategy.NEAR_REAL_TIME
    retry_count: int = 0
    max_retries: int = 3
    status: SyncStatus = SyncStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    postgresql_success: bool = False
    duckdb_success: bool = False


@dataclass
class SyncMetrics:
    """Synchronization performance metrics"""
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    average_latency_ms: float = 0.0
    sync_lag_seconds: float = 0.0
    queue_depth: int = 0
    last_sync_timestamp: Optional[datetime] = None
    consistency_score: float = 100.0  # Percentage (0-100)


class CircuitBreakerState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker for service protection"""
    name: str
    failure_threshold: int = 5
    recovery_timeout: int = 300  # seconds
    failure_count: int = 0
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    last_failure_time: Optional[datetime] = None
    
    def should_allow_request(self) -> bool:
        """Check if request should be allowed based on circuit breaker state"""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if (datetime.utcnow() - self.last_failure_time).seconds > self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
    
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN


class DatabaseAdapter(ABC):
    """Abstract base class for database adapters"""
    
    @abstractmethod
    async def execute_operation(self, operation: SyncOperation) -> bool:
        """Execute a sync operation on the target database"""
        pass
    
    @abstractmethod
    async def validate_consistency(self, table_name: str, primary_key: Any, expected_hash: str) -> bool:
        """Validate data consistency by comparing record hashes"""
        pass
    
    @abstractmethod
    async def get_health_status(self) -> Dict[str, Any]:
        """Get database health status"""
        pass


class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL database adapter for transactional operations"""
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker("postgresql", failure_threshold=3, recovery_timeout=30)
    
    async def execute_operation(self, operation: SyncOperation) -> bool:
        """Execute sync operation on PostgreSQL"""
        if not self.circuit_breaker.should_allow_request():
            logger.warning(f"PostgreSQL circuit breaker OPEN - blocking operation {operation.operation_id}")
            return False
        
        try:
            async with AsyncSessionLocal() as session:
                if operation.operation_type == SyncOperationType.CREATE:
                    result = await self._execute_create(session, operation)
                elif operation.operation_type == SyncOperationType.UPDATE:
                    result = await self._execute_update(session, operation)
                elif operation.operation_type == SyncOperationType.DELETE:
                    result = await self._execute_delete(session, operation)
                else:
                    result = await self._execute_bulk_operation(session, operation)
                
                await session.commit()
                self.circuit_breaker.record_success()
                return result
                
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"PostgreSQL operation failed: {str(e)}", exc_info=True)
            operation.error_message = str(e)
            return False
    
    async def _execute_create(self, session: AsyncSession, operation: SyncOperation) -> bool:
        """Execute CREATE operation"""
        # This is a simplified implementation - would need model-specific logic
        query = text(f"INSERT INTO {operation.table_name} (data) VALUES (:data)")
        await session.execute(query, {"data": json.dumps(operation.data)})
        return True
    
    async def _execute_update(self, session: AsyncSession, operation: SyncOperation) -> bool:
        """Execute UPDATE operation"""
        # This is a simplified implementation - would need model-specific logic
        query = text(f"UPDATE {operation.table_name} SET data = :data WHERE id = :pk")
        result = await session.execute(query, {"data": json.dumps(operation.data), "pk": operation.primary_key})
        return result.rowcount > 0
    
    async def _execute_delete(self, session: AsyncSession, operation: SyncOperation) -> bool:
        """Execute DELETE operation"""
        query = text(f"DELETE FROM {operation.table_name} WHERE id = :pk")
        result = await session.execute(query, {"pk": operation.primary_key})
        return result.rowcount > 0
    
    async def _execute_bulk_operation(self, session: AsyncSession, operation: SyncOperation) -> bool:
        """Execute bulk operations"""
        # Simplified bulk operation - would need specific implementation per operation type
        return True
    
    async def validate_consistency(self, table_name: str, primary_key: Any, expected_hash: str) -> bool:
        """Validate record consistency using hash comparison"""
        try:
            async with AsyncSessionLocal() as session:
                # Get record data and compute hash
                query = text(f"SELECT * FROM {table_name} WHERE id = :pk")
                result = await session.execute(query, {"pk": primary_key})
                record = result.first()
                
                if not record:
                    return False
                
                # Compute hash of record data
                record_dict = dict(record._mapping)
                record_json = json.dumps(record_dict, sort_keys=True, default=str)
                computed_hash = hashlib.sha256(record_json.encode()).hexdigest()
                
                return computed_hash == expected_hash
                
        except Exception as e:
            logger.error(f"Consistency validation failed: {str(e)}")
            return False
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get PostgreSQL health status"""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(text("SELECT 1"))
                return {
                    "status": "healthy",
                    "circuit_breaker": self.circuit_breaker.state.value,
                    "connection": "ok",
                    "response_time_ms": 0  # Would measure actual response time
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "circuit_breaker": self.circuit_breaker.state.value
            }


class DuckDBAdapter(DatabaseAdapter):
    """DuckDB database adapter for analytical operations"""
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker("duckdb", failure_threshold=5, recovery_timeout=60)
        self._connection_pool: Dict[str, duckdb.DuckDBPyConnection] = {}
    
    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get or create DuckDB connection"""
        thread_id = str(asyncio.current_task())
        if thread_id not in self._connection_pool:
            conn = duckdb.connect(settings.DUCKDB_DATABASE_PATH)
            
            # Configure DuckDB settings
            conn.execute(f"SET memory_limit='{settings.DUCKDB_MEMORY_LIMIT}'")
            conn.execute(f"SET threads TO {settings.DUCKDB_WORKER_THREADS}")
            conn.execute(f"SET temp_directory='{settings.DUCKDB_TEMP_DIRECTORY}'")
            
            # Install and load necessary extensions
            if settings.DUCKDB_ENABLE_S3:
                conn.execute("INSTALL httpfs; LOAD httpfs;")
            
            self._connection_pool[thread_id] = conn
        
        return self._connection_pool[thread_id]
    
    async def execute_operation(self, operation: SyncOperation) -> bool:
        """Execute sync operation on DuckDB"""
        if not self.circuit_breaker.should_allow_request():
            logger.warning(f"DuckDB circuit breaker OPEN - blocking operation {operation.operation_id}")
            return False
        
        try:
            conn = self._get_connection()
            
            if operation.operation_type == SyncOperationType.CREATE:
                result = await self._execute_create(conn, operation)
            elif operation.operation_type == SyncOperationType.UPDATE:
                result = await self._execute_update(conn, operation)
            elif operation.operation_type == SyncOperationType.DELETE:
                result = await self._execute_delete(conn, operation)
            else:
                result = await self._execute_bulk_operation(conn, operation)
            
            self.circuit_breaker.record_success()
            return result
            
        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"DuckDB operation failed: {str(e)}", exc_info=True)
            operation.error_message = str(e)
            return False
    
    async def _execute_create(self, conn: duckdb.DuckDBPyConnection, operation: SyncOperation) -> bool:
        """Execute CREATE operation on DuckDB"""
        # Convert data to Parquet-friendly format
        parquet_path = f"{settings.PARQUET_STORAGE_PATH}/{operation.table_name}"
        
        # Create table if not exists (simplified)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {operation.table_name} AS 
            SELECT * FROM read_parquet('{parquet_path}/*.parquet') 
            WHERE 1=0
        """)
        
        # Insert data (simplified - would need proper schema mapping)
        conn.execute(f"INSERT INTO {operation.table_name} VALUES (?)", [operation.data])
        return True
    
    async def _execute_update(self, conn: duckdb.DuckDBPyConnection, operation: SyncOperation) -> bool:
        """Execute UPDATE operation on DuckDB"""
        # Simplified UPDATE operation
        conn.execute(f"""
            UPDATE {operation.table_name} 
            SET data = ? 
            WHERE id = ?
        """, [json.dumps(operation.data), operation.primary_key])
        return True
    
    async def _execute_delete(self, conn: duckdb.DuckDBPyConnection, operation: SyncOperation) -> bool:
        """Execute DELETE operation on DuckDB"""
        conn.execute(f"DELETE FROM {operation.table_name} WHERE id = ?", [operation.primary_key])
        return True
    
    async def _execute_bulk_operation(self, conn: duckdb.DuckDBPyConnection, operation: SyncOperation) -> bool:
        """Execute bulk operations on DuckDB"""
        # Simplified bulk operation implementation
        return True
    
    async def validate_consistency(self, table_name: str, primary_key: Any, expected_hash: str) -> bool:
        """Validate record consistency in DuckDB"""
        try:
            conn = self._get_connection()
            result = conn.execute(f"SELECT * FROM {table_name} WHERE id = ?", [primary_key]).fetchone()
            
            if not result:
                return False
            
            # Compute hash of record data
            record_dict = dict(zip([col[0] for col in conn.description], result))
            record_json = json.dumps(record_dict, sort_keys=True, default=str)
            computed_hash = hashlib.sha256(record_json.encode()).hexdigest()
            
            return computed_hash == expected_hash
            
        except Exception as e:
            logger.error(f"DuckDB consistency validation failed: {str(e)}")
            return False
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get DuckDB health status"""
        try:
            conn = self._get_connection()
            conn.execute("SELECT 1")
            return {
                "status": "healthy",
                "circuit_breaker": self.circuit_breaker.state.value,
                "connection": "ok",
                "database_path": settings.DUCKDB_DATABASE_PATH,
                "memory_limit": settings.DUCKDB_MEMORY_LIMIT
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "circuit_breaker": self.circuit_breaker.state.value
            }


class DataSyncService:
    """
    Comprehensive data synchronization service for maintaining consistency
    between PostgreSQL (OLTP) and DuckDB (OLAP) databases.
    
    Features:
    - Dual-write patterns with circuit breakers
    - Multiple consistency levels and sync strategies  
    - Automatic failure recovery and compensation
    - Performance monitoring and metrics
    - Change data capture integration
    """
    
    def __init__(self):
        self.postgresql_adapter = PostgreSQLAdapter()
        self.duckdb_adapter = DuckDBAdapter()
        
        # Operation queues by priority/strategy
        self.real_time_queue: asyncio.Queue = asyncio.Queue()
        self.near_real_time_queue: asyncio.Queue = asyncio.Queue()
        self.batch_queue: asyncio.Queue = asyncio.Queue()
        self.recovery_queue: asyncio.Queue = asyncio.Queue()
        
        # Dead letter queue for persistent failures
        self.dead_letter_queue: List[SyncOperation] = []
        
        # Metrics and monitoring
        self.metrics = SyncMetrics()
        self.operation_history: Dict[str, SyncOperation] = {}
        
        # Background task handles
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
        
    async def initialize(self) -> None:
        """Initialize the sync service and start background workers"""
        logger.info("Initializing DataSyncService...")
        
        # Start background worker tasks
        self._background_tasks.add(asyncio.create_task(self._real_time_worker()))
        self._background_tasks.add(asyncio.create_task(self._near_real_time_worker()))
        self._background_tasks.add(asyncio.create_task(self._batch_worker()))
        self._background_tasks.add(asyncio.create_task(self._recovery_worker()))
        self._background_tasks.add(asyncio.create_task(self._metrics_collector()))
        
        logger.info("DataSyncService initialized successfully")
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the sync service"""
        logger.info("Shutting down DataSyncService...")
        
        # Signal shutdown to background workers
        self._shutdown_event.set()
        
        # Wait for all background tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        logger.info("DataSyncService shutdown completed")
    
    async def dual_write_create(
        self,
        table_name: str,
        data: Dict[str, Any],
        consistency_level: ConsistencyLevel = ConsistencyLevel.EVENTUAL,
        strategy: SyncStrategy = SyncStrategy.NEAR_REAL_TIME
    ) -> Tuple[bool, str]:
        """
        Create record with dual-write pattern
        
        Returns:
            Tuple of (success, operation_id)
        """
        operation_id = str(uuid4())
        operation = SyncOperation(
            operation_id=operation_id,
            operation_type=SyncOperationType.CREATE,
            table_name=table_name,
            primary_key=data.get('id'),
            data=data,
            consistency_level=consistency_level,
            strategy=strategy
        )
        
        # For strong consistency, execute synchronously
        if consistency_level == ConsistencyLevel.STRONG:
            return await self._execute_dual_write_sync(operation)
        
        # For eventual/weak consistency, queue for async processing
        await self._queue_operation(operation)
        return True, operation_id
    
    async def dual_write_update(
        self,
        table_name: str,
        primary_key: Any,
        data: Dict[str, Any],
        consistency_level: ConsistencyLevel = ConsistencyLevel.EVENTUAL,
        strategy: SyncStrategy = SyncStrategy.NEAR_REAL_TIME
    ) -> Tuple[bool, str]:
        """Update record with dual-write pattern"""
        operation_id = str(uuid4())
        operation = SyncOperation(
            operation_id=operation_id,
            operation_type=SyncOperationType.UPDATE,
            table_name=table_name,
            primary_key=primary_key,
            data=data,
            consistency_level=consistency_level,
            strategy=strategy
        )
        
        if consistency_level == ConsistencyLevel.STRONG:
            return await self._execute_dual_write_sync(operation)
        
        await self._queue_operation(operation)
        return True, operation_id
    
    async def dual_write_delete(
        self,
        table_name: str,
        primary_key: Any,
        consistency_level: ConsistencyLevel = ConsistencyLevel.EVENTUAL,
        strategy: SyncStrategy = SyncStrategy.NEAR_REAL_TIME
    ) -> Tuple[bool, str]:
        """Delete record with dual-write pattern"""
        operation_id = str(uuid4())
        operation = SyncOperation(
            operation_id=operation_id,
            operation_type=SyncOperationType.DELETE,
            table_name=table_name,
            primary_key=primary_key,
            data={},
            consistency_level=consistency_level,
            strategy=strategy
        )
        
        if consistency_level == ConsistencyLevel.STRONG:
            return await self._execute_dual_write_sync(operation)
        
        await self._queue_operation(operation)
        return True, operation_id
    
    async def _execute_dual_write_sync(self, operation: SyncOperation) -> Tuple[bool, str]:
        """Execute synchronous dual-write operation"""
        operation.status = SyncStatus.IN_PROGRESS
        start_time = datetime.utcnow()
        
        try:
            # Execute on PostgreSQL first (primary database)
            postgresql_success = await self.postgresql_adapter.execute_operation(operation)
            operation.postgresql_success = postgresql_success
            
            if not postgresql_success:
                operation.status = SyncStatus.FAILED
                return False, operation.operation_id
            
            # Execute on DuckDB (analytical database)
            duckdb_success = await self.duckdb_adapter.execute_operation(operation)
            operation.duckdb_success = duckdb_success
            
            if duckdb_success:
                operation.status = SyncStatus.COMPLETED
                success = True
            else:
                # PostgreSQL succeeded but DuckDB failed - queue for retry
                operation.status = SyncStatus.FAILED
                await self._queue_operation(operation)  # Retry async
                success = True  # Don't fail the primary operation
            
            # Update metrics
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            self._update_metrics(operation, latency_ms)
            
            return success, operation.operation_id
            
        except Exception as e:
            logger.error(f"Dual-write sync operation failed: {str(e)}", exc_info=True)
            operation.status = SyncStatus.FAILED
            operation.error_message = str(e)
            return False, operation.operation_id
    
    async def _queue_operation(self, operation: SyncOperation) -> None:
        """Queue operation based on strategy"""
        self.operation_history[operation.operation_id] = operation
        
        if operation.strategy == SyncStrategy.REAL_TIME:
            await self.real_time_queue.put(operation)
        elif operation.strategy == SyncStrategy.NEAR_REAL_TIME:
            await self.near_real_time_queue.put(operation)
        elif operation.strategy == SyncStrategy.BATCH:
            await self.batch_queue.put(operation)
        elif operation.strategy == SyncStrategy.RECOVERY:
            await self.recovery_queue.put(operation)
    
    async def _real_time_worker(self) -> None:
        """Background worker for real-time operations (<100ms target)"""
        logger.info("Real-time sync worker started")
        
        while not self._shutdown_event.is_set():
            try:
                # Use timeout to allow periodic shutdown checks
                operation = await asyncio.wait_for(
                    self.real_time_queue.get(), timeout=1.0
                )
                await self._process_operation(operation)
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue loop
            except Exception as e:
                logger.error(f"Real-time worker error: {str(e)}", exc_info=True)
        
        logger.info("Real-time sync worker stopped")
    
    async def _near_real_time_worker(self) -> None:
        """Background worker for near-real-time operations (5-min batches)"""
        logger.info("Near-real-time sync worker started")
        batch_operations = []
        last_batch_time = datetime.utcnow()
        
        while not self._shutdown_event.is_set():
            try:
                # Collect operations for batching
                try:
                    operation = await asyncio.wait_for(
                        self.near_real_time_queue.get(), timeout=1.0
                    )
                    batch_operations.append(operation)
                except asyncio.TimeoutError:
                    pass  # Normal timeout
                
                # Process batch if time elapsed or batch size reached
                now = datetime.utcnow()
                batch_size_threshold = settings.DATA_SYNC_BATCH_SIZE // 10  # Smaller batches for near-real-time
                
                if (batch_operations and 
                    ((now - last_batch_time).seconds >= 300 or  # 5 minutes
                     len(batch_operations) >= batch_size_threshold)):
                    
                    await self._process_batch(batch_operations)
                    batch_operations.clear()
                    last_batch_time = now
                    
            except Exception as e:
                logger.error(f"Near-real-time worker error: {str(e)}", exc_info=True)
        
        # Process remaining operations on shutdown
        if batch_operations:
            await self._process_batch(batch_operations)
        
        logger.info("Near-real-time sync worker stopped")
    
    async def _batch_worker(self) -> None:
        """Background worker for batch operations (scheduled intervals)"""
        logger.info("Batch sync worker started")
        
        while not self._shutdown_event.is_set():
            try:
                # Wait for batch processing interval
                await asyncio.sleep(settings.DATA_SYNC_INTERVAL)
                
                # Collect batch operations
                batch_operations = []
                batch_size = settings.DATA_SYNC_BATCH_SIZE
                
                for _ in range(batch_size):
                    try:
                        operation = self.batch_queue.get_nowait()
                        batch_operations.append(operation)
                    except asyncio.QueueEmpty:
                        break
                
                if batch_operations:
                    await self._process_batch(batch_operations)
                    
            except Exception as e:
                logger.error(f"Batch worker error: {str(e)}", exc_info=True)
        
        logger.info("Batch sync worker stopped")
    
    async def _recovery_worker(self) -> None:
        """Background worker for recovery operations"""
        logger.info("Recovery sync worker started")
        
        while not self._shutdown_event.is_set():
            try:
                operation = await asyncio.wait_for(
                    self.recovery_queue.get(), timeout=5.0
                )
                
                # Recovery operations get special handling
                await self._process_recovery_operation(operation)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Recovery worker error: {str(e)}", exc_info=True)
        
        logger.info("Recovery sync worker stopped")
    
    async def _process_operation(self, operation: SyncOperation) -> None:
        """Process a single sync operation"""
        operation.status = SyncStatus.IN_PROGRESS
        start_time = datetime.utcnow()
        
        try:
            # Execute on both databases
            postgresql_result = await self.postgresql_adapter.execute_operation(operation)
            duckdb_result = await self.duckdb_adapter.execute_operation(operation)
            
            operation.postgresql_success = postgresql_result
            operation.duckdb_success = duckdb_result
            
            if postgresql_result and duckdb_result:
                operation.status = SyncStatus.COMPLETED
            else:
                await self._handle_partial_failure(operation)
            
            # Update metrics
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            self._update_metrics(operation, latency_ms)
            
        except Exception as e:
            logger.error(f"Operation processing failed: {str(e)}", exc_info=True)
            operation.status = SyncStatus.FAILED
            operation.error_message = str(e)
            await self._handle_operation_failure(operation)
    
    async def _process_batch(self, operations: List[SyncOperation]) -> None:
        """Process a batch of sync operations"""
        logger.info(f"Processing batch of {len(operations)} operations")
        
        # Process operations concurrently with limited concurrency
        semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_BATCHES)
        
        async def process_with_semaphore(op):
            async with semaphore:
                await self._process_operation(op)
        
        await asyncio.gather(
            *[process_with_semaphore(op) for op in operations],
            return_exceptions=True
        )
    
    async def _process_recovery_operation(self, operation: SyncOperation) -> None:
        """Process recovery operation with enhanced error handling"""
        max_retries = operation.max_retries * 2  # Extra retries for recovery
        
        for attempt in range(max_retries):
            try:
                await self._process_operation(operation)
                
                if operation.status == SyncStatus.COMPLETED:
                    return
                
                # Wait before retry with exponential backoff
                wait_time = min(300, 2 ** attempt * 5)  # Max 5 minutes
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Recovery attempt {attempt + 1} failed: {str(e)}")
        
        # After all retries failed, move to dead letter queue
        self.dead_letter_queue.append(operation)
        operation.status = SyncStatus.FAILED
        logger.error(f"Operation {operation.operation_id} moved to dead letter queue after recovery failure")
    
    async def _handle_partial_failure(self, operation: SyncOperation) -> None:
        """Handle cases where operation succeeded on one database but failed on another"""
        if operation.postgresql_success and not operation.duckdb_success:
            # Primary succeeded, analytical failed - queue for retry
            operation.retry_count += 1
            if operation.retry_count <= operation.max_retries:
                operation.status = SyncStatus.RETRYING
                await asyncio.sleep(settings.SYNC_RETRY_DELAY)
                await self._queue_operation(operation)
            else:
                operation.status = SyncStatus.FAILED
                logger.error(f"Operation {operation.operation_id} failed after max retries on DuckDB")
        
        elif not operation.postgresql_success and operation.duckdb_success:
            # Analytical succeeded, primary failed - this shouldn't happen in normal flow
            # Need to compensate by rolling back DuckDB operation
            await self._compensate_operation(operation)
        
        else:
            # Both failed
            operation.status = SyncStatus.FAILED
            await self._handle_operation_failure(operation)
    
    async def _compensate_operation(self, operation: SyncOperation) -> None:
        """Compensate for partial failure by rolling back successful operations"""
        operation.status = SyncStatus.COMPENSATED
        
        try:
            # Create compensating operation (reverse of original)
            if operation.operation_type == SyncOperationType.CREATE:
                compensating_op = SyncOperation(
                    operation_id=f"{operation.operation_id}_compensate",
                    operation_type=SyncOperationType.DELETE,
                    table_name=operation.table_name,
                    primary_key=operation.primary_key,
                    data={}
                )
            elif operation.operation_type == SyncOperationType.DELETE:
                compensating_op = SyncOperation(
                    operation_id=f"{operation.operation_id}_compensate",
                    operation_type=SyncOperationType.CREATE,
                    table_name=operation.table_name,
                    primary_key=operation.primary_key,
                    data=operation.data
                )
            else:  # UPDATE - would need to fetch original data
                logger.warning(f"Cannot compensate UPDATE operation {operation.operation_id}")
                return
            
            # Execute compensation only on DuckDB
            if operation.duckdb_success:
                await self.duckdb_adapter.execute_operation(compensating_op)
            
        except Exception as e:
            logger.error(f"Compensation failed for operation {operation.operation_id}: {str(e)}")
    
    async def _handle_operation_failure(self, operation: SyncOperation) -> None:
        """Handle completely failed operations"""
        operation.retry_count += 1
        
        if operation.retry_count <= operation.max_retries:
            # Retry with exponential backoff
            wait_time = min(300, 2 ** operation.retry_count * settings.SYNC_RETRY_DELAY)
            await asyncio.sleep(wait_time)
            operation.status = SyncStatus.RETRYING
            await self._queue_operation(operation)
        else:
            # Move to dead letter queue for manual intervention
            self.dead_letter_queue.append(operation)
            logger.error(f"Operation {operation.operation_id} moved to dead letter queue")
    
    def _update_metrics(self, operation: SyncOperation, latency_ms: float) -> None:
        """Update performance metrics"""
        self.metrics.total_operations += 1
        
        if operation.status == SyncStatus.COMPLETED:
            self.metrics.successful_operations += 1
        else:
            self.metrics.failed_operations += 1
        
        # Update average latency (simple moving average)
        total_ops = self.metrics.total_operations
        current_avg = self.metrics.average_latency_ms
        self.metrics.average_latency_ms = ((current_avg * (total_ops - 1)) + latency_ms) / total_ops
        
        # Update consistency score
        success_rate = (self.metrics.successful_operations / total_ops) * 100
        self.metrics.consistency_score = success_rate
        
        # Update last sync timestamp
        self.metrics.last_sync_timestamp = datetime.utcnow()
    
    async def _metrics_collector(self) -> None:
        """Background worker for collecting and updating metrics"""
        logger.info("Metrics collector started")
        
        while not self._shutdown_event.is_set():
            try:
                # Update queue depths
                self.metrics.queue_depth = (
                    self.real_time_queue.qsize() +
                    self.near_real_time_queue.qsize() +
                    self.batch_queue.qsize() +
                    self.recovery_queue.qsize()
                )
                
                # Calculate sync lag
                if self.metrics.last_sync_timestamp:
                    lag = (datetime.utcnow() - self.metrics.last_sync_timestamp).total_seconds()
                    self.metrics.sync_lag_seconds = lag
                
                # Wait before next collection
                await asyncio.sleep(30)  # Collect metrics every 30 seconds
                
            except Exception as e:
                logger.error(f"Metrics collector error: {str(e)}", exc_info=True)
        
        logger.info("Metrics collector stopped")
    
    async def get_sync_status(self) -> Dict[str, Any]:
        """Get comprehensive synchronization status"""
        postgresql_health = await self.postgresql_adapter.get_health_status()
        duckdb_health = await self.duckdb_adapter.get_health_status()
        
        return {
            "service_status": "running" if not self._shutdown_event.is_set() else "shutdown",
            "metrics": {
                "total_operations": self.metrics.total_operations,
                "successful_operations": self.metrics.successful_operations,
                "failed_operations": self.metrics.failed_operations,
                "success_rate_percent": (
                    (self.metrics.successful_operations / self.metrics.total_operations * 100)
                    if self.metrics.total_operations > 0 else 100.0
                ),
                "average_latency_ms": self.metrics.average_latency_ms,
                "sync_lag_seconds": self.metrics.sync_lag_seconds,
                "queue_depth": self.metrics.queue_depth,
                "consistency_score": self.metrics.consistency_score,
                "last_sync": self.metrics.last_sync_timestamp.isoformat() if self.metrics.last_sync_timestamp else None
            },
            "queue_status": {
                "real_time": self.real_time_queue.qsize(),
                "near_real_time": self.near_real_time_queue.qsize(),
                "batch": self.batch_queue.qsize(),
                "recovery": self.recovery_queue.qsize(),
                "dead_letter": len(self.dead_letter_queue)
            },
            "database_health": {
                "postgresql": postgresql_health,
                "duckdb": duckdb_health
            },
            "background_workers": len(self._background_tasks),
            "configuration": {
                "batch_size": settings.DATA_SYNC_BATCH_SIZE,
                "sync_interval": settings.DATA_SYNC_INTERVAL,
                "dual_write_enabled": settings.ENABLE_DUAL_WRITE,
                "retry_attempts": settings.SYNC_RETRY_ATTEMPTS
            }
        }
    
    async def validate_consistency(self, table_name: str, primary_key: Any) -> Dict[str, Any]:
        """Validate data consistency between PostgreSQL and DuckDB"""
        # Get data from PostgreSQL and compute hash
        async with AsyncSessionLocal() as session:
            query = text(f"SELECT * FROM {table_name} WHERE id = :pk")
            result = await session.execute(query, {"pk": primary_key})
            pg_record = result.first()
        
        if not pg_record:
            return {"status": "not_found", "database": "postgresql"}
        
        # Compute PostgreSQL record hash
        pg_dict = dict(pg_record._mapping)
        pg_json = json.dumps(pg_dict, sort_keys=True, default=str)
        pg_hash = hashlib.sha256(pg_json.encode()).hexdigest()
        
        # Validate against both databases
        pg_valid = await self.postgresql_adapter.validate_consistency(table_name, primary_key, pg_hash)
        duckdb_valid = await self.duckdb_adapter.validate_consistency(table_name, primary_key, pg_hash)
        
        return {
            "status": "consistent" if pg_valid and duckdb_valid else "inconsistent",
            "postgresql_valid": pg_valid,
            "duckdb_valid": duckdb_valid,
            "data_hash": pg_hash,
            "checked_at": datetime.utcnow().isoformat()
        }
    
    async def sync_from_postgresql(
        self,
        table_name: str,
        since: Optional[datetime] = None,
        batch_size: int = None
    ) -> Dict[str, Any]:
        """Full synchronization from PostgreSQL to DuckDB"""
        if batch_size is None:
            batch_size = settings.DATA_SYNC_BATCH_SIZE
        
        sync_start = datetime.utcnow()
        total_synced = 0
        
        try:
            async with AsyncSessionLocal() as session:
                # Build query with optional timestamp filter
                base_query = f"SELECT * FROM {table_name}"
                if since:
                    base_query += " WHERE updated_at > :since"
                    params = {"since": since}
                else:
                    params = {}
                
                base_query += " ORDER BY id"
                
                # Process in batches
                offset = 0
                while True:
                    query = text(f"{base_query} LIMIT :limit OFFSET :offset")
                    params.update({"limit": batch_size, "offset": offset})
                    
                    result = await session.execute(query, params)
                    records = result.fetchall()
                    
                    if not records:
                        break
                    
                    # Create sync operations for batch
                    operations = []
                    for record in records:
                        record_dict = dict(record._mapping)
                        operation = SyncOperation(
                            operation_id=str(uuid4()),
                            operation_type=SyncOperationType.CREATE,  # Or UPDATE based on existence
                            table_name=table_name,
                            primary_key=record_dict.get('id'),
                            data=record_dict,
                            strategy=SyncStrategy.BATCH
                        )
                        operations.append(operation)
                    
                    # Process batch
                    await self._process_batch(operations)
                    total_synced += len(operations)
                    offset += batch_size
                    
                    logger.info(f"Synced {total_synced} records from {table_name}")
        
        except Exception as e:
            logger.error(f"Full sync failed for {table_name}: {str(e)}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "records_synced": total_synced,
                "duration_seconds": (datetime.utcnow() - sync_start).total_seconds()
            }
        
        return {
            "status": "completed",
            "records_synced": total_synced,
            "duration_seconds": (datetime.utcnow() - sync_start).total_seconds(),
            "started_at": sync_start.isoformat(),
            "completed_at": datetime.utcnow().isoformat()
        }
    
    async def handle_sync_failure(self, operation_id: str) -> bool:
        """Handle specific sync failure with recovery options"""
        operation = self.operation_history.get(operation_id)
        if not operation:
            logger.error(f"Operation {operation_id} not found in history")
            return False
        
        # Move to recovery queue for special handling
        operation.strategy = SyncStrategy.RECOVERY
        await self.recovery_queue.put(operation)
        
        logger.info(f"Operation {operation_id} queued for recovery")
        return True
    
    def get_dead_letter_operations(self) -> List[Dict[str, Any]]:
        """Get operations that failed persistently and need manual intervention"""
        return [
            {
                "operation_id": op.operation_id,
                "operation_type": op.operation_type.value,
                "table_name": op.table_name,
                "primary_key": op.primary_key,
                "retry_count": op.retry_count,
                "error_message": op.error_message,
                "created_at": op.created_at.isoformat(),
                "updated_at": op.updated_at.isoformat()
            }
            for op in self.dead_letter_queue
        ]
    
    async def retry_dead_letter_operation(self, operation_id: str) -> bool:
        """Retry a specific dead letter operation"""
        operation = next((op for op in self.dead_letter_queue if op.operation_id == operation_id), None)
        if not operation:
            return False
        
        # Reset operation state and move to recovery queue
        operation.retry_count = 0
        operation.status = SyncStatus.PENDING
        operation.error_message = None
        operation.strategy = SyncStrategy.RECOVERY
        
        # Remove from dead letter queue
        self.dead_letter_queue.remove(operation)
        
        # Queue for recovery
        await self.recovery_queue.put(operation)
        
        logger.info(f"Dead letter operation {operation_id} queued for retry")
        return True


# Global service instance
data_sync_service = DataSyncService()


@asynccontextmanager
async def get_data_sync_service() -> AsyncGenerator[DataSyncService, None]:
    """Async context manager for data sync service"""
    try:
        yield data_sync_service
    except Exception as e:
        logger.error(f"DataSync service error: {str(e)}", exc_info=True)
        raise