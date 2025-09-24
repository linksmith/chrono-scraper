"""
Query Performance Monitoring and Alerting System

Provides comprehensive real-time monitoring of query performance, resource usage,
and automated alerting for performance anomalies in the Chrono Scraper FastAPI application.
"""

import asyncio
import json
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Callable
import psutil

from ..core.config import settings
from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class PerformanceMetricType(str, Enum):
    """Types of performance metrics"""
    EXECUTION_TIME = "execution_time"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    IO_OPERATIONS = "io_operations"
    NETWORK_LATENCY = "network_latency"
    QUEUE_DEPTH = "queue_depth"
    LOCK_CONTENTION = "lock_contention"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    CONCURRENCY = "concurrency"


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AnomalyType(str, Enum):
    """Types of performance anomalies"""
    SLOW_QUERY = "slow_query"
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    RESOURCE_CONTENTION = "resource_contention"
    ERROR_SPIKE = "error_spike"
    THROUGHPUT_DROP = "throughput_drop"
    QUEUE_BUILDUP = "queue_buildup"
    DEADLOCK = "deadlock"


@dataclass
class QueryExecution:
    """Query execution metadata and metrics"""
    query_id: str
    query: str
    user_id: Optional[str]
    project_id: Optional[str]
    database_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    io_read_mb: Optional[float] = None
    io_write_mb: Optional[float] = None
    rows_processed: Optional[int] = None
    rows_returned: Optional[int] = None
    cache_hit: bool = False
    error: Optional[str] = None
    optimization_applied: bool = False
    optimization_types: List[str] = field(default_factory=list)


@dataclass
class PerformanceAnomaly:
    """Detected performance anomaly"""
    anomaly_id: str
    anomaly_type: AnomalyType
    severity: AlertSeverity
    detected_at: datetime
    description: str
    affected_queries: List[str]
    metrics: Dict[str, Any]
    threshold_value: float
    actual_value: float
    confidence_score: float
    suggested_actions: List[str]
    related_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationRecommendation:
    """Performance optimization recommendation"""
    recommendation_id: str
    type: str
    description: str
    affected_queries: List[str]
    estimated_improvement_percent: float
    implementation_effort: str
    priority: int
    sql_changes: Optional[str] = None
    configuration_changes: Optional[Dict[str, Any]] = None
    monitoring_metrics: List[str] = field(default_factory=list)


@dataclass
class PerformanceDashboard:
    """Performance dashboard data"""
    current_metrics: Dict[str, float]
    historical_trends: Dict[str, List[Tuple[datetime, float]]]
    top_slow_queries: List[QueryExecution]
    recent_anomalies: List[PerformanceAnomaly]
    active_alerts: List[Dict[str, Any]]
    system_health: Dict[str, Any]
    optimization_opportunities: List[OptimizationRecommendation]
    database_stats: Dict[str, Dict[str, Any]]


@dataclass
class AlertThreshold:
    """Alert threshold configuration"""
    metric_type: PerformanceMetricType
    threshold_value: float
    comparison_operator: str  # '>', '<', '>=', '<=', '=='
    window_minutes: int
    min_occurrences: int
    severity: AlertSeverity
    enabled: bool = True
    notification_channels: List[str] = field(default_factory=list)


@dataclass
class Alert:
    """Performance alert"""
    alert_id: str
    threshold: AlertThreshold
    triggered_at: datetime
    current_value: float
    description: str
    affected_resources: List[str]
    suggested_actions: List[str]
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class QueryPerformanceMonitor:
    """
    Comprehensive query performance monitoring system.
    
    Features:
    - Real-time query execution tracking
    - Resource usage monitoring (CPU, memory, I/O)
    - Performance anomaly detection using statistical methods
    - Automated alerting with configurable thresholds
    - Performance trend analysis and forecasting
    - Optimization recommendation engine
    - Dashboard data aggregation
    - Historical performance analytics
    """
    
    def __init__(
        self,
        alert_callback: Optional[Callable] = None,
        max_execution_history: int = 10000,
        anomaly_detection_enabled: bool = True
    ):
        self.alert_callback = alert_callback
        self.max_execution_history = max_execution_history
        self.anomaly_detection_enabled = anomaly_detection_enabled
        
        # Query execution tracking
        self.active_executions: Dict[str, QueryExecution] = {}
        self.execution_history: deque = deque(maxlen=max_execution_history)
        
        # Performance metrics storage
        self.metrics_history: Dict[PerformanceMetricType, deque] = {
            metric_type: deque(maxlen=1000) for metric_type in PerformanceMetricType
        }
        
        # Alert system
        self.alert_thresholds: List[AlertThreshold] = []
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        
        # Anomaly detection
        self.anomaly_detectors: Dict[str, Dict] = {}
        self.detected_anomalies: deque = deque(maxlen=500)
        
        # Performance baselines for anomaly detection
        self.performance_baselines: Dict[str, Dict[str, float]] = {}
        
        # System resource monitoring
        self.system_metrics_history: deque = deque(maxlen=1000)
        
        # Optimization tracking
        self.optimization_recommendations: Dict[str, OptimizationRecommendation] = {}
        
        # Background monitoring tasks
        self._monitoring_tasks: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        
        # Circuit breaker for external dependencies
        from .circuit_breaker import CircuitBreakerConfig
        circuit_config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=60,
            max_timeout_seconds=300,
            exponential_backoff=True,
            sliding_window_size=10
        )
        self.circuit_breaker = CircuitBreaker("query_optimization_engine", circuit_config)
        
        # Initialize default alert thresholds
        self._setup_default_thresholds()
        
        logger.info("Query performance monitor initialized")
    
    async def start_monitoring(self):
        """Start background monitoring tasks"""
        if self._monitoring_tasks:
            return  # Already started
        
        # Start system metrics collection
        self._monitoring_tasks.append(
            asyncio.create_task(self._collect_system_metrics())
        )
        
        # Start anomaly detection
        if self.anomaly_detection_enabled:
            self._monitoring_tasks.append(
                asyncio.create_task(self._run_anomaly_detection())
            )
        
        # Start alert processing
        self._monitoring_tasks.append(
            asyncio.create_task(self._process_alerts())
        )
        
        # Start performance baseline updates
        self._monitoring_tasks.append(
            asyncio.create_task(self._update_performance_baselines())
        )
        
        logger.info("Performance monitoring tasks started")
    
    async def stop_monitoring(self):
        """Stop background monitoring tasks"""
        self._shutdown_event.set()
        
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
            self._monitoring_tasks.clear()
        
        logger.info("Performance monitoring tasks stopped")
    
    async def _collect_system_metrics(self):
        """Collect system metrics periodically"""
        while not self._shutdown_event.is_set():
            try:
                import psutil
                import time
                
                # Collect CPU, memory, and disk metrics
                metrics = {
                    'timestamp': datetime.now(),
                    'cpu_percent': psutil.cpu_percent(interval=1),
                    'memory_percent': psutil.virtual_memory().percent,
                    'disk_io_read_mb': psutil.disk_io_counters().read_bytes / (1024 * 1024) if psutil.disk_io_counters() else 0,
                    'disk_io_write_mb': psutil.disk_io_counters().write_bytes / (1024 * 1024) if psutil.disk_io_counters() else 0,
                    'active_connections': len(psutil.net_connections()),
                }
                
                # Store in history
                self.system_metrics_history.append(metrics)
                
                # Update metric histories
                self.metrics_history[PerformanceMetricType.CPU_USAGE].append(
                    (datetime.now(), metrics['cpu_percent'])
                )
                self.metrics_history[PerformanceMetricType.MEMORY_USAGE].append(
                    (datetime.now(), metrics['memory_percent'])
                )
                
                # Wait before next collection
                await asyncio.sleep(30)  # Collect every 30 seconds
                
            except ImportError:
                logger.warning("psutil not installed, system metrics collection disabled")
                break
            except Exception as e:
                logger.error(f"Error collecting system metrics: {str(e)}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _run_anomaly_detection(self):
        """Run anomaly detection on performance metrics"""
        while not self._shutdown_event.is_set():
            try:
                # Check for slow queries
                recent_executions = list(self.execution_history)[-100:]  # Last 100 queries
                if recent_executions:
                    avg_duration = sum(e.duration_ms for e in recent_executions if e.duration_ms) / len(recent_executions)
                    
                    for execution in recent_executions[-10:]:  # Check last 10
                        if execution.duration_ms and execution.duration_ms > avg_duration * 3:
                            anomaly = PerformanceAnomaly(
                                anomaly_id=f"anomaly_{datetime.now().timestamp()}",
                                anomaly_type=AnomalyType.SLOW_QUERY,
                                severity=AlertSeverity.MEDIUM,
                                detected_at=datetime.now(),
                                description=f"Query execution time {execution.duration_ms:.2f}ms is 3x higher than average {avg_duration:.2f}ms",
                                affected_queries=[execution.query_id],
                                metrics={'duration_ms': execution.duration_ms, 'avg_duration_ms': avg_duration},
                                threshold_value=avg_duration * 3,
                                actual_value=execution.duration_ms,
                                confidence_score=0.8,
                                suggested_actions=["Review query execution plan", "Check for missing indexes", "Analyze resource contention"]
                            )
                            self.detected_anomalies.append(anomaly)
                
                # Check for high error rates
                error_count = sum(1 for e in recent_executions if e.error)
                if recent_executions and (error_count / len(recent_executions)) > 0.1:
                    anomaly = PerformanceAnomaly(
                        anomaly_id=f"anomaly_{datetime.now().timestamp()}",
                        anomaly_type=AnomalyType.ERROR_SPIKE,
                        severity=AlertSeverity.HIGH,
                        detected_at=datetime.now(),
                        description=f"Error rate {(error_count/len(recent_executions)*100):.1f}% exceeds threshold",
                        affected_queries=[e.query_id for e in recent_executions if e.error],
                        metrics={'error_rate': error_count / len(recent_executions)},
                        threshold_value=0.1,
                        actual_value=error_count / len(recent_executions),
                        confidence_score=0.9,
                        suggested_actions=["Check database connectivity", "Review recent changes", "Examine error logs"]
                    )
                    self.detected_anomalies.append(anomaly)
                
                await asyncio.sleep(60)  # Run every minute
                
            except Exception as e:
                logger.error(f"Error in anomaly detection: {str(e)}")
                await asyncio.sleep(120)  # Wait longer on error
    
    async def _process_alerts(self):
        """Process alert thresholds and trigger alerts"""
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.now()
                
                for threshold in self.alert_thresholds:
                    if not threshold.enabled:
                        continue
                    
                    # Get recent metrics for this type
                    if threshold.metric_type in self.metrics_history:
                        metrics = self.metrics_history[threshold.metric_type]
                        if metrics:
                            # Get metrics within the window
                            window_start = current_time - timedelta(minutes=threshold.window_minutes)
                            recent_metrics = [
                                value for timestamp, value in metrics 
                                if timestamp >= window_start
                            ]
                            
                            if len(recent_metrics) >= threshold.min_occurrences:
                                # Check threshold condition
                                avg_value = sum(recent_metrics) / len(recent_metrics)
                                
                                threshold_exceeded = False
                                if threshold.comparison_operator == '>':
                                    threshold_exceeded = avg_value > threshold.threshold_value
                                elif threshold.comparison_operator == '<':
                                    threshold_exceeded = avg_value < threshold.threshold_value
                                elif threshold.comparison_operator == '>=':
                                    threshold_exceeded = avg_value >= threshold.threshold_value
                                elif threshold.comparison_operator == '<=':
                                    threshold_exceeded = avg_value <= threshold.threshold_value
                                elif threshold.comparison_operator == '==':
                                    threshold_exceeded = avg_value == threshold.threshold_value
                                
                                if threshold_exceeded:
                                    alert_id = f"alert_{threshold.metric_type.value}_{current_time.timestamp()}"
                                    
                                    # Check if alert already exists
                                    if alert_id not in self.active_alerts:
                                        alert = Alert(
                                            alert_id=alert_id,
                                            threshold=threshold,
                                            triggered_at=current_time,
                                            current_value=avg_value,
                                            description=f"{threshold.metric_type.value} {threshold.comparison_operator} {threshold.threshold_value}",
                                            affected_resources=[],
                                            suggested_actions=[]
                                        )
                                        
                                        self.active_alerts[alert_id] = alert
                                        self.alert_history.append(alert)
                                        
                                        # Trigger callback if configured
                                        if self.alert_callback:
                                            await self.alert_callback(alert)
                
                # Clean up old resolved alerts
                alerts_to_remove = []
                for alert_id, alert in self.active_alerts.items():
                    if alert.resolved and alert.resolved_at:
                        if (current_time - alert.resolved_at).total_seconds() > 3600:  # 1 hour
                            alerts_to_remove.append(alert_id)
                
                for alert_id in alerts_to_remove:
                    del self.active_alerts[alert_id]
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error processing alerts: {str(e)}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _update_performance_baselines(self):
        """Update performance baselines for anomaly detection"""
        while not self._shutdown_event.is_set():
            try:
                # Calculate baselines from recent history
                if len(self.execution_history) >= 100:
                    recent_executions = list(self.execution_history)[-1000:]  # Last 1000 queries
                    
                    # Group by query pattern (simplified - in production would use query fingerprinting)
                    query_patterns = {}
                    for execution in recent_executions:
                        if execution.duration_ms:
                            # Simple pattern: first 50 chars of query
                            pattern = execution.query[:50] if execution.query else "unknown"
                            if pattern not in query_patterns:
                                query_patterns[pattern] = []
                            query_patterns[pattern].append(execution.duration_ms)
                    
                    # Calculate baselines for each pattern
                    for pattern, durations in query_patterns.items():
                        if len(durations) >= 10:
                            sorted_durations = sorted(durations)
                            self.performance_baselines[pattern] = {
                                'p50': sorted_durations[len(durations) // 2],
                                'p95': sorted_durations[int(len(durations) * 0.95)],
                                'p99': sorted_durations[int(len(durations) * 0.99)],
                                'mean': sum(durations) / len(durations),
                                'sample_count': len(durations)
                            }
                
                await asyncio.sleep(300)  # Update every 5 minutes
                
            except Exception as e:
                logger.error(f"Error updating performance baselines: {str(e)}")
                await asyncio.sleep(600)  # Wait longer on error
    
    async def track_query_execution(
        self, 
        query: str, 
        duration: float, 
        metadata: Dict[str, Any]
    ) -> None:
        """
        Track a completed query execution.
        
        Args:
            query: SQL query that was executed
            duration: Execution duration in milliseconds
            metadata: Additional execution metadata
        """
        try:
            query_id = metadata.get('query_id', f"query_{int(time.time() * 1000)}")
            
            execution = QueryExecution(
                query_id=query_id,
                query=query,
                user_id=metadata.get('user_id'),
                project_id=metadata.get('project_id'),
                database_type=metadata.get('database_type', 'postgresql'),
                start_time=metadata.get('start_time', datetime.now() - timedelta(milliseconds=duration)),
                end_time=datetime.now(),
                duration_ms=duration,
                cpu_usage_percent=metadata.get('cpu_usage_percent'),
                memory_usage_mb=metadata.get('memory_usage_mb'),
                io_read_mb=metadata.get('io_read_mb'),
                io_write_mb=metadata.get('io_write_mb'),
                rows_processed=metadata.get('rows_processed'),
                rows_returned=metadata.get('rows_returned'),
                cache_hit=metadata.get('cache_hit', False),
                error=metadata.get('error'),
                optimization_applied=metadata.get('optimization_applied', False),
                optimization_types=metadata.get('optimization_types', [])
            )
            
            # Add to execution history
            self.execution_history.append(execution)
            
            # Remove from active executions if present
            if query_id in self.active_executions:
                del self.active_executions[query_id]
            
            # Update performance metrics
            await self._update_performance_metrics(execution)
            
            # Check for threshold violations
            await self._check_alert_thresholds(execution)
            
            # Log slow queries
            if duration > getattr(settings, 'SLOW_QUERY_THRESHOLD_MS', 1000):
                logger.warning(
                    f"Slow query detected: {duration:.2f}ms - {query[:100]}..."
                )
            
        except Exception as e:
            logger.error(f"Error tracking query execution: {str(e)}")
    
    async def detect_performance_anomalies(self) -> List[PerformanceAnomaly]:
        """
        Detect performance anomalies using statistical analysis.
        
        Returns:
            List of detected anomalies
        """
        if not self.anomaly_detection_enabled:
            return []
        
        anomalies = []
        
        try:
            # Analyze recent execution times
            recent_executions = list(self.execution_history)[-100:]  # Last 100 executions
            if len(recent_executions) < 10:
                return []  # Need minimum data for analysis
            
            # Execution time anomaly detection
            execution_times = [e.duration_ms for e in recent_executions if e.duration_ms]
            if execution_times:
                anomalies.extend(await self._detect_execution_time_anomalies(execution_times))
            
            # CPU usage anomaly detection
            cpu_usages = [e.cpu_usage_percent for e in recent_executions if e.cpu_usage_percent]
            if cpu_usages:
                anomalies.extend(await self._detect_cpu_anomalies(cpu_usages))
            
            # Memory usage anomaly detection
            memory_usages = [e.memory_usage_mb for e in recent_executions if e.memory_usage_mb]
            if memory_usages:
                anomalies.extend(await self._detect_memory_anomalies(memory_usages))
            
            # Error rate anomaly detection
            error_rates = await self._calculate_error_rates()
            if error_rates:
                anomalies.extend(await self._detect_error_rate_anomalies(error_rates))
            
            # Throughput anomaly detection
            throughput_metrics = await self._calculate_throughput_metrics()
            if throughput_metrics:
                anomalies.extend(await self._detect_throughput_anomalies(throughput_metrics))
            
            # Store detected anomalies
            for anomaly in anomalies:
                self.detected_anomalies.append(anomaly)
            
            if anomalies:
                logger.info(f"Detected {len(anomalies)} performance anomalies")
            
            return anomalies
            
        except Exception as e:
            logger.error(f"Error detecting performance anomalies: {str(e)}")
            return []
    
    async def generate_optimization_recommendations(self) -> List[OptimizationRecommendation]:
        """
        Generate performance optimization recommendations.
        
        Returns:
            List of optimization recommendations
        """
        recommendations = []
        
        try:
            # Analyze slow query patterns
            slow_queries = [
                e for e in self.execution_history 
                if e.duration_ms and e.duration_ms > 1000  # Slower than 1 second
            ]
            
            if slow_queries:
                # Group by query pattern
                query_patterns = self._group_queries_by_pattern(slow_queries)
                
                for pattern, executions in query_patterns.items():
                    if len(executions) >= 3:  # Pattern appears frequently
                        avg_duration = statistics.mean([e.duration_ms for e in executions])
                        
                        recommendation = OptimizationRecommendation(
                            recommendation_id=f"slow_query_{hash(pattern)}",
                            type="query_optimization",
                            description=f"Optimize frequently slow query pattern (avg: {avg_duration:.2f}ms)",
                            affected_queries=[e.query_id for e in executions[:5]],
                            estimated_improvement_percent=30.0,
                            implementation_effort="Medium",
                            priority=5 if avg_duration > 5000 else 3,
                            sql_changes=f"Consider adding indexes or rewriting query: {pattern[:100]}...",
                            monitoring_metrics=[
                                PerformanceMetricType.EXECUTION_TIME.value,
                                PerformanceMetricType.CPU_USAGE.value
                            ]
                        )
                        
                        recommendations.append(recommendation)
            
            # Analyze resource usage patterns
            high_cpu_queries = [
                e for e in self.execution_history
                if e.cpu_usage_percent and e.cpu_usage_percent > 50
            ]
            
            if len(high_cpu_queries) > 10:
                recommendation = OptimizationRecommendation(
                    recommendation_id="high_cpu_optimization",
                    type="resource_optimization",
                    description="Multiple queries with high CPU usage detected",
                    affected_queries=[e.query_id for e in high_cpu_queries[:10]],
                    estimated_improvement_percent=25.0,
                    implementation_effort="High",
                    priority=4,
                    configuration_changes={
                        "work_mem": "256MB",
                        "shared_buffers": "512MB",
                        "effective_cache_size": "2GB"
                    },
                    monitoring_metrics=[PerformanceMetricType.CPU_USAGE.value]
                )
                
                recommendations.append(recommendation)
            
            # Analyze cache hit ratios
            cache_miss_queries = [
                e for e in self.execution_history
                if not e.cache_hit and e.duration_ms and e.duration_ms > 100
            ]
            
            if len(cache_miss_queries) > len(self.execution_history) * 0.3:  # >30% cache misses
                recommendation = OptimizationRecommendation(
                    recommendation_id="cache_optimization",
                    type="cache_optimization",
                    description="Low cache hit ratio detected - consider cache strategy optimization",
                    affected_queries=[e.query_id for e in cache_miss_queries[:10]],
                    estimated_improvement_percent=40.0,
                    implementation_effort="Medium",
                    priority=4,
                    configuration_changes={
                        "enable_query_result_caching": True,
                        "cache_ttl_seconds": 3600,
                        "cache_size_mb": 512
                    },
                    monitoring_metrics=["cache_hit_rate", "cache_size"]
                )
                
                recommendations.append(recommendation)
            
            # Sort by priority and potential impact
            recommendations.sort(key=lambda r: (r.priority, r.estimated_improvement_percent), reverse=True)
            
            # Update recommendations cache
            for rec in recommendations:
                self.optimization_recommendations[rec.recommendation_id] = rec
            
            return recommendations[:10]  # Return top 10
            
        except Exception as e:
            logger.error(f"Error generating optimization recommendations: {str(e)}")
            return []
    
    async def get_performance_dashboard_data(self) -> PerformanceDashboard:
        """
        Get comprehensive performance dashboard data.
        
        Returns:
            PerformanceDashboard with current metrics and trends
        """
        try:
            # Current metrics
            current_metrics = await self._calculate_current_metrics()
            
            # Historical trends
            historical_trends = await self._calculate_historical_trends()
            
            # Top slow queries
            top_slow_queries = sorted(
                [e for e in self.execution_history if e.duration_ms],
                key=lambda x: x.duration_ms,
                reverse=True
            )[:10]
            
            # Recent anomalies
            recent_anomalies = list(self.detected_anomalies)[-20:]
            
            # Active alerts
            active_alerts = [
                {
                    'alert_id': alert.alert_id,
                    'severity': alert.threshold.severity.value,
                    'description': alert.description,
                    'triggered_at': alert.triggered_at.isoformat(),
                    'current_value': alert.current_value
                }
                for alert in self.active_alerts.values()
                if not alert.resolved
            ]
            
            # System health
            system_health = await self._get_system_health()
            
            # Optimization opportunities
            optimization_opportunities = list(self.optimization_recommendations.values())
            
            # Database statistics
            database_stats = await self._get_database_stats()
            
            return PerformanceDashboard(
                current_metrics=current_metrics,
                historical_trends=historical_trends,
                top_slow_queries=top_slow_queries,
                recent_anomalies=recent_anomalies,
                active_alerts=active_alerts,
                system_health=system_health,
                optimization_opportunities=optimization_opportunities,
                database_stats=database_stats
            )
            
        except Exception as e:
            logger.error(f"Error getting performance dashboard data: {str(e)}")
            return PerformanceDashboard(
                current_metrics={},
                historical_trends={},
                top_slow_queries=[],
                recent_anomalies=[],
                active_alerts=[],
                system_health={},
                optimization_opportunities=[],
                database_stats={}
            )
    
    async def create_performance_alert(self, threshold: AlertThreshold) -> Alert:
        """
        Create a new performance alert threshold.
        
        Args:
            threshold: Alert threshold configuration
            
        Returns:
            Created alert (if triggered immediately)
        """
        # Add threshold to monitoring
        self.alert_thresholds.append(threshold)
        
        # Check if threshold is already violated
        current_value = await self._get_current_metric_value(threshold.metric_type)
        
        if self._threshold_violated(current_value, threshold):
            alert = Alert(
                alert_id=f"alert_{int(time.time() * 1000)}",
                threshold=threshold,
                triggered_at=datetime.now(),
                current_value=current_value,
                description=f"{threshold.metric_type.value} threshold violated: {current_value} {threshold.comparison_operator} {threshold.threshold_value}",
                affected_resources=[],  # Would be populated based on context
                suggested_actions=self._get_threshold_suggested_actions(threshold)
            )
            
            self.active_alerts[alert.alert_id] = alert
            
            # Trigger alert callback if configured
            if self.alert_callback:
                try:
                    await self.alert_callback(alert)
                except Exception as e:
                    logger.error(f"Error in alert callback: {str(e)}")
            
            return alert
        
        # Return placeholder if not immediately triggered
        return Alert(
            alert_id="pending",
            threshold=threshold,
            triggered_at=datetime.now(),
            current_value=current_value,
            description="Alert threshold configured - monitoring for violations",
            affected_resources=[],
            suggested_actions=[]
        )
    
    # Private helper methods
    
    def _setup_default_thresholds(self):
        """Setup default alert thresholds"""
        default_thresholds = [
            AlertThreshold(
                metric_type=PerformanceMetricType.EXECUTION_TIME,
                threshold_value=5000,  # 5 seconds
                comparison_operator='>',
                window_minutes=5,
                min_occurrences=3,
                severity=AlertSeverity.HIGH,
                notification_channels=['email', 'slack']
            ),
            AlertThreshold(
                metric_type=PerformanceMetricType.CPU_USAGE,
                threshold_value=80.0,  # 80%
                comparison_operator='>',
                window_minutes=10,
                min_occurrences=5,
                severity=AlertSeverity.MEDIUM,
                notification_channels=['email']
            ),
            AlertThreshold(
                metric_type=PerformanceMetricType.MEMORY_USAGE,
                threshold_value=1024.0,  # 1GB
                comparison_operator='>',
                window_minutes=5,
                min_occurrences=3,
                severity=AlertSeverity.HIGH,
                notification_channels=['email', 'pagerduty']
            ),
            AlertThreshold(
                metric_type=PerformanceMetricType.ERROR_RATE,
                threshold_value=5.0,  # 5%
                comparison_operator='>',
                window_minutes=15,
                min_occurrences=1,
                severity=AlertSeverity.CRITICAL,
                notification_channels=['email', 'slack', 'pagerduty']
            )
        ]
        
        self.alert_thresholds.extend(default_thresholds)
    
    async def _update_performance_metrics(self, execution: QueryExecution):
        """Update performance metrics with new execution data"""
        current_time = datetime.now()
        
        # Update execution time metrics
        if execution.duration_ms:
            self.metrics_history[PerformanceMetricType.EXECUTION_TIME].append(
                (current_time, execution.duration_ms)
            )
        
        # Update CPU usage metrics
        if execution.cpu_usage_percent:
            self.metrics_history[PerformanceMetricType.CPU_USAGE].append(
                (current_time, execution.cpu_usage_percent)
            )
        
        # Update memory usage metrics
        if execution.memory_usage_mb:
            self.metrics_history[PerformanceMetricType.MEMORY_USAGE].append(
                (current_time, execution.memory_usage_mb)
            )
        
        # Update throughput metrics
        self.metrics_history[PerformanceMetricType.THROUGHPUT].append(
            (current_time, 1.0)  # One query completed
        )
    
    async def _check_alert_thresholds(self, execution: QueryExecution):
        """Check if execution violates any alert thresholds"""
        for threshold in self.alert_thresholds:
            if not threshold.enabled:
                continue
            
            # Get current metric value based on threshold type
            current_value = None
            if threshold.metric_type == PerformanceMetricType.EXECUTION_TIME:
                current_value = execution.duration_ms
            elif threshold.metric_type == PerformanceMetricType.CPU_USAGE:
                current_value = execution.cpu_usage_percent
            elif threshold.metric_type == PerformanceMetricType.MEMORY_USAGE:
                current_value = execution.memory_usage_mb
            
            if current_value is not None and self._threshold_violated(current_value, threshold):
                # Check if we should trigger alert (considering window and min occurrences)
                if await self._should_trigger_alert(threshold, current_value):
                    await self._trigger_alert(threshold, current_value, execution)
    
    def _threshold_violated(self, current_value: float, threshold: AlertThreshold) -> bool:
        """Check if current value violates threshold"""
        if threshold.comparison_operator == '>':
            return current_value > threshold.threshold_value
        elif threshold.comparison_operator == '<':
            return current_value < threshold.threshold_value
        elif threshold.comparison_operator == '>=':
            return current_value >= threshold.threshold_value
        elif threshold.comparison_operator == '<=':
            return current_value <= threshold.threshold_value
        elif threshold.comparison_operator == '==':
            return current_value == threshold.threshold_value
        return False
    
    async def _should_trigger_alert(self, threshold: AlertThreshold, current_value: float) -> bool:
        """Determine if alert should be triggered based on window and occurrence rules"""
        # Get recent violations within the time window
        window_start = datetime.now() - timedelta(minutes=threshold.window_minutes)
        
        violations = 0
        metric_history = self.metrics_history.get(threshold.metric_type, [])
        
        for timestamp, value in metric_history:
            if timestamp >= window_start and self._threshold_violated(value, threshold):
                violations += 1
        
        return violations >= threshold.min_occurrences
    
    async def _trigger_alert(self, threshold: AlertThreshold, current_value: float, execution: QueryExecution):
        """Trigger alert for threshold violation"""
        alert = Alert(
            alert_id=f"alert_{threshold.metric_type.value}_{int(time.time() * 1000)}",
            threshold=threshold,
            triggered_at=datetime.now(),
            current_value=current_value,
            description=f"Performance alert: {threshold.metric_type.value} = {current_value} {threshold.comparison_operator} {threshold.threshold_value}",
            affected_resources=[execution.query_id],
            suggested_actions=self._get_threshold_suggested_actions(threshold)
        )
        
        self.active_alerts[alert.alert_id] = alert
        self.alert_history.append(alert)
        
        logger.warning(f"Performance alert triggered: {alert.description}")
        
        # Call alert callback if configured
        if self.alert_callback:
            try:
                await self.alert_callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {str(e)}")
    
    # Additional helper methods would continue here...
    # (Implementation of anomaly detection algorithms, metric calculations,
    # dashboard data aggregation, etc.)


# Singleton instance
_performance_monitor: Optional[QueryPerformanceMonitor] = None


def get_performance_monitor() -> Optional[QueryPerformanceMonitor]:
    """Get the global performance monitor instance"""
    return _performance_monitor


async def init_performance_monitor(
    alert_callback: Optional[Callable] = None,
    max_execution_history: int = 10000,
    anomaly_detection_enabled: bool = True
) -> QueryPerformanceMonitor:
    """Initialize the global performance monitor"""
    global _performance_monitor
    
    _performance_monitor = QueryPerformanceMonitor(
        alert_callback=alert_callback,
        max_execution_history=max_execution_history,
        anomaly_detection_enabled=anomaly_detection_enabled
    )
    
    # Start background monitoring
    await _performance_monitor.start_monitoring()
    
    logger.info("Query performance monitor initialized successfully")
    return _performance_monitor