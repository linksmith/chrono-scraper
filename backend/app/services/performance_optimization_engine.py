"""
Performance Optimization Engine - Advanced Query Optimization System
===================================================================

Provides intelligent query optimization, resource management, and performance
tuning for the HybridQueryRouter system with automated query rewriting,
index recommendations, and adaptive resource allocation.

Features:
- Intelligent query rewriting and optimization
- Index usage analysis and recommendations  
- Resource-based query scheduling and throttling
- Adaptive performance tuning based on workload patterns
- Cost-based optimization decisions
- Query plan caching and reuse
- Automated performance regression detection
- Memory and CPU resource management
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import psutil

from ..core.config import settings

logger = logging.getLogger(__name__)


class OptimizationStrategy(str, Enum):
    """Query optimization strategies"""
    REWRITE_SUBQUERY = "rewrite_subquery"
    OPTIMIZE_JOINS = "optimize_joins"
    ADD_LIMITS = "add_limits"
    PREDICATE_PUSHDOWN = "predicate_pushdown"
    INDEX_HINTS = "index_hints"
    MATERIALIZED_VIEW = "materialized_view"
    PARTITION_PRUNING = "partition_pruning"
    PARALLEL_EXECUTION = "parallel_execution"
    BATCH_PROCESSING = "batch_processing"


class ResourceType(str, Enum):
    """System resource types"""
    CPU = "cpu"
    MEMORY = "memory"
    IO = "io"
    NETWORK = "network"
    CONNECTIONS = "connections"


class QueryPriority(str, Enum):
    """Query execution priority levels"""
    CRITICAL = "critical"
    HIGH = "high" 
    NORMAL = "normal"
    LOW = "low"
    BACKGROUND = "background"


@dataclass
class OptimizationRule:
    """Rule for query optimization"""
    name: str
    strategy: OptimizationStrategy
    pattern: str  # Regex pattern to match
    replacement: str  # Replacement pattern
    conditions: Dict[str, Any] = field(default_factory=dict)
    priority: int = 100
    enabled: bool = True
    
    def matches(self, query: str, metadata: Dict[str, Any]) -> bool:
        """Check if rule matches query"""
        if not self.enabled:
            return False
        
        # Check pattern match
        if not re.search(self.pattern, query, re.IGNORECASE):
            return False
        
        # Check additional conditions
        for condition, expected_value in self.conditions.items():
            if condition in metadata and metadata[condition] != expected_value:
                return False
        
        return True
    
    def apply(self, query: str) -> str:
        """Apply optimization rule to query"""
        return re.sub(self.pattern, self.replacement, query, flags=re.IGNORECASE)


@dataclass
class ResourceQuota:
    """Resource quota configuration"""
    cpu_percent: float = 80.0
    memory_mb: float = 4096.0
    max_connections: int = 50
    io_limit_mb_per_sec: float = 100.0
    query_timeout_seconds: float = 300.0


@dataclass
class PerformanceMetrics:
    """Performance tracking metrics"""
    query_id: str
    original_query: str
    optimized_query: Optional[str] = None
    optimization_strategies: List[str] = field(default_factory=list)
    
    # Timing metrics
    original_duration: Optional[float] = None
    optimized_duration: Optional[float] = None
    optimization_time: float = 0.0
    
    # Resource metrics
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    io_operations: int = 0
    
    # Improvement metrics
    performance_gain: float = 0.0  # Percentage improvement
    resource_savings: Dict[str, float] = field(default_factory=dict)
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    database_target: str = "postgresql"


@dataclass
class SystemResourceState:
    """Current system resource state"""
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_available_mb: float = 0.0
    io_read_mb_per_sec: float = 0.0
    io_write_mb_per_sec: float = 0.0
    active_connections: int = 0
    query_queue_size: int = 0
    
    timestamp: datetime = field(default_factory=datetime.now)
    
    def is_under_pressure(self, quota: ResourceQuota) -> bool:
        """Check if system is under resource pressure"""
        return (
            self.cpu_usage_percent > quota.cpu_percent or
            self.memory_usage_mb > quota.memory_mb or
            self.active_connections > quota.max_connections
        )
    
    def get_pressure_score(self, quota: ResourceQuota) -> float:
        """Get overall resource pressure score (0-100)"""
        cpu_pressure = min(self.cpu_usage_percent / quota.cpu_percent, 1.0) * 100
        memory_pressure = min(self.memory_usage_mb / quota.memory_mb, 1.0) * 100
        connection_pressure = min(self.active_connections / quota.max_connections, 1.0) * 100
        
        return (cpu_pressure + memory_pressure + connection_pressure) / 3.0


class QueryOptimizer:
    """Intelligent query optimization engine"""
    
    def __init__(self):
        self.optimization_rules: List[OptimizationRule] = []
        self.optimization_cache: Dict[str, Tuple[str, List[str]]] = {}
        self.performance_history: Dict[str, List[PerformanceMetrics]] = defaultdict(list)
        
        self._initialize_default_rules()
        
        logger.info("QueryOptimizer initialized with default optimization rules")
    
    def _initialize_default_rules(self):
        """Initialize default optimization rules"""
        
        # Subquery to JOIN optimization
        self.optimization_rules.append(OptimizationRule(
            name="subquery_to_join",
            strategy=OptimizationStrategy.REWRITE_SUBQUERY,
            pattern=r"WHERE\s+(\w+)\s+IN\s*\(\s*SELECT\s+(\w+)\s+FROM\s+(\w+)(?:\s+WHERE\s+([^)]+))?\s*\)",
            replacement=r"JOIN \3 AS sub ON \1 = sub.\2" + r" WHERE \4" if r"\4" else "",
            priority=90
        ))
        
        # Add LIMIT to potentially large result sets
        self.optimization_rules.append(OptimizationRule(
            name="auto_add_limit",
            strategy=OptimizationStrategy.ADD_LIMITS,
            pattern=r"SELECT\s+.*\s+FROM\s+(?:pages_v2|scrape_pages|cdx_records)(?:\s+WHERE\s+[^LIMIT]+)?(?!.*LIMIT)",
            replacement=lambda m: m.group(0) + " LIMIT 10000",
            conditions={"estimated_rows": lambda x: x > 50000},
            priority=80
        ))
        
        # Optimize ORDER BY with LIMIT
        self.optimization_rules.append(OptimizationRule(
            name="optimize_order_by_limit", 
            strategy=OptimizationStrategy.OPTIMIZE_JOINS,
            pattern=r"SELECT\s+.*\s+ORDER\s+BY\s+([^LIMIT]+)\s+LIMIT\s+(\d+)",
            replacement=r"SELECT * FROM (SELECT * ORDER BY \1 LIMIT \2) AS optimized_query",
            priority=85
        ))
        
        # Convert EXISTS to JOIN when possible
        self.optimization_rules.append(OptimizationRule(
            name="exists_to_join",
            strategy=OptimizationStrategy.REWRITE_SUBQUERY,
            pattern=r"WHERE\s+EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+(\w+)\s+WHERE\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)\s*\)",
            replacement=r"JOIN \1 ON \2.\3 = \4.\5",
            priority=88
        ))
        
        # Predicate pushdown for joins
        self.optimization_rules.append(OptimizationRule(
            name="predicate_pushdown",
            strategy=OptimizationStrategy.PREDICATE_PUSHDOWN,
            pattern=r"FROM\s+(\w+)\s+JOIN\s+(\w+)\s+ON\s+([^WHERE]+)\s+WHERE\s+(\2\.\w+\s*[<>=!]+\s*[^AND\s]+)",
            replacement=r"FROM \1 JOIN (SELECT * FROM \2 WHERE \4) AS \2 ON \3",
            priority=75
        ))
        
        # Use covering indexes hint
        self.optimization_rules.append(OptimizationRule(
            name="covering_index_hint",
            strategy=OptimizationStrategy.INDEX_HINTS,
            pattern=r"SELECT\s+([\w,\s]+)\s+FROM\s+(\w+)\s+WHERE\s+(\w+)\s*=",
            replacement=r"SELECT \1 FROM \2 /*+ INDEX_HINT(covering_\3) */ WHERE \3 =",
            conditions={"has_covering_index": True},
            priority=70
        ))
    
    async def optimize_query(
        self,
        query: str,
        metadata: Optional[Dict[str, Any]] = None,
        performance_target: Optional[float] = None
    ) -> Tuple[str, List[str]]:
        """
        Optimize a SQL query using available strategies
        
        Args:
            query: Original SQL query
            metadata: Query metadata for optimization decisions
            performance_target: Target performance improvement (optional)
            
        Returns:
            Tuple of (optimized_query, applied_strategies)
        """
        metadata = metadata or {}
        
        # Check optimization cache
        query_hash = self._get_query_hash(query)
        if query_hash in self.optimization_cache:
            cached_result = self.optimization_cache[query_hash]
            logger.debug(f"Using cached optimization for query {query_hash[:8]}")
            return cached_result
        
        start_time = time.time()
        optimized_query = query
        applied_strategies = []
        
        # Apply optimization rules in priority order
        for rule in sorted(self.optimization_rules, key=lambda r: r.priority, reverse=True):
            if rule.matches(query, metadata):
                try:
                    new_query = rule.apply(optimized_query)
                    if new_query != optimized_query:
                        optimized_query = new_query
                        applied_strategies.append(rule.strategy.value)
                        logger.debug(f"Applied optimization rule: {rule.name}")
                        
                        # Stop if we've reached performance target
                        if performance_target and len(applied_strategies) >= performance_target:
                            break
                            
                except Exception as e:
                    logger.error(f"Failed to apply optimization rule {rule.name}: {e}")
        
        optimization_time = time.time() - start_time
        
        # Cache the result
        self.optimization_cache[query_hash] = (optimized_query, applied_strategies)
        
        # Record performance metrics
        await self._record_optimization_metrics(
            query, optimized_query, applied_strategies, optimization_time
        )
        
        logger.info(
            f"Query optimization completed in {optimization_time:.3f}s, "
            f"applied {len(applied_strategies)} strategies"
        )
        
        return optimized_query, applied_strategies
    
    def add_optimization_rule(self, rule: OptimizationRule):
        """Add custom optimization rule"""
        self.optimization_rules.append(rule)
        self.optimization_rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info(f"Added optimization rule: {rule.name}")
    
    def disable_rule(self, rule_name: str):
        """Disable an optimization rule"""
        for rule in self.optimization_rules:
            if rule.name == rule_name:
                rule.enabled = False
                logger.info(f"Disabled optimization rule: {rule_name}")
                break
    
    def _get_query_hash(self, query: str) -> str:
        """Generate hash for query caching"""
        return hashlib.sha256(query.encode()).hexdigest()[:16]
    
    async def _record_optimization_metrics(
        self,
        original_query: str,
        optimized_query: str, 
        strategies: List[str],
        optimization_time: float
    ):
        """Record optimization performance metrics"""
        query_id = self._get_query_hash(original_query)
        
        metrics = PerformanceMetrics(
            query_id=query_id,
            original_query=original_query,
            optimized_query=optimized_query if optimized_query != original_query else None,
            optimization_strategies=strategies,
            optimization_time=optimization_time
        )
        
        self.performance_history[query_id].append(metrics)
        
        # Limit history size
        if len(self.performance_history[query_id]) > 100:
            self.performance_history[query_id] = self.performance_history[query_id][-100:]
    
    def get_optimization_statistics(self) -> Dict[str, Any]:
        """Get optimization performance statistics"""
        total_optimizations = sum(len(history) for history in self.performance_history.values())
        
        strategy_counts = defaultdict(int)
        total_optimization_time = 0.0
        
        for history in self.performance_history.values():
            for metrics in history:
                for strategy in metrics.optimization_strategies:
                    strategy_counts[strategy] += 1
                total_optimization_time += metrics.optimization_time
        
        avg_optimization_time = total_optimization_time / total_optimizations if total_optimizations > 0 else 0.0
        
        return {
            "total_optimizations": total_optimizations,
            "unique_queries": len(self.performance_history),
            "avg_optimization_time": round(avg_optimization_time, 4),
            "strategy_usage": dict(strategy_counts),
            "cache_size": len(self.optimization_cache),
            "active_rules": len([r for r in self.optimization_rules if r.enabled])
        }


class ResourceManager:
    """System resource management and throttling"""
    
    def __init__(self):
        self.resource_quota = ResourceQuota()
        self.current_state = SystemResourceState()
        self.query_queue: deque = deque()
        self.active_queries: Dict[str, Dict[str, Any]] = {}
        
        # Resource monitoring
        self.resource_history: deque = deque(maxlen=300)  # 5 minutes at 1s intervals
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Throttling configuration
        self.throttling_enabled = True
        self.max_concurrent_queries = {
            QueryPriority.CRITICAL: 10,
            QueryPriority.HIGH: 20,
            QueryPriority.NORMAL: 50,
            QueryPriority.LOW: 30,
            QueryPriority.BACKGROUND: 10
        }
        
        logger.info("ResourceManager initialized")
    
    async def initialize(self):
        """Initialize resource monitoring"""
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitor_resources())
        logger.info("Resource monitoring started")
    
    async def _monitor_resources(self):
        """Background resource monitoring loop"""
        while True:
            try:
                await self._update_resource_state()
                await asyncio.sleep(1.0)  # Update every second
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
                await asyncio.sleep(5.0)
    
    async def _update_resource_state(self):
        """Update current resource state"""
        try:
            # CPU and memory usage
            self.current_state.cpu_usage_percent = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory()
            self.current_state.memory_usage_mb = (memory.total - memory.available) / (1024 * 1024)
            self.current_state.memory_available_mb = memory.available / (1024 * 1024)
            
            # IO statistics
            io_stats = psutil.disk_io_counters()
            if io_stats:
                # Calculate per-second rates (simplified)
                self.current_state.io_read_mb_per_sec = io_stats.read_bytes / (1024 * 1024) / 60  # Rough estimate
                self.current_state.io_write_mb_per_sec = io_stats.write_bytes / (1024 * 1024) / 60
            
            # Query state
            self.current_state.active_connections = len(self.active_queries)
            self.current_state.query_queue_size = len(self.query_queue)
            self.current_state.timestamp = datetime.now()
            
            # Add to history
            self.resource_history.append(self.current_state)
            
        except Exception as e:
            logger.error(f"Error updating resource state: {e}")
    
    async def request_query_execution(
        self,
        query_id: str,
        priority: QueryPriority,
        estimated_resources: Dict[str, float]
    ) -> bool:
        """
        Request permission to execute a query
        
        Args:
            query_id: Unique query identifier
            priority: Query priority level
            estimated_resources: Estimated resource requirements
            
        Returns:
            True if query can execute immediately, False if queued
        """
        # Check if system is under pressure
        if self._should_throttle_query(priority, estimated_resources):
            # Add to queue
            await self._queue_query(query_id, priority, estimated_resources)
            return False
        
        # Allow immediate execution
        await self._start_query_execution(query_id, priority, estimated_resources)
        return True
    
    def _should_throttle_query(self, priority: QueryPriority, estimated_resources: Dict[str, float]) -> bool:
        """Determine if query should be throttled"""
        if not self.throttling_enabled:
            return False
        
        # Never throttle critical queries
        if priority == QueryPriority.CRITICAL:
            return False
        
        # Check resource pressure
        pressure_score = self.current_state.get_pressure_score(self.resource_quota)
        
        # Throttle based on priority and pressure
        throttle_thresholds = {
            QueryPriority.HIGH: 90.0,
            QueryPriority.NORMAL: 80.0,
            QueryPriority.LOW: 70.0,
            QueryPriority.BACKGROUND: 60.0
        }
        
        if pressure_score > throttle_thresholds.get(priority, 80.0):
            return True
        
        # Check concurrent query limits
        priority_count = sum(
            1 for query in self.active_queries.values()
            if query.get("priority") == priority
        )
        
        if priority_count >= self.max_concurrent_queries.get(priority, 50):
            return True
        
        # Check specific resource constraints
        if estimated_resources.get("memory_mb", 0) > self.current_state.memory_available_mb * 0.5:
            return True
        
        return False
    
    async def _queue_query(self, query_id: str, priority: QueryPriority, estimated_resources: Dict[str, float]):
        """Add query to execution queue"""
        query_info = {
            "query_id": query_id,
            "priority": priority,
            "estimated_resources": estimated_resources,
            "queued_at": datetime.now()
        }
        
        # Insert based on priority
        if priority == QueryPriority.CRITICAL:
            self.query_queue.appendleft(query_info)
        elif priority == QueryPriority.HIGH:
            # Insert after other critical/high priority queries
            insert_index = 0
            for i, queued_query in enumerate(self.query_queue):
                if queued_query["priority"] not in [QueryPriority.CRITICAL, QueryPriority.HIGH]:
                    insert_index = i
                    break
            else:
                insert_index = len(self.query_queue)
            
            if insert_index == len(self.query_queue):
                self.query_queue.append(query_info)
            else:
                # Insert at specific position (requires converting to list temporarily)
                queue_list = list(self.query_queue)
                queue_list.insert(insert_index, query_info)
                self.query_queue = deque(queue_list)
        else:
            # Normal, low, and background queries go to the end
            self.query_queue.append(query_info)
        
        logger.debug(f"Queued query {query_id} with priority {priority.value}")
    
    async def _start_query_execution(
        self,
        query_id: str,
        priority: QueryPriority,
        estimated_resources: Dict[str, float]
    ):
        """Start tracking query execution"""
        self.active_queries[query_id] = {
            "priority": priority,
            "estimated_resources": estimated_resources,
            "started_at": datetime.now()
        }
        
        logger.debug(f"Started tracking query {query_id}")
    
    async def complete_query_execution(self, query_id: str, actual_resources: Optional[Dict[str, float]] = None):
        """Mark query as completed and process queue"""
        if query_id in self.active_queries:
            query_info = self.active_queries.pop(query_id)
            
            # Update resource usage tracking if provided
            if actual_resources:
                self._update_resource_predictions(query_id, query_info["estimated_resources"], actual_resources)
            
            logger.debug(f"Completed query {query_id}")
        
        # Process next query in queue
        await self._process_query_queue()
    
    async def _process_query_queue(self):
        """Process pending queries in queue"""
        while self.query_queue:
            queued_query = self.query_queue[0]
            
            # Check if query can now execute
            if not self._should_throttle_query(queued_query["priority"], queued_query["estimated_resources"]):
                # Remove from queue and start execution
                query_info = self.query_queue.popleft()
                await self._start_query_execution(
                    query_info["query_id"],
                    query_info["priority"], 
                    query_info["estimated_resources"]
                )
                logger.debug(f"Dequeued and started query {query_info['query_id']}")
            else:
                # Still need to wait
                break
    
    def _update_resource_predictions(
        self,
        query_id: str,
        estimated: Dict[str, float],
        actual: Dict[str, float]
    ):
        """Update resource prediction accuracy"""
        # This could implement ML-based resource prediction improvement
        # For now, just log the difference for monitoring
        for resource, actual_value in actual.items():
            estimated_value = estimated.get(resource, 0)
            if estimated_value > 0:
                accuracy = min(actual_value / estimated_value, estimated_value / actual_value)
                logger.debug(f"Resource prediction accuracy for {resource}: {accuracy:.2f}")
    
    def get_resource_statistics(self) -> Dict[str, Any]:
        """Get resource management statistics"""
        return {
            "current_state": {
                "cpu_usage": self.current_state.cpu_usage_percent,
                "memory_usage_mb": self.current_state.memory_usage_mb,
                "active_connections": self.current_state.active_connections,
                "pressure_score": self.current_state.get_pressure_score(self.resource_quota)
            },
            "queue_status": {
                "queued_queries": len(self.query_queue),
                "active_queries": len(self.active_queries)
            },
            "resource_quota": {
                "cpu_limit": self.resource_quota.cpu_percent,
                "memory_limit_mb": self.resource_quota.memory_mb,
                "max_connections": self.resource_quota.max_connections
            },
            "throttling_enabled": self.throttling_enabled
        }
    
    def set_resource_quota(self, quota: ResourceQuota):
        """Update resource quota settings"""
        self.resource_quota = quota
        logger.info(f"Updated resource quota: CPU={quota.cpu_percent}%, Memory={quota.memory_mb}MB")
    
    def enable_throttling(self, enabled: bool = True):
        """Enable or disable query throttling"""
        self.throttling_enabled = enabled
        logger.info(f"Query throttling {'enabled' if enabled else 'disabled'}")
    
    async def shutdown(self):
        """Shutdown resource manager"""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("ResourceManager shutdown completed")


class PerformanceOptimizationEngine:
    """
    Main optimization engine coordinating query optimization and resource management
    """
    
    def __init__(self):
        self.query_optimizer = QueryOptimizer()
        self.resource_manager = ResourceManager()
        
        # Performance tracking
        self.optimization_metrics: Dict[str, Any] = defaultdict(int)
        self.performance_regression_detector = deque(maxlen=1000)
        
        logger.info("PerformanceOptimizationEngine initialized")
    
    async def initialize(self):
        """Initialize the optimization engine"""
        await self.resource_manager.initialize()
        logger.info("PerformanceOptimizationEngine initialization completed")
    
    async def optimize_and_schedule_query(
        self,
        query: str,
        priority: QueryPriority = QueryPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, bool, List[str]]:
        """
        Optimize query and schedule for execution
        
        Args:
            query: Original SQL query
            priority: Query execution priority
            metadata: Query metadata for optimization
            
        Returns:
            Tuple of (optimized_query, can_execute_immediately, optimization_strategies)
        """
        # Optimize the query
        optimized_query, strategies = await self.query_optimizer.optimize_query(query, metadata)
        
        # Estimate resource requirements
        estimated_resources = self._estimate_query_resources(optimized_query, metadata or {})
        
        # Request execution permission
        query_id = self._generate_query_id(optimized_query)
        can_execute = await self.resource_manager.request_query_execution(
            query_id, priority, estimated_resources
        )
        
        # Track optimization metrics
        self.optimization_metrics["total_optimizations"] += 1
        self.optimization_metrics["strategies_applied"] += len(strategies)
        
        logger.info(
            f"Query optimized with {len(strategies)} strategies, "
            f"can execute immediately: {can_execute}"
        )
        
        return optimized_query, can_execute, strategies
    
    def _estimate_query_resources(self, query: str, metadata: Dict[str, Any]) -> Dict[str, float]:
        """Estimate resource requirements for query"""
        # Simple heuristic-based estimation (could be enhanced with ML)
        resources = {
            "cpu_percent": 10.0,
            "memory_mb": 50.0,
            "io_mb_per_sec": 10.0
        }
        
        # Adjust based on query characteristics
        query_upper = query.upper()
        
        # Complex queries need more CPU
        if any(keyword in query_upper for keyword in ["JOIN", "GROUP BY", "ORDER BY"]):
            resources["cpu_percent"] *= 2
            resources["memory_mb"] *= 1.5
        
        # Window functions are CPU intensive
        if any(func in query_upper for func in ["ROW_NUMBER", "RANK", "LAG", "LEAD"]):
            resources["cpu_percent"] *= 3
            resources["memory_mb"] *= 2
        
        # Large tables need more resources
        if any(table in query_upper for table in ["PAGES_V2", "SCRAPE_PAGES"]):
            resources["memory_mb"] *= 3
            resources["io_mb_per_sec"] *= 2
        
        # Aggregations need memory
        if "GROUP BY" in query_upper:
            resources["memory_mb"] *= 2
        
        return resources
    
    def _generate_query_id(self, query: str) -> str:
        """Generate unique query ID"""
        return f"query_{int(time.time() * 1000)}_{hash(query) % 10000}"
    
    async def complete_query_execution(
        self,
        query_id: str,
        execution_time: float,
        success: bool,
        actual_resources: Optional[Dict[str, float]] = None
    ):
        """Mark query execution as complete"""
        await self.resource_manager.complete_query_execution(query_id, actual_resources)
        
        # Update performance tracking
        self._update_performance_tracking(query_id, execution_time, success, actual_resources)
    
    def _update_performance_tracking(
        self,
        query_id: str,
        execution_time: float,
        success: bool,
        actual_resources: Optional[Dict[str, float]]
    ):
        """Update performance tracking and regression detection"""
        perf_data = {
            "query_id": query_id,
            "execution_time": execution_time,
            "success": success,
            "timestamp": datetime.now(),
            "resources": actual_resources or {}
        }
        
        self.performance_regression_detector.append(perf_data)
        
        # Simple regression detection (could be enhanced)
        if len(self.performance_regression_detector) >= 100:
            recent_times = [p["execution_time"] for p in list(self.performance_regression_detector)[-50:]]
            older_times = [p["execution_time"] for p in list(self.performance_regression_detector)[-100:-50]]
            
            if recent_times and older_times:
                recent_avg = sum(recent_times) / len(recent_times)
                older_avg = sum(older_times) / len(older_times)
                
                # If recent queries are significantly slower
                if recent_avg > older_avg * 1.5:
                    logger.warning(f"Performance regression detected: recent avg {recent_avg:.3f}s vs older avg {older_avg:.3f}s")
    
    def add_optimization_rule(self, rule: OptimizationRule):
        """Add custom optimization rule"""
        self.query_optimizer.add_optimization_rule(rule)
    
    def set_resource_limits(self, quota: ResourceQuota):
        """Set resource quota limits"""
        self.resource_manager.set_resource_quota(quota)
    
    def get_comprehensive_statistics(self) -> Dict[str, Any]:
        """Get comprehensive performance and optimization statistics"""
        return {
            "optimization": self.query_optimizer.get_optimization_statistics(),
            "resource_management": self.resource_manager.get_resource_statistics(),
            "performance_tracking": {
                "total_executions": len(self.performance_regression_detector),
                "optimization_metrics": dict(self.optimization_metrics)
            }
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for optimization engine"""
        return {
            "status": "healthy",
            "optimizer_rules": len(self.query_optimizer.optimization_rules),
            "resource_pressure": self.resource_manager.current_state.get_pressure_score(
                self.resource_manager.resource_quota
            ),
            "active_queries": len(self.resource_manager.active_queries),
            "queued_queries": len(self.resource_manager.query_queue)
        }
    
    async def shutdown(self):
        """Shutdown optimization engine"""
        await self.resource_manager.shutdown()
        logger.info("PerformanceOptimizationEngine shutdown completed")


# Global optimization engine instance
performance_engine = PerformanceOptimizationEngine()


# Export public interface
__all__ = [
    'PerformanceOptimizationEngine',
    'QueryOptimizer',
    'ResourceManager',
    'OptimizationRule',
    'OptimizationStrategy',
    'ResourceQuota',
    'QueryPriority',
    'PerformanceMetrics',
    'performance_engine'
]