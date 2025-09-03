"""
Performance Dashboard Service for Phase 2 DuckDB Analytics System
===============================================================

Real-time performance monitoring and dashboard data aggregation service
for the complete Phase 2 analytics platform with WebSocket support.

Features:
- Real-time system overview with health status indicators
- Component-specific performance metrics and trends
- Resource utilization charts and capacity planning
- Query performance analytics and optimization insights
- User activity patterns and usage statistics
- Historical performance trend analysis
- Cost analysis and optimization recommendations
- SLA compliance reporting and incident correlation
- Interactive dashboard data with WebSocket streaming
- Customizable metric collection and aggregation
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple, Union
from uuid import uuid4

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.monitoring_service import (
    monitoring_service,
    SystemMetrics,
    PerformanceMetrics,
    HealthReport,
    HealthStatus,
    ComponentHealth
)

logger = logging.getLogger(__name__)


class TimeRange(str, Enum):
    """Time ranges for performance data"""
    REALTIME = "realtime"  # Last 5 minutes
    HOUR = "1h"           # Last hour
    DAY = "24h"           # Last 24 hours
    WEEK = "7d"           # Last 7 days
    MONTH = "30d"         # Last 30 days


class MetricAggregation(str, Enum):
    """Metric aggregation methods"""
    AVERAGE = "avg"
    MINIMUM = "min"
    MAXIMUM = "max"
    SUM = "sum"
    COUNT = "count"
    PERCENTILE_95 = "p95"
    PERCENTILE_99 = "p99"


class ChartType(str, Enum):
    """Chart visualization types"""
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    GAUGE = "gauge"
    HEATMAP = "heatmap"
    SCATTER = "scatter"


@dataclass
class MetricDataPoint:
    """Single metric data point with timestamp"""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class TimeSeriesData:
    """Time series data for a metric"""
    metric_name: str
    data_points: List[MetricDataPoint]
    aggregation: MetricAggregation = MetricAggregation.AVERAGE
    unit: str = ""
    description: str = ""


@dataclass
class SystemOverview:
    """System-wide overview data"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    overall_health: HealthStatus = HealthStatus.UNKNOWN
    total_components: int = 0
    healthy_components: int = 0
    degraded_components: int = 0
    unhealthy_components: int = 0
    critical_components: int = 0
    
    # Key metrics
    system_cpu_usage: float = 0.0
    system_memory_usage: float = 0.0
    system_disk_usage: float = 0.0
    active_users: int = 0
    total_requests_per_second: float = 0.0
    
    # Phase 2 specific metrics
    duckdb_query_rate: float = 0.0
    data_sync_lag: float = 0.0
    parquet_processing_rate: float = 0.0
    analytics_cache_hit_rate: float = 0.0
    
    # Alerts and incidents
    active_alerts: int = 0
    critical_alerts: int = 0
    recent_incidents: int = 0


@dataclass
class ComponentMetrics:
    """Detailed metrics for a specific component"""
    component_name: str
    health_status: HealthStatus
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Performance metrics
    response_time_ms: Optional[float] = None
    throughput: Optional[float] = None
    error_rate: Optional[float] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    
    # Component-specific metrics
    custom_metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Historical data
    response_time_trend: List[MetricDataPoint] = field(default_factory=list)
    throughput_trend: List[MetricDataPoint] = field(default_factory=list)
    error_rate_trend: List[MetricDataPoint] = field(default_factory=list)


@dataclass
class ResourceMetrics:
    """Resource utilization metrics"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # CPU metrics
    cpu_usage_percent: float = 0.0
    cpu_cores: int = 0
    load_average: List[float] = field(default_factory=list)
    
    # Memory metrics
    memory_usage_percent: float = 0.0
    memory_used_gb: float = 0.0
    memory_total_gb: float = 0.0
    memory_available_gb: float = 0.0
    
    # Disk metrics
    disk_usage_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    
    # Network metrics
    network_in_mb: float = 0.0
    network_out_mb: float = 0.0
    
    # Process metrics
    active_processes: int = 0
    zombie_processes: int = 0


@dataclass
class TrendData:
    """Performance trend analysis"""
    metric_name: str
    timerange: TimeRange
    current_value: float
    previous_value: float
    change_percent: float
    trend_direction: str  # "increasing", "decreasing", "stable"
    trend_strength: str   # "weak", "moderate", "strong"
    prediction: Optional[float] = None  # Predicted next value
    recommendation: Optional[str] = None


@dataclass
class CostAnalysis:
    """Cost analysis and optimization data"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Current costs (estimated)
    compute_cost_per_hour: float = 0.0
    storage_cost_per_gb: float = 0.0
    network_cost_per_gb: float = 0.0
    total_estimated_cost_per_day: float = 0.0
    
    # Cost savings from optimizations
    cache_hit_savings: float = 0.0
    data_deduplication_savings: float = 0.0
    query_optimization_savings: float = 0.0
    total_savings: float = 0.0
    
    # Recommendations
    optimization_opportunities: List[str] = field(default_factory=list)
    scaling_recommendations: List[str] = field(default_factory=list)


@dataclass
class DashboardWidget:
    """Individual dashboard widget configuration"""
    widget_id: str
    title: str
    chart_type: ChartType
    metric_name: str
    timerange: TimeRange = TimeRange.HOUR
    aggregation: MetricAggregation = MetricAggregation.AVERAGE
    refresh_interval: int = 30  # seconds
    size: Dict[str, int] = field(default_factory=lambda: {"width": 4, "height": 3})
    position: Dict[str, int] = field(default_factory=lambda: {"x": 0, "y": 0})
    filters: Dict[str, Any] = field(default_factory=dict)
    thresholds: Dict[str, float] = field(default_factory=dict)


class PerformanceDashboardService:
    """
    Comprehensive performance dashboard service for Phase 2 DuckDB analytics system
    
    Provides real-time dashboard data aggregation, performance trend analysis,
    and interactive metrics visualization with WebSocket streaming support.
    """
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self._metric_collectors: Dict[str, Any] = {}
        self._websocket_connections: Set[Any] = set()
        self._dashboard_cache: Dict[str, Any] = {}
        self._cache_ttl = 30  # seconds
        
        # Metric aggregation buffers
        self._metric_buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._aggregated_data: Dict[str, Dict[TimeRange, List[MetricDataPoint]]] = defaultdict(dict)
        
        # Dashboard widgets configuration
        self._default_widgets: List[DashboardWidget] = []
        
        # Background tasks
        self._background_tasks: Set[asyncio.Task] = set()
        self._shutdown_event = asyncio.Event()
        
        # Performance trend analysis
        self._trend_analyzers: Dict[str, Any] = {}
        
        logger.info("PerformanceDashboardService initialized")
    
    async def initialize(self):
        """Initialize dashboard service and background tasks"""
        try:
            # Initialize Redis connection
            self.redis_client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=6379,
                db=6,  # Dedicated DB for dashboard
                decode_responses=True,
                socket_timeout=5.0
            )
            
            # Test Redis connection
            await self.redis_client.ping()
            logger.info("PerformanceDashboardService Redis connection established")
            
            # Initialize default widgets
            await self._create_default_widgets()
            
            # Start background tasks
            await self._start_background_tasks()
            
        except Exception as e:
            logger.error(f"Failed to initialize PerformanceDashboardService: {e}")
            raise
    
    async def _create_default_widgets(self):
        """Create default dashboard widgets"""
        self._default_widgets = [
            # System Overview
            DashboardWidget(
                widget_id="system_health_overview",
                title="System Health Overview",
                chart_type=ChartType.PIE,
                metric_name="component_health_distribution",
                timerange=TimeRange.REALTIME,
                size={"width": 6, "height": 4},
                position={"x": 0, "y": 0}
            ),
            
            # Resource Utilization
            DashboardWidget(
                widget_id="cpu_usage_trend",
                title="CPU Usage",
                chart_type=ChartType.LINE,
                metric_name="system_cpu_usage_percent",
                timerange=TimeRange.HOUR,
                size={"width": 6, "height": 4},
                position={"x": 6, "y": 0},
                thresholds={"warning": 70.0, "critical": 90.0}
            ),
            
            DashboardWidget(
                widget_id="memory_usage_trend",
                title="Memory Usage",
                chart_type=ChartType.LINE,
                metric_name="system_memory_usage_percent",
                timerange=TimeRange.HOUR,
                size={"width": 6, "height": 4},
                position={"x": 0, "y": 4},
                thresholds={"warning": 80.0, "critical": 95.0}
            ),
            
            # DuckDB Analytics
            DashboardWidget(
                widget_id="duckdb_query_performance",
                title="DuckDB Query Performance",
                chart_type=ChartType.LINE,
                metric_name="duckdb_query_duration_avg",
                timerange=TimeRange.HOUR,
                size={"width": 6, "height": 4},
                position={"x": 6, "y": 4},
                thresholds={"warning": 5.0, "critical": 30.0}
            ),
            
            # Data Synchronization
            DashboardWidget(
                widget_id="data_sync_lag",
                title="Data Sync Lag",
                chart_type=ChartType.GAUGE,
                metric_name="sync_lag_seconds",
                timerange=TimeRange.REALTIME,
                size={"width": 4, "height": 3},
                position={"x": 0, "y": 8},
                thresholds={"warning": 120.0, "critical": 300.0}
            ),
            
            # API Performance
            DashboardWidget(
                widget_id="api_response_times",
                title="API Response Times",
                chart_type=ChartType.BAR,
                metric_name="api_response_time_p95",
                timerange=TimeRange.HOUR,
                aggregation=MetricAggregation.PERCENTILE_95,
                size={"width": 4, "height": 3},
                position={"x": 4, "y": 8}
            ),
            
            # Cache Performance
            DashboardWidget(
                widget_id="cache_hit_rate",
                title="Cache Hit Rate",
                chart_type=ChartType.GAUGE,
                metric_name="cache_hit_rate_percent",
                timerange=TimeRange.REALTIME,
                size={"width": 4, "height": 3},
                position={"x": 8, "y": 8},
                thresholds={"critical": 50.0, "warning": 70.0}  # Lower is worse for cache hit rate
            )
        ]
    
    async def _start_background_tasks(self):
        """Start background tasks for dashboard data collection"""
        # Data collection task
        collection_task = asyncio.create_task(self._data_collection_loop())
        self._background_tasks.add(collection_task)
        collection_task.add_done_callback(self._background_tasks.discard)
        
        # Data aggregation task
        aggregation_task = asyncio.create_task(self._data_aggregation_loop())
        self._background_tasks.add(aggregation_task)
        aggregation_task.add_done_callback(self._background_tasks.discard)
        
        # WebSocket broadcast task
        websocket_task = asyncio.create_task(self._websocket_broadcast_loop())
        self._background_tasks.add(websocket_task)
        websocket_task.add_done_callback(self._background_tasks.discard)
        
        # Cache cleanup task
        cleanup_task = asyncio.create_task(self._cache_cleanup_loop())
        self._background_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(self._background_tasks.discard)
        
        logger.info("PerformanceDashboardService background tasks started")
    
    async def _data_collection_loop(self):
        """Background loop for collecting performance data"""
        while not self._shutdown_event.is_set():
            try:
                # Collect data from monitoring service
                system_metrics = await monitoring_service.collect_system_metrics()
                health_report = await monitoring_service.generate_health_report()
                
                # Store collected data
                await self._store_performance_data(system_metrics, health_report)
                
                # Wait before next collection
                await asyncio.sleep(15)  # Collect every 15 seconds
                
            except Exception as e:
                logger.error(f"Error in data collection loop: {e}")
                await asyncio.sleep(30)
    
    async def _data_aggregation_loop(self):
        """Background loop for aggregating collected data"""
        while not self._shutdown_event.is_set():
            try:
                # Aggregate data for different time ranges
                await self._aggregate_metric_data()
                
                # Calculate trends and predictions
                await self._calculate_performance_trends()
                
                # Wait before next aggregation
                await asyncio.sleep(60)  # Aggregate every minute
                
            except Exception as e:
                logger.error(f"Error in data aggregation loop: {e}")
                await asyncio.sleep(120)
    
    async def _websocket_broadcast_loop(self):
        """Background loop for broadcasting real-time data via WebSocket"""
        while not self._shutdown_event.is_set():
            try:
                if self._websocket_connections:
                    # Get real-time dashboard data
                    dashboard_data = await self.get_dashboard_data(TimeRange.REALTIME)
                    
                    # Broadcast to all connected WebSocket clients
                    await self._broadcast_to_websockets({
                        "type": "dashboard_update",
                        "data": dashboard_data,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                # Wait before next broadcast
                await asyncio.sleep(5)  # Broadcast every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in WebSocket broadcast loop: {e}")
                await asyncio.sleep(10)
    
    async def _cache_cleanup_loop(self):
        """Background loop for cleaning up expired cache entries"""
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.utcnow()
                
                # Clean up dashboard cache
                expired_keys = []
                for key, (data, timestamp) in self._dashboard_cache.items():
                    if (current_time - timestamp).seconds > self._cache_ttl:
                        expired_keys.append(key)
                
                for key in expired_keys:
                    del self._dashboard_cache[key]
                
                # Clean up old aggregated data
                cutoff_time = current_time - timedelta(days=7)
                for metric_name in self._aggregated_data:
                    for timerange in self._aggregated_data[metric_name]:
                        self._aggregated_data[metric_name][timerange] = [
                            dp for dp in self._aggregated_data[metric_name][timerange]
                            if dp.timestamp > cutoff_time
                        ]
                
                # Wait before next cleanup
                await asyncio.sleep(300)  # Clean every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in cache cleanup loop: {e}")
                await asyncio.sleep(300)
    
    async def _store_performance_data(self, system_metrics: SystemMetrics, health_report: HealthReport):
        """Store performance data in metric buffers and Redis"""
        try:
            timestamp = datetime.utcnow()
            
            # Store system metrics
            system_data = {
                "cpu_usage_percent": system_metrics.cpu_usage_percent,
                "memory_usage_percent": system_metrics.memory_usage_percent,
                "disk_usage_percent": system_metrics.disk_usage_percent,
                "network_in_mb": system_metrics.network_io_mb.get("bytes_recv_mb", 0),
                "network_out_mb": system_metrics.network_io_mb.get("bytes_sent_mb", 0)
            }
            
            for metric_name, value in system_data.items():
                data_point = MetricDataPoint(timestamp=timestamp, value=value)
                self._metric_buffers[f"system_{metric_name}"].append(data_point)
            
            # Store component health data
            health_distribution = {"healthy": 0, "degraded": 0, "unhealthy": 0, "critical": 0, "unknown": 0}
            for component in health_report.components:
                health_distribution[component.status.value] += 1
            
            for status, count in health_distribution.items():
                data_point = MetricDataPoint(timestamp=timestamp, value=count, labels={"status": status})
                self._metric_buffers[f"component_health_{status}"].append(data_point)
            
            # Store performance metrics
            if health_report.performance_metrics:
                perf_data = {
                    "duckdb_query_duration_avg": health_report.performance_metrics.duckdb_query_duration_avg,
                    "duckdb_active_connections": health_report.performance_metrics.duckdb_active_connections,
                    "duckdb_memory_usage_mb": health_report.performance_metrics.duckdb_memory_usage_mb,
                    "sync_lag_seconds": health_report.performance_metrics.sync_lag_seconds,
                    "sync_operations_total": health_report.performance_metrics.sync_operations_total,
                    "query_cache_hit_rate": health_report.performance_metrics.query_cache_hit_rate,
                    "analytics_requests_per_second": health_report.performance_metrics.analytics_requests_per_second,
                    "parquet_processing_rate": health_report.performance_metrics.parquet_processing_rate
                }
                
                for metric_name, value in perf_data.items():
                    if value is not None:
                        data_point = MetricDataPoint(timestamp=timestamp, value=value)
                        self._metric_buffers[metric_name].append(data_point)
            
            # Store in Redis for persistence
            if self.redis_client:
                redis_data = {
                    "timestamp": timestamp.isoformat(),
                    "system_metrics": asdict(system_metrics),
                    "health_distribution": health_distribution,
                    "performance_metrics": asdict(health_report.performance_metrics) if health_report.performance_metrics else {}
                }
                
                await self.redis_client.setex(
                    f"dashboard_data:{timestamp.timestamp()}",
                    3600,  # 1 hour TTL
                    json.dumps(redis_data, default=str)
                )
                
                # Keep track of recent data points
                await self.redis_client.zadd(
                    "dashboard_timestamps",
                    {timestamp.isoformat(): timestamp.timestamp()}
                )
                
                # Clean up old timestamps (keep 24 hours)
                cutoff = (timestamp - timedelta(hours=24)).timestamp()
                await self.redis_client.zremrangebyscore("dashboard_timestamps", 0, cutoff)
            
        except Exception as e:
            logger.error(f"Error storing performance data: {e}")
    
    async def _aggregate_metric_data(self):
        """Aggregate metric data for different time ranges"""
        try:
            current_time = datetime.utcnow()
            
            for metric_name, buffer in self._metric_buffers.items():
                if not buffer:
                    continue
                
                # Aggregate for different time ranges
                for timerange in TimeRange:
                    if timerange == TimeRange.REALTIME:
                        cutoff_time = current_time - timedelta(minutes=5)
                    elif timerange == TimeRange.HOUR:
                        cutoff_time = current_time - timedelta(hours=1)
                    elif timerange == TimeRange.DAY:
                        cutoff_time = current_time - timedelta(hours=24)
                    elif timerange == TimeRange.WEEK:
                        cutoff_time = current_time - timedelta(days=7)
                    else:  # MONTH
                        cutoff_time = current_time - timedelta(days=30)
                    
                    # Filter data points for this time range
                    filtered_points = [dp for dp in buffer if dp.timestamp >= cutoff_time]
                    
                    if filtered_points:
                        # Store aggregated data
                        if metric_name not in self._aggregated_data:
                            self._aggregated_data[metric_name] = {}
                        
                        self._aggregated_data[metric_name][timerange] = filtered_points
            
        except Exception as e:
            logger.error(f"Error aggregating metric data: {e}")
    
    async def _calculate_performance_trends(self):
        """Calculate performance trends and predictions"""
        try:
            current_time = datetime.utcnow()
            
            for metric_name in self._aggregated_data:
                # Get hourly and daily data for trend analysis
                hourly_data = self._aggregated_data[metric_name].get(TimeRange.HOUR, [])
                daily_data = self._aggregated_data[metric_name].get(TimeRange.DAY, [])
                
                if len(hourly_data) >= 2 and len(daily_data) >= 2:
                    # Calculate trend for this metric
                    trend = await self._analyze_metric_trend(metric_name, hourly_data, daily_data)
                    
                    # Store trend analysis
                    if self.redis_client:
                        await self.redis_client.setex(
                            f"trend_analysis:{metric_name}",
                            1800,  # 30 minutes TTL
                            json.dumps(asdict(trend), default=str)
                        )
            
        except Exception as e:
            logger.error(f"Error calculating performance trends: {e}")
    
    async def _analyze_metric_trend(
        self,
        metric_name: str,
        hourly_data: List[MetricDataPoint],
        daily_data: List[MetricDataPoint]
    ) -> TrendData:
        """Analyze trend for a specific metric"""
        try:
            # Calculate current and previous values
            current_value = hourly_data[-1].value if hourly_data else 0
            hour_ago_value = hourly_data[0].value if len(hourly_data) > 1 else current_value
            
            # Calculate change percentage
            if hour_ago_value != 0:
                change_percent = ((current_value - hour_ago_value) / hour_ago_value) * 100
            else:
                change_percent = 0
            
            # Determine trend direction and strength
            if abs(change_percent) < 5:
                trend_direction = "stable"
                trend_strength = "weak"
            elif change_percent > 0:
                trend_direction = "increasing"
                trend_strength = "strong" if change_percent > 25 else "moderate"
            else:
                trend_direction = "decreasing"
                trend_strength = "strong" if change_percent < -25 else "moderate"
            
            # Simple linear prediction (in production, use more sophisticated methods)
            prediction = None
            if len(daily_data) >= 5:
                values = [dp.value for dp in daily_data[-5:]]
                # Simple linear regression
                n = len(values)
                sum_x = sum(range(n))
                sum_y = sum(values)
                sum_xy = sum(i * values[i] for i in range(n))
                sum_x2 = sum(i * i for i in range(n))
                
                if n * sum_x2 - sum_x * sum_x != 0:
                    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
                    intercept = (sum_y - slope * sum_x) / n
                    prediction = slope * n + intercept
            
            # Generate recommendation
            recommendation = self._generate_trend_recommendation(
                metric_name, current_value, change_percent, trend_direction
            )
            
            return TrendData(
                metric_name=metric_name,
                timerange=TimeRange.HOUR,
                current_value=current_value,
                previous_value=hour_ago_value,
                change_percent=change_percent,
                trend_direction=trend_direction,
                trend_strength=trend_strength,
                prediction=prediction,
                recommendation=recommendation
            )
            
        except Exception as e:
            logger.error(f"Error analyzing trend for {metric_name}: {e}")
            return TrendData(
                metric_name=metric_name,
                timerange=TimeRange.HOUR,
                current_value=0,
                previous_value=0,
                change_percent=0,
                trend_direction="unknown",
                trend_strength="unknown"
            )
    
    def _generate_trend_recommendation(
        self,
        metric_name: str,
        current_value: float,
        change_percent: float,
        trend_direction: str
    ) -> str:
        """Generate recommendation based on trend analysis"""
        try:
            recommendations = []
            
            if "cpu" in metric_name.lower() and current_value > 80:
                if trend_direction == "increasing":
                    recommendations.append("CPU usage is high and increasing - consider scaling up or optimizing workloads")
                else:
                    recommendations.append("CPU usage is high but stable - monitor closely")
            
            elif "memory" in metric_name.lower() and current_value > 85:
                if trend_direction == "increasing":
                    recommendations.append("Memory usage is high and increasing - investigate memory leaks or scale up")
                else:
                    recommendations.append("Memory usage is high - consider optimizing memory allocation")
            
            elif "query_duration" in metric_name.lower() and current_value > 10:
                recommendations.append("Query performance is degraded - consider query optimization or index tuning")
            
            elif "sync_lag" in metric_name.lower() and current_value > 300:
                recommendations.append("Data sync lag is high - check sync service health and network connectivity")
            
            elif "cache_hit_rate" in metric_name.lower() and current_value < 70:
                recommendations.append("Cache hit rate is low - review caching strategy and TTL settings")
            
            elif change_percent > 50 and trend_direction == "increasing":
                recommendations.append(f"Rapid increase detected in {metric_name} - investigate cause")
            
            elif change_percent < -50 and trend_direction == "decreasing":
                recommendations.append(f"Significant decrease in {metric_name} - verify if expected")
            
            return "; ".join(recommendations) if recommendations else "No specific recommendations at this time"
            
        except Exception as e:
            logger.error(f"Error generating recommendation: {e}")
            return "Unable to generate recommendation"
    
    async def _broadcast_to_websockets(self, data: Dict[str, Any]):
        """Broadcast data to all WebSocket connections"""
        if not self._websocket_connections:
            return
        
        message = json.dumps(data, default=str)
        disconnected_connections = set()
        
        for websocket in self._websocket_connections:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                disconnected_connections.add(websocket)
        
        # Remove disconnected connections
        self._websocket_connections -= disconnected_connections
    
    # Public API methods
    
    async def get_system_overview(self) -> SystemOverview:
        """Get system-wide overview data"""
        try:
            cache_key = "system_overview"
            
            # Check cache
            if cache_key in self._dashboard_cache:
                data, timestamp = self._dashboard_cache[cache_key]
                if (datetime.utcnow() - timestamp).seconds < self._cache_ttl:
                    return data
            
            # Generate fresh data
            health_report = await monitoring_service.generate_health_report()
            system_metrics = await monitoring_service.collect_system_metrics()
            
            # Count component health statuses
            component_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0, "critical": 0, "unknown": 0}
            for component in health_report.components:
                component_counts[component.status.value] += 1
            
            # Calculate active users (simplified - would integrate with user session tracking)
            active_users = await self._get_active_users_count()
            
            # Calculate request rate (from API metrics)
            total_requests_per_second = await self._get_requests_per_second()
            
            # Phase 2 specific metrics
            perf_metrics = health_report.performance_metrics
            duckdb_query_rate = self._calculate_query_rate() if perf_metrics else 0.0
            
            overview = SystemOverview(
                overall_health=health_report.overall_status,
                total_components=len(health_report.components),
                healthy_components=component_counts["healthy"],
                degraded_components=component_counts["degraded"],
                unhealthy_components=component_counts["unhealthy"],
                critical_components=component_counts["critical"],
                system_cpu_usage=system_metrics.cpu_usage_percent,
                system_memory_usage=system_metrics.memory_usage_percent,
                system_disk_usage=system_metrics.disk_usage_percent,
                active_users=active_users,
                total_requests_per_second=total_requests_per_second,
                duckdb_query_rate=duckdb_query_rate,
                data_sync_lag=perf_metrics.sync_lag_seconds if perf_metrics else 0.0,
                parquet_processing_rate=perf_metrics.parquet_processing_rate if perf_metrics else 0.0,
                analytics_cache_hit_rate=perf_metrics.query_cache_hit_rate if perf_metrics else 0.0,
                active_alerts=len(health_report.anomalies),
                critical_alerts=len([a for a in health_report.anomalies if a.severity.value == "critical"]),
                recent_incidents=await self._get_recent_incidents_count()
            )
            
            # Cache result
            self._dashboard_cache[cache_key] = (overview, datetime.utcnow())
            
            return overview
            
        except Exception as e:
            logger.error(f"Error getting system overview: {e}")
            return SystemOverview()
    
    async def get_component_metrics(self, component: str) -> ComponentMetrics:
        """Get detailed metrics for a specific component"""
        try:
            cache_key = f"component_metrics_{component}"
            
            # Check cache
            if cache_key in self._dashboard_cache:
                data, timestamp = self._dashboard_cache[cache_key]
                if (datetime.utcnow() - timestamp).seconds < self._cache_ttl:
                    return data
            
            # Get component health from monitoring service
            health_status = await monitoring_service.check_service_health(component)
            
            # Get component from health report
            health_report = await monitoring_service.generate_health_report()
            component_health = next((c for c in health_report.components if c.name == component), None)
            
            if not component_health:
                return ComponentMetrics(component_name=component, health_status=HealthStatus.UNKNOWN)
            
            # Extract metrics
            metrics = ComponentMetrics(
                component_name=component,
                health_status=component_health.status,
                response_time_ms=component_health.response_time_ms,
                custom_metrics=component_health.metrics
            )
            
            # Get historical trend data
            if component in self._aggregated_data:
                hourly_data = self._aggregated_data[component].get(TimeRange.HOUR, [])
                if hourly_data:
                    metrics.response_time_trend = hourly_data[-20:]  # Last 20 points
            
            # Cache result
            self._dashboard_cache[cache_key] = (metrics, datetime.utcnow())
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error getting component metrics for {component}: {e}")
            return ComponentMetrics(component_name=component, health_status=HealthStatus.UNKNOWN)
    
    async def get_performance_trends(self, timerange: TimeRange = TimeRange.DAY) -> Dict[str, TrendData]:
        """Get performance trends for specified timerange"""
        try:
            cache_key = f"performance_trends_{timerange.value}"
            
            # Check cache
            if cache_key in self._dashboard_cache:
                data, timestamp = self._dashboard_cache[cache_key]
                if (datetime.utcnow() - timestamp).seconds < self._cache_ttl:
                    return data
            
            trends = {}
            
            # Get trends from Redis
            if self.redis_client:
                trend_keys = await self.redis_client.keys("trend_analysis:*")
                
                for key in trend_keys:
                    metric_name = key.split(":")[-1]
                    trend_data = await self.redis_client.get(key)
                    
                    if trend_data:
                        try:
                            trend_dict = json.loads(trend_data)
                            trends[metric_name] = TrendData(**trend_dict)
                        except (json.JSONDecodeError, TypeError):
                            continue
            
            # Cache result
            self._dashboard_cache[cache_key] = (trends, datetime.utcnow())
            
            return trends
            
        except Exception as e:
            logger.error(f"Error getting performance trends: {e}")
            return {}
    
    async def get_resource_utilization(self) -> ResourceMetrics:
        """Get resource utilization metrics"""
        try:
            cache_key = "resource_utilization"
            
            # Check cache
            if cache_key in self._dashboard_cache:
                data, timestamp = self._dashboard_cache[cache_key]
                if (datetime.utcnow() - timestamp).seconds < self._cache_ttl:
                    return data
            
            # Get system metrics
            system_metrics = await monitoring_service.collect_system_metrics()
            
            # Convert to ResourceMetrics format
            resource_metrics = ResourceMetrics(
                cpu_usage_percent=system_metrics.cpu_usage_percent,
                cpu_cores=len(system_metrics.load_average) if system_metrics.load_average else 1,
                load_average=system_metrics.load_average,
                memory_usage_percent=system_metrics.memory_usage_percent,
                disk_usage_percent=system_metrics.disk_usage_percent,
                network_in_mb=system_metrics.network_io_mb.get("bytes_recv_mb", 0),
                network_out_mb=system_metrics.network_io_mb.get("bytes_sent_mb", 0)
            )
            
            # Cache result
            self._dashboard_cache[cache_key] = (resource_metrics, datetime.utcnow())
            
            return resource_metrics
            
        except Exception as e:
            logger.error(f"Error getting resource utilization: {e}")
            return ResourceMetrics()
    
    async def get_cost_analysis(self) -> CostAnalysis:
        """Get cost analysis and optimization recommendations"""
        try:
            cache_key = "cost_analysis"
            
            # Check cache
            if cache_key in self._dashboard_cache:
                data, timestamp = self._dashboard_cache[cache_key]
                if (datetime.utcnow() - timestamp).seconds < self._cache_ttl * 10:  # Cache longer for cost analysis
                    return data
            
            # Get resource metrics for cost calculation
            resource_metrics = await self.get_resource_utilization()
            system_overview = await self.get_system_overview()
            
            # Calculate estimated costs (simplified model)
            compute_cost_per_hour = self._calculate_compute_cost(resource_metrics)
            storage_cost_per_gb = 0.023  # Example: $0.023 per GB per month
            network_cost_per_gb = 0.09  # Example: $0.09 per GB
            
            # Calculate savings from optimizations
            cache_hit_savings = system_overview.analytics_cache_hit_rate * 0.001  # $0.001 per cache hit
            data_deduplication_savings = await self._calculate_deduplication_savings()
            
            cost_analysis = CostAnalysis(
                compute_cost_per_hour=compute_cost_per_hour,
                storage_cost_per_gb=storage_cost_per_gb,
                network_cost_per_gb=network_cost_per_gb,
                total_estimated_cost_per_day=compute_cost_per_hour * 24,
                cache_hit_savings=cache_hit_savings,
                data_deduplication_savings=data_deduplication_savings,
                total_savings=cache_hit_savings + data_deduplication_savings,
                optimization_opportunities=await self._get_optimization_opportunities(),
                scaling_recommendations=await self._get_scaling_recommendations()
            )
            
            # Cache result
            self._dashboard_cache[cache_key] = (cost_analysis, datetime.utcnow())
            
            return cost_analysis
            
        except Exception as e:
            logger.error(f"Error getting cost analysis: {e}")
            return CostAnalysis()
    
    async def get_dashboard_data(self, timerange: TimeRange = TimeRange.HOUR) -> Dict[str, Any]:
        """Get comprehensive dashboard data"""
        try:
            dashboard_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "timerange": timerange.value,
                "system_overview": asdict(await self.get_system_overview()),
                "resource_utilization": asdict(await self.get_resource_utilization()),
                "performance_trends": {
                    name: asdict(trend) for name, trend in (await self.get_performance_trends(timerange)).items()
                },
                "cost_analysis": asdict(await self.get_cost_analysis()),
                "widgets": [asdict(widget) for widget in self._default_widgets]
            }
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}
    
    async def get_widget_data(self, widget_id: str) -> Dict[str, Any]:
        """Get data for a specific dashboard widget"""
        try:
            widget = next((w for w in self._default_widgets if w.widget_id == widget_id), None)
            if not widget:
                return {"error": "Widget not found"}
            
            # Get metric data for the widget
            metric_data = self._aggregated_data.get(widget.metric_name, {})
            timerange_data = metric_data.get(widget.timerange, [])
            
            # Format data for the specific chart type
            if widget.chart_type == ChartType.LINE:
                chart_data = {
                    "labels": [dp.timestamp.isoformat() for dp in timerange_data],
                    "values": [dp.value for dp in timerange_data],
                    "unit": widget.metric_name.split("_")[-1] if "_" in widget.metric_name else ""
                }
            elif widget.chart_type == ChartType.GAUGE:
                current_value = timerange_data[-1].value if timerange_data else 0
                chart_data = {
                    "value": current_value,
                    "min": 0,
                    "max": 100 if "percent" in widget.metric_name else max(100, current_value * 1.2),
                    "thresholds": widget.thresholds
                }
            elif widget.chart_type == ChartType.PIE:
                # Aggregate values by labels
                label_totals = defaultdict(float)
                for dp in timerange_data:
                    label = dp.labels.get("status", "unknown")
                    label_totals[label] += dp.value
                
                chart_data = {
                    "labels": list(label_totals.keys()),
                    "values": list(label_totals.values())
                }
            else:
                chart_data = {
                    "labels": [dp.timestamp.isoformat() for dp in timerange_data],
                    "values": [dp.value for dp in timerange_data]
                }
            
            return {
                "widget_id": widget_id,
                "title": widget.title,
                "chart_type": widget.chart_type.value,
                "data": chart_data,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting widget data for {widget_id}: {e}")
            return {"error": str(e)}
    
    # Helper methods
    
    async def _get_active_users_count(self) -> int:
        """Get count of active users (simplified implementation)"""
        try:
            if self.redis_client:
                # Count active sessions in Redis
                active_sessions = await self.redis_client.keys("session:*")
                return len(active_sessions)
            return 0
        except Exception:
            return 0
    
    async def _get_requests_per_second(self) -> float:
        """Get requests per second rate"""
        try:
            if self.redis_client:
                # Get request count from last minute
                current_minute = int(time.time() // 60)
                request_count = await self.redis_client.get(f"api_requests:{current_minute}")
                return float(request_count) / 60 if request_count else 0.0
            return 0.0
        except Exception:
            return 0.0
    
    def _calculate_query_rate(self) -> float:
        """Calculate DuckDB query rate"""
        try:
            # Get recent query metrics
            duckdb_metrics = self._metric_buffers.get("duckdb_queries_total", deque())
            if len(duckdb_metrics) >= 2:
                recent_total = duckdb_metrics[-1].value
                previous_total = duckdb_metrics[-2].value
                time_diff = (duckdb_metrics[-1].timestamp - duckdb_metrics[-2].timestamp).seconds
                
                if time_diff > 0:
                    return (recent_total - previous_total) / time_diff
            
            return 0.0
        except Exception:
            return 0.0
    
    async def _get_recent_incidents_count(self) -> int:
        """Get count of recent incidents"""
        try:
            # This would integrate with incident management system
            # For now, return count of recent critical anomalies
            health_report = await monitoring_service.generate_health_report()
            recent_incidents = len([a for a in health_report.anomalies 
                                 if a.severity.value == "critical" and 
                                 (datetime.utcnow() - a.detected_at).hours < 24])
            return recent_incidents
        except Exception:
            return 0
    
    def _calculate_compute_cost(self, resource_metrics: ResourceMetrics) -> float:
        """Calculate estimated compute cost per hour"""
        try:
            # Simplified cost model based on resource usage
            base_cost = 0.10  # $0.10 per hour base
            cpu_cost = resource_metrics.cpu_usage_percent / 100 * 0.05
            memory_cost = resource_metrics.memory_usage_percent / 100 * 0.03
            
            return base_cost + cpu_cost + memory_cost
        except Exception:
            return 0.10
    
    async def _calculate_deduplication_savings(self) -> float:
        """Calculate estimated savings from data deduplication"""
        try:
            # This would query the database for deduplication statistics
            # For now, return a simplified estimate
            return 0.05  # $0.05 per day estimated savings
        except Exception:
            return 0.0
    
    async def _get_optimization_opportunities(self) -> List[str]:
        """Get list of optimization opportunities"""
        opportunities = []
        
        try:
            resource_metrics = await self.get_resource_utilization()
            system_overview = await self.get_system_overview()
            
            if resource_metrics.cpu_usage_percent > 80:
                opportunities.append("High CPU usage - consider query optimization or scaling")
            
            if resource_metrics.memory_usage_percent > 85:
                opportunities.append("High memory usage - review memory allocation and caching")
            
            if system_overview.analytics_cache_hit_rate < 70:
                opportunities.append("Low cache hit rate - optimize caching strategy")
            
            if system_overview.data_sync_lag > 300:
                opportunities.append("High data sync lag - optimize sync processes")
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error getting optimization opportunities: {e}")
            return ["Unable to analyze optimization opportunities"]
    
    async def _get_scaling_recommendations(self) -> List[str]:
        """Get scaling recommendations"""
        recommendations = []
        
        try:
            trends = await self.get_performance_trends()
            
            for metric_name, trend in trends.items():
                if "cpu" in metric_name and trend.trend_direction == "increasing" and trend.current_value > 70:
                    recommendations.append("Consider horizontal scaling - CPU trends increasing")
                
                elif "memory" in metric_name and trend.trend_direction == "increasing" and trend.current_value > 80:
                    recommendations.append("Consider adding memory or optimizing memory usage")
                
                elif "query_duration" in metric_name and trend.trend_direction == "increasing":
                    recommendations.append("Query performance degrading - consider read replicas or query optimization")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error getting scaling recommendations: {e}")
            return ["Unable to generate scaling recommendations"]
    
    # WebSocket management
    
    async def add_websocket_connection(self, websocket):
        """Add a WebSocket connection for real-time updates"""
        self._websocket_connections.add(websocket)
        logger.info(f"Added WebSocket connection. Total: {len(self._websocket_connections)}")
    
    async def remove_websocket_connection(self, websocket):
        """Remove a WebSocket connection"""
        self._websocket_connections.discard(websocket)
        logger.info(f"Removed WebSocket connection. Total: {len(self._websocket_connections)}")
    
    async def shutdown(self):
        """Cleanup dashboard service resources"""
        try:
            # Signal shutdown to background tasks
            self._shutdown_event.set()
            
            # Wait for background tasks to complete
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
            
            # Close WebSocket connections
            for websocket in self._websocket_connections:
                try:
                    await websocket.close()
                except Exception:
                    pass
            
            # Close Redis connection
            if self.redis_client:
                await self.redis_client.close()
            
            logger.info("PerformanceDashboardService shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during PerformanceDashboardService shutdown: {e}")


# Global dashboard service instance
performance_dashboard_service = PerformanceDashboardService()


# FastAPI dependency
async def get_performance_dashboard_service() -> PerformanceDashboardService:
    """FastAPI dependency for dashboard service"""
    if not performance_dashboard_service.redis_client:
        await performance_dashboard_service.initialize()
    return performance_dashboard_service