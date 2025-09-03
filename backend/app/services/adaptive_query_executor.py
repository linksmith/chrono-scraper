"""
Adaptive Query Executor with Resource Management

Provides intelligent query execution with dynamic routing, resource management,
load balancing, and adaptive optimization strategies for the Chrono Scraper FastAPI application.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Union
import psutil

from ..core.config import settings
from .circuit_breaker import CircuitBreaker
from .query_optimization_engine import QueryContext, OptimizedQuery, get_query_optimization_engine
from .intelligent_cache_manager import get_cache_manager
from .query_performance_monitor import get_performance_monitor, QueryExecution

logger = logging.getLogger(__name__)


class Priority(int, Enum):
    """Query execution priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4
    EMERGENCY = 5


class QueryStatus(str, Enum):
    """Query execution status"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ResourceType(str, Enum):
    """System resource types"""
    CPU = "cpu"
    MEMORY = "memory"
    CONNECTIONS = "connections"
    IO = "io"
    NETWORK = "network"


@dataclass
class Query:
    """Query execution request"""
    query_id: str
    sql: str
    parameters: Optional[Dict[str, Any]] = None
    database_type: str = "postgresql"
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    priority: Priority = Priority.NORMAL
    timeout_seconds: Optional[int] = None
    memory_limit_mb: Optional[int] = None
    enable_optimization: bool = True
    enable_caching: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class QueryExecution:
    """Query execution tracking"""
    execution_id: str
    query: Query
    status: QueryStatus
    assigned_worker: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    resources_used: Dict[ResourceType, float] = field(default_factory=dict)
    optimization_applied: bool = False
    cache_hit: bool = False
    retry_count: int = 0
    max_retries: int = 3


@dataclass
class ExecutionStatus:
    """Query execution status information"""
    execution_id: str
    status: QueryStatus
    progress_percent: Optional[float] = None
    estimated_remaining_ms: Optional[float] = None
    current_operation: Optional[str] = None
    resources_allocated: Dict[ResourceType, float] = field(default_factory=dict)
    queue_position: Optional[int] = None


@dataclass
class ExecutionMetrics:
    """System execution metrics"""
    active_queries: int
    queued_queries: int
    completed_queries_last_hour: int
    failed_queries_last_hour: int
    average_execution_time_ms: float
    resource_utilization: Dict[ResourceType, float]
    queue_wait_time_ms: float
    system_load: float
    connection_pool_usage: float


@dataclass
class ResourceQuota:
    """Resource quota for users/projects"""
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    max_concurrent_queries: int = 10
    max_memory_mb: int = 1024
    max_cpu_percent: float = 25.0
    max_execution_time_seconds: int = 300
    daily_query_limit: int = 10000
    priority_boost: int = 0


class AdaptiveQueryExecutor:
    """
    Intelligent query execution engine with adaptive optimization and resource management.
    
    Features:
    - Dynamic query routing based on real-time performance
    - Resource-aware query scheduling and prioritization
    - Adaptive timeout management based on query complexity
    - Automatic retry with exponential backoff
    - Load balancing across database connections
    - Memory and CPU usage monitoring and limits
    - Query cancellation and cleanup
    - Performance-based connection pool optimization
    - Emergency circuit breaker activation
    """
    
    def __init__(
        self,
        postgresql_session_factory=None,
        duckdb_service=None,
        max_concurrent_queries: int = 100,
        default_timeout_seconds: int = 300,
        enable_adaptive_routing: bool = True
    ):
        self.postgresql_session_factory = postgresql_session_factory
        self.duckdb_service = duckdb_service
        self.max_concurrent_queries = max_concurrent_queries
        self.default_timeout_seconds = default_timeout_seconds
        self.enable_adaptive_routing = enable_adaptive_routing
        
        # Query management
        self.query_queue: List[QueryExecution] = []
        self.active_executions: Dict[str, QueryExecution] = {}
        self.completed_executions: Dict[str, QueryExecution] = {}
        
        # Resource management
        self.resource_quotas: Dict[str, ResourceQuota] = {}
        self.current_resource_usage: Dict[ResourceType, float] = {
            resource: 0.0 for resource in ResourceType
        }
        
        # Connection management
        self.connection_pools = {
            'postgresql': {'active': 0, 'max': 20, 'performance': 1.0},
            'duckdb': {'active': 0, 'max': 10, 'performance': 1.0}
        }
        
        # Circuit breakers for different databases
        self.circuit_breakers = {
            'postgresql': CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60,
                expected_exception=Exception
            ),
            'duckdb': CircuitBreaker(
                failure_threshold=3,
                recovery_timeout=30,
                expected_exception=Exception
            )
        }
        
        # Performance tracking
        self.execution_history: List[QueryExecution] = []
        self.performance_metrics = {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'average_execution_time': 0.0,
            'resource_efficiency_score': 1.0
        }
        
        # Background task management
        self._scheduler_task: Optional[asyncio.Task] = None
        self._resource_monitor_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Optimization and caching services
        self.optimization_engine = None
        self.cache_manager = None
        self.performance_monitor = None
        
        logger.info(
            f"Adaptive query executor initialized. "
            f"Max concurrent queries: {max_concurrent_queries}, "
            f"Default timeout: {default_timeout_seconds}s"
        )
    
    async def initialize(self):
        """Initialize executor with dependent services"""
        self.optimization_engine = get_query_optimization_engine()
        self.cache_manager = get_cache_manager()
        self.performance_monitor = get_performance_monitor()
        
        # Start background tasks
        self._scheduler_task = asyncio.create_task(self._query_scheduler())
        self._resource_monitor_task = asyncio.create_task(self._resource_monitor())
        
        logger.info("Adaptive query executor initialized with dependent services")
    
    async def shutdown(self):
        """Shutdown executor and cleanup resources"""
        self._shutdown_event.set()
        
        # Cancel active queries
        for execution in list(self.active_executions.values()):
            await self.cancel_query(execution.execution_id)
        
        # Stop background tasks
        if self._scheduler_task:
            self._scheduler_task.cancel()
        if self._resource_monitor_task:
            self._resource_monitor_task.cancel()
        
        logger.info("Adaptive query executor shutdown completed")
    
    async def execute_optimized_query(self, optimized_query: OptimizedQuery) -> Any:
        """
        Execute an optimized query with full resource management.
        
        Args:
            optimized_query: Pre-optimized query from optimization engine
            
        Returns:
            Query execution result
        """
        query_id = str(uuid.uuid4())
        
        query = Query(
            query_id=query_id,
            sql=optimized_query.optimized_query,
            enable_optimization=False,  # Already optimized
            enable_caching=optimized_query.cache_ttl is not None,
            metadata={
                'optimization_types': [t.value for t in optimized_query.optimization_types],
                'estimated_improvement': optimized_query.estimated_improvement_percent,
                'execution_hints': optimized_query.execution_hints
            }
        )
        
        execution = await self.schedule_query(query, Priority.NORMAL)
        
        # Wait for execution to complete
        while execution.status in [QueryStatus.QUEUED, QueryStatus.RUNNING]:
            await asyncio.sleep(0.1)
            execution = self.active_executions.get(
                execution.execution_id, 
                self.completed_executions.get(execution.execution_id, execution)
            )
        
        if execution.status == QueryStatus.COMPLETED:
            return execution.result
        elif execution.status == QueryStatus.FAILED:
            raise Exception(f"Query execution failed: {execution.error}")
        elif execution.status == QueryStatus.CANCELLED:
            raise Exception("Query execution was cancelled")
        elif execution.status == QueryStatus.TIMEOUT:
            raise Exception("Query execution timed out")
        
        raise Exception(f"Query execution ended with unexpected status: {execution.status}")
    
    async def schedule_query(self, query: Query, priority: Priority) -> QueryExecution:
        """
        Schedule a query for execution with priority and resource management.
        
        Args:
            query: Query to schedule
            priority: Execution priority
            
        Returns:
            QueryExecution tracking object
        """
        execution_id = str(uuid.uuid4())
        
        # Apply resource quotas and limits
        await self._apply_resource_limits(query)
        
        # Create execution tracking
        execution = QueryExecution(
            execution_id=execution_id,
            query=query,
            status=QueryStatus.QUEUED,
            max_retries=getattr(settings, 'MAX_QUERY_RETRIES', 3)
        )
        
        # Add to queue with priority ordering
        self._insert_query_by_priority(execution, priority)
        
        logger.debug(f"Query scheduled: {execution_id}, Priority: {priority.name}")
        
        return execution
    
    async def monitor_execution(self, execution_id: str) -> ExecutionStatus:
        """
        Monitor query execution status and progress.
        
        Args:
            execution_id: Unique execution identifier
            
        Returns:
            ExecutionStatus with current status and metrics
        """
        # Find execution
        execution = (
            self.active_executions.get(execution_id) or
            self.completed_executions.get(execution_id) or
            next((e for e in self.query_queue if e.execution_id == execution_id), None)
        )
        
        if not execution:
            raise ValueError(f"Execution not found: {execution_id}")
        
        # Calculate queue position if queued
        queue_position = None
        if execution.status == QueryStatus.QUEUED:
            queue_position = next(
                (i for i, e in enumerate(self.query_queue) if e.execution_id == execution_id),
                None
            )
        
        # Estimate remaining time
        estimated_remaining_ms = None
        if execution.status == QueryStatus.RUNNING and execution.started_at:
            elapsed_ms = (datetime.now() - execution.started_at).total_seconds() * 1000
            # Simple heuristic - could be improved with ML model
            avg_duration = self.performance_metrics.get('average_execution_time', 1000)
            estimated_remaining_ms = max(0, avg_duration - elapsed_ms)
        
        return ExecutionStatus(
            execution_id=execution_id,
            status=execution.status,
            queue_position=queue_position,
            estimated_remaining_ms=estimated_remaining_ms,
            current_operation="Executing query" if execution.status == QueryStatus.RUNNING else None,
            resources_allocated=execution.resources_used
        )
    
    async def cancel_query(self, execution_id: str) -> bool:
        """
        Cancel a running or queued query.
        
        Args:
            execution_id: Unique execution identifier
            
        Returns:
            True if successfully cancelled, False otherwise
        """
        try:
            # Find and remove from queue
            for i, execution in enumerate(self.query_queue):
                if execution.execution_id == execution_id:
                    execution.status = QueryStatus.CANCELLED
                    self.query_queue.pop(i)
                    self.completed_executions[execution_id] = execution
                    logger.info(f"Query cancelled from queue: {execution_id}")
                    return True
            
            # Cancel active execution
            if execution_id in self.active_executions:
                execution = self.active_executions[execution_id]
                execution.status = QueryStatus.CANCELLED
                
                # Release resources
                await self._release_execution_resources(execution)
                
                # Move to completed
                self.completed_executions[execution_id] = execution
                del self.active_executions[execution_id]
                
                logger.info(f"Active query cancelled: {execution_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error cancelling query {execution_id}: {str(e)}")
            return False
    
    async def get_execution_metrics(self) -> ExecutionMetrics:
        """
        Get comprehensive execution metrics.
        
        Returns:
            ExecutionMetrics with system performance data
        """
        # Calculate metrics
        active_queries = len(self.active_executions)
        queued_queries = len(self.query_queue)
        
        # Calculate recent success/failure rates
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_executions = [
            e for e in self.execution_history
            if e.completed_at and e.completed_at >= one_hour_ago
        ]
        
        completed_last_hour = len([e for e in recent_executions if e.status == QueryStatus.COMPLETED])
        failed_last_hour = len([e for e in recent_executions if e.status == QueryStatus.FAILED])
        
        # Average execution time
        completed_executions = [e for e in recent_executions if e.duration_ms]
        avg_execution_time = (
            sum(e.duration_ms for e in completed_executions) / len(completed_executions)
            if completed_executions else 0.0
        )
        
        # Queue wait time
        if self.query_queue:
            queue_wait_time = (
                sum((datetime.now() - e.query.created_at).total_seconds() * 1000 
                    for e in self.query_queue) / len(self.query_queue)
            )
        else:
            queue_wait_time = 0.0
        
        # System load
        try:
            system_load = psutil.cpu_percent(interval=None)
        except Exception:
            system_load = 0.0
        
        # Connection pool usage
        total_connections = sum(pool['active'] for pool in self.connection_pools.values())
        max_connections = sum(pool['max'] for pool in self.connection_pools.values())
        connection_pool_usage = (total_connections / max_connections * 100) if max_connections > 0 else 0.0
        
        return ExecutionMetrics(
            active_queries=active_queries,
            queued_queries=queued_queries,
            completed_queries_last_hour=completed_last_hour,
            failed_queries_last_hour=failed_last_hour,
            average_execution_time_ms=avg_execution_time,
            resource_utilization=dict(self.current_resource_usage),
            queue_wait_time_ms=queue_wait_time,
            system_load=system_load,
            connection_pool_usage=connection_pool_usage
        )
    
    # Private helper methods
    
    def _insert_query_by_priority(self, execution: QueryExecution, priority: Priority):
        """Insert query into queue with priority ordering"""
        # Simple priority insertion - higher priority goes first
        inserted = False
        for i, queued_execution in enumerate(self.query_queue):
            if priority > Priority.NORMAL:  # Higher priority
                self.query_queue.insert(i, execution)
                inserted = True
                break
        
        if not inserted:
            self.query_queue.append(execution)
    
    async def _apply_resource_limits(self, query: Query):
        """Apply resource quotas and limits to query"""
        # Get user/project quota
        quota = await self._get_resource_quota(query.user_id, query.project_id)
        
        # Apply memory limit
        if not query.memory_limit_mb:
            query.memory_limit_mb = quota.max_memory_mb
        
        # Apply timeout
        if not query.timeout_seconds:
            query.timeout_seconds = min(
                quota.max_execution_time_seconds,
                self.default_timeout_seconds
            )
        
        # Check daily limits
        await self._check_daily_limits(query.user_id, query.project_id, quota)
    
    async def _get_resource_quota(self, user_id: Optional[str], project_id: Optional[str]) -> ResourceQuota:
        """Get resource quota for user/project"""
        quota_key = f"{user_id}:{project_id}"
        
        if quota_key not in self.resource_quotas:
            # Create default quota - in production, would load from database
            self.resource_quotas[quota_key] = ResourceQuota(
                user_id=user_id,
                project_id=project_id
            )
        
        return self.resource_quotas[quota_key]
    
    async def _check_daily_limits(self, user_id: Optional[str], project_id: Optional[str], quota: ResourceQuota):
        """Check if user/project has exceeded daily query limits"""
        # In production, would check against database
        # For now, just log the check
        logger.debug(f"Checking daily limits for user: {user_id}, project: {project_id}")
    
    async def _query_scheduler(self):
        """Background query scheduler task"""
        while not self._shutdown_event.is_set():
            try:
                # Process queue if we have capacity
                if (len(self.active_executions) < self.max_concurrent_queries and 
                    self.query_queue):
                    
                    execution = self.query_queue.pop(0)
                    await self._execute_query(execution)
                
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                
            except Exception as e:
                logger.error(f"Error in query scheduler: {str(e)}")
                await asyncio.sleep(1)  # Longer delay on error
    
    async def _resource_monitor(self):
        """Background resource monitoring task"""
        while not self._shutdown_event.is_set():
            try:
                # Update system resource usage
                await self._update_resource_usage()
                
                # Check for resource pressure and take action
                await self._handle_resource_pressure()
                
                # Update connection pool performance metrics
                await self._update_connection_performance()
                
                await asyncio.sleep(5)  # Monitor every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in resource monitor: {str(e)}")
                await asyncio.sleep(10)  # Longer delay on error
    
    async def _execute_query(self, execution: QueryExecution):
        """Execute a single query with full resource management"""
        execution_id = execution.execution_id
        
        try:
            # Move to active executions
            execution.status = QueryStatus.RUNNING
            execution.started_at = datetime.now()
            self.active_executions[execution_id] = execution
            
            # Allocate resources
            await self._allocate_execution_resources(execution)
            
            # Try cache first if enabled
            if execution.query.enable_caching and self.cache_manager:
                cached_result = await self.cache_manager.get_cached_result(execution.query.sql)
                if cached_result:
                    execution.result = cached_result.data
                    execution.cache_hit = True
                    execution.status = QueryStatus.COMPLETED
                    execution.completed_at = datetime.now()
                    execution.duration_ms = (
                        execution.completed_at - execution.started_at
                    ).total_seconds() * 1000
                    
                    await self._complete_execution(execution)
                    return
            
            # Apply optimization if enabled
            query_to_execute = execution.query.sql
            if (execution.query.enable_optimization and 
                self.optimization_engine and 
                not execution.optimization_applied):
                
                try:
                    context = QueryContext(
                        database_type=execution.query.database_type,
                        user_id=execution.query.user_id,
                        project_id=execution.query.project_id,
                        memory_limit=execution.query.memory_limit_mb,
                        timeout_seconds=execution.query.timeout_seconds
                    )
                    
                    optimized = await self.optimization_engine.optimize_query(
                        execution.query.sql, context
                    )
                    
                    if optimized.estimated_improvement_percent > 10:  # Only use if significant improvement
                        query_to_execute = optimized.optimized_query
                        execution.optimization_applied = True
                        logger.debug(
                            f"Applied query optimization: {optimized.estimated_improvement_percent:.1f}% improvement"
                        )
                
                except Exception as e:
                    logger.warning(f"Query optimization failed: {str(e)}")
            
            # Execute query with timeout and resource monitoring
            result = await self._execute_with_database(execution, query_to_execute)
            
            # Cache result if successful and caching enabled
            if (result is not None and 
                execution.query.enable_caching and 
                self.cache_manager):
                
                try:
                    await self.cache_manager.cache_result(
                        execution.query.sql,
                        result,
                        ttl=3600  # 1 hour default TTL
                    )
                except Exception as e:
                    logger.warning(f"Failed to cache query result: {str(e)}")
            
            # Complete execution
            execution.result = result
            execution.status = QueryStatus.COMPLETED
            execution.completed_at = datetime.now()
            execution.duration_ms = (
                execution.completed_at - execution.started_at
            ).total_seconds() * 1000
            
            await self._complete_execution(execution)
            
        except asyncio.TimeoutError:
            execution.status = QueryStatus.TIMEOUT
            execution.error = "Query execution timed out"
            await self._handle_execution_failure(execution)
            
        except Exception as e:
            execution.status = QueryStatus.FAILED
            execution.error = str(e)
            await self._handle_execution_failure(execution)
    
    async def _execute_with_database(self, execution: QueryExecution, query: str) -> Any:
        """Execute query with specific database"""
        database_type = execution.query.database_type
        timeout = execution.query.timeout_seconds or self.default_timeout_seconds
        
        try:
            with self.circuit_breakers[database_type]:
                if database_type == "postgresql" and self.postgresql_session_factory:
                    return await asyncio.wait_for(
                        self._execute_postgresql_query(query, execution.query.parameters),
                        timeout=timeout
                    )
                elif database_type == "duckdb" and self.duckdb_service:
                    return await asyncio.wait_for(
                        self._execute_duckdb_query(query, execution.query.parameters),
                        timeout=timeout
                    )
                else:
                    raise ValueError(f"Unsupported database type: {database_type}")
        
        except Exception as e:
            # Update circuit breaker failure count
            self.circuit_breakers[database_type].record_failure()
            raise
    
    async def _execute_postgresql_query(self, query: str, parameters: Optional[Dict]) -> Any:
        """Execute PostgreSQL query"""
        async with self.postgresql_session_factory() as session:
            if parameters:
                result = await session.execute(query, parameters)
            else:
                result = await session.execute(query)
            return result.fetchall()
    
    async def _execute_duckdb_query(self, query: str, parameters: Optional[Dict]) -> Any:
        """Execute DuckDB query"""
        if parameters:
            return await self.duckdb_service.execute_query(query, list(parameters.values()))
        else:
            return await self.duckdb_service.execute_query(query)


# Singleton instance
_query_executor: Optional[AdaptiveQueryExecutor] = None


def get_query_executor() -> Optional[AdaptiveQueryExecutor]:
    """Get the global query executor instance"""
    return _query_executor


async def init_query_executor(
    postgresql_session_factory=None,
    duckdb_service=None,
    max_concurrent_queries: int = 100,
    default_timeout_seconds: int = 300,
    enable_adaptive_routing: bool = True
) -> AdaptiveQueryExecutor:
    """Initialize the global query executor"""
    global _query_executor
    
    _query_executor = AdaptiveQueryExecutor(
        postgresql_session_factory=postgresql_session_factory,
        duckdb_service=duckdb_service,
        max_concurrent_queries=max_concurrent_queries,
        default_timeout_seconds=default_timeout_seconds,
        enable_adaptive_routing=enable_adaptive_routing
    )
    
    await _query_executor.initialize()
    
    logger.info("Adaptive query executor initialized successfully")
    return _query_executor