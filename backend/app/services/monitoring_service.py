"""
Comprehensive Monitoring Service for Phase 2 DuckDB Analytics System
================================================================

Unified monitoring and metrics collection for the complete Phase 2 analytics platform:
- DuckDBService: Analytics database with circuit breaker patterns
- ParquetPipeline: Batch processing with resource monitoring  
- DataSyncService: Dual-write consistency with CDC monitoring
- HybridQueryRouter: Intelligent OLTP/OLAP routing with performance tracking
- Analytics API: 24 endpoints with real-time WebSocket features
- QueryOptimizationEngine: Multi-level caching with performance monitoring

This service provides:
- System health monitoring with component dependency mapping
- Performance metrics collection and anomaly detection
- Resource utilization tracking and alerting
- SLA compliance monitoring
- Real-time dashboard data aggregation
- Service dependency health propagation
"""

import asyncio
import json
import logging
import psutil
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import hashlib

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from app.core.config import settings
from app.core.database import get_db
from app.services.duckdb_service import duckdb_service, DuckDBService
from app.services.meilisearch_service import MeilisearchService

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ComponentType(str, Enum):
    """Types of system components"""
    DATABASE = "database"
    SERVICE = "service"
    API = "api"
    CACHE = "cache"
    SEARCH = "search"
    ANALYTICS = "analytics"
    INFRASTRUCTURE = "infrastructure"


class MetricType(str, Enum):
    """Types of metrics collected"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class ComponentHealth:
    """Health status of a system component"""
    name: str
    component_type: ComponentType
    status: HealthStatus
    response_time_ms: Optional[float] = None
    error_rate: Optional[float] = None
    last_check: datetime = field(default_factory=datetime.utcnow)
    metrics: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)


@dataclass
class SystemMetrics:
    """System-wide metrics"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    cpu_usage_percent: float = 0.0
    memory_usage_percent: float = 0.0
    disk_usage_percent: float = 0.0
    network_io_mb: Dict[str, float] = field(default_factory=dict)
    load_average: List[float] = field(default_factory=list)
    active_connections: Dict[str, int] = field(default_factory=dict)
    queue_depths: Dict[str, int] = field(default_factory=dict)


@dataclass
class PerformanceMetrics:
    """Performance metrics for analytics components"""
    duckdb_query_duration_avg: float = 0.0
    duckdb_active_connections: int = 0
    duckdb_memory_usage_mb: float = 0.0
    sync_lag_seconds: float = 0.0
    sync_operations_total: int = 0
    sync_failures_total: int = 0
    query_cache_hit_rate: float = 0.0
    analytics_requests_per_second: float = 0.0
    parquet_processing_rate: float = 0.0
    hybrid_query_routing_efficiency: float = 0.0


@dataclass
class Anomaly:
    """Detected system anomaly"""
    id: str
    component: str
    metric: str
    severity: AlertSeverity
    description: str
    current_value: Any
    expected_range: Tuple[Any, Any]
    detected_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    correlation_id: Optional[str] = None


@dataclass
class HealthReport:
    """Comprehensive system health report"""
    overall_status: HealthStatus
    timestamp: datetime = field(default_factory=datetime.utcnow)
    components: List[ComponentHealth] = field(default_factory=list)
    system_metrics: Optional[SystemMetrics] = None
    performance_metrics: Optional[PerformanceMetrics] = None
    anomalies: List[Anomaly] = field(default_factory=list)
    sla_compliance: Dict[str, float] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


class MonitoringService:
    """
    Comprehensive monitoring service for Phase 2 DuckDB analytics system
    
    Provides unified monitoring, metrics collection, health checks, and anomaly detection
    for all Phase 2 components with real-time dashboard integration.
    """
    
    def __init__(self):
        self.redis_client: Optional[aioredis.Redis] = None
        self._component_registry: Dict[str, ComponentHealth] = {}
        self._metrics_buffer: List[Dict[str, Any]] = []
        self._max_buffer_size = 1000
        self._health_cache_ttl = 30  # seconds
        self._performance_history: Dict[str, List[Tuple[datetime, float]]] = {}
        self._anomaly_detection_enabled = True
        
        # Performance thresholds
        self._thresholds = {
            "duckdb_query_duration_critical": 30.0,  # seconds
            "duckdb_query_duration_warning": 10.0,
            "memory_usage_critical": 90.0,  # percent
            "memory_usage_warning": 80.0,
            "cpu_usage_critical": 90.0,
            "cpu_usage_warning": 75.0,
            "disk_usage_critical": 95.0,
            "disk_usage_warning": 85.0,
            "sync_lag_critical": 300.0,  # seconds
            "sync_lag_warning": 120.0,
            "cache_hit_rate_critical": 50.0,  # percent
            "cache_hit_rate_warning": 70.0,
        }
        
        logger.info("MonitoringService initialized with Phase 2 DuckDB analytics monitoring")
    
    async def initialize(self):
        """Initialize monitoring service and Redis connection"""
        try:
            self.redis_client = aioredis.Redis(
                host=settings.REDIS_HOST,
                port=6379,
                db=3,  # Dedicated DB for monitoring
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0
            )
            
            # Test Redis connection
            await self.redis_client.ping()
            logger.info("MonitoringService Redis connection established")
            
            # Initialize component registry
            await self._initialize_component_registry()
            
        except Exception as e:
            logger.error(f"Failed to initialize MonitoringService: {e}")
            raise
    
    async def _initialize_component_registry(self):
        """Initialize registry of all Phase 2 components"""
        components = [
            ComponentHealth(
                name="postgresql",
                component_type=ComponentType.DATABASE,
                status=HealthStatus.UNKNOWN,
                dependencies=[]
            ),
            ComponentHealth(
                name="duckdb",
                component_type=ComponentType.ANALYTICS,
                status=HealthStatus.UNKNOWN,
                dependencies=[]
            ),
            ComponentHealth(
                name="redis",
                component_type=ComponentType.CACHE,
                status=HealthStatus.UNKNOWN,
                dependencies=[]
            ),
            ComponentHealth(
                name="meilisearch",
                component_type=ComponentType.SEARCH,
                status=HealthStatus.UNKNOWN,
                dependencies=[]
            ),
            ComponentHealth(
                name="data_sync_service",
                component_type=ComponentType.SERVICE,
                status=HealthStatus.UNKNOWN,
                dependencies=["postgresql", "duckdb"]
            ),
            ComponentHealth(
                name="hybrid_query_router",
                component_type=ComponentType.SERVICE,
                status=HealthStatus.UNKNOWN,
                dependencies=["postgresql", "duckdb", "redis"]
            ),
            ComponentHealth(
                name="parquet_pipeline",
                component_type=ComponentType.SERVICE,
                status=HealthStatus.UNKNOWN,
                dependencies=["duckdb"]
            ),
            ComponentHealth(
                name="query_optimization_engine",
                component_type=ComponentType.SERVICE,
                status=HealthStatus.UNKNOWN,
                dependencies=["redis", "duckdb"]
            ),
            ComponentHealth(
                name="analytics_api",
                component_type=ComponentType.API,
                status=HealthStatus.UNKNOWN,
                dependencies=["duckdb", "postgresql", "redis"]
            ),
            ComponentHealth(
                name="firecrawl_api",
                component_type=ComponentType.API,
                status=HealthStatus.UNKNOWN,
                dependencies=[]
            ),
            ComponentHealth(
                name="celery_workers",
                component_type=ComponentType.SERVICE,
                status=HealthStatus.UNKNOWN,
                dependencies=["redis", "postgresql"]
            )
        ]
        
        for component in components:
            self._component_registry[component.name] = component
    
    async def collect_system_metrics(self) -> SystemMetrics:
        """Collect comprehensive system metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            
            # Network I/O
            network = psutil.net_io_counters()
            network_io = {
                "bytes_sent_mb": network.bytes_sent / (1024 * 1024),
                "bytes_recv_mb": network.bytes_recv / (1024 * 1024)
            }
            
            # Load average (Unix/Linux only)
            load_avg = []
            if hasattr(psutil, "getloadavg"):
                load_avg = list(psutil.getloadavg())
            
            # Active connections from component health checks
            active_connections = {}
            for name, component in self._component_registry.items():
                if "active_connections" in component.metrics:
                    active_connections[name] = component.metrics["active_connections"]
            
            # Queue depths
            queue_depths = await self._collect_queue_depths()
            
            return SystemMetrics(
                cpu_usage_percent=cpu_percent,
                memory_usage_percent=memory_percent,
                disk_usage_percent=disk_percent,
                network_io_mb=network_io,
                load_average=load_avg,
                active_connections=active_connections,
                queue_depths=queue_depths
            )
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return SystemMetrics()
    
    async def _collect_queue_depths(self) -> Dict[str, int]:
        """Collect queue depths from various services"""
        queue_depths = {}
        
        try:
            if self.redis_client:
                # Celery queues
                for queue_name in ["celery", "scraping", "indexing", "analytics"]:
                    try:
                        length = await self.redis_client.llen(queue_name)
                        queue_depths[f"celery_{queue_name}"] = length
                    except Exception:
                        pass
                
                # Custom analytics queues
                for queue_name in ["sync_operations", "parquet_jobs", "query_optimization"]:
                    try:
                        length = await self.redis_client.llen(queue_name)
                        queue_depths[f"analytics_{queue_name}"] = length
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Error collecting queue depths: {e}")
        
        return queue_depths
    
    async def check_service_health(self, service: str) -> HealthStatus:
        """Check health of a specific service component"""
        if service not in self._component_registry:
            logger.warning(f"Unknown service: {service}")
            return HealthStatus.UNKNOWN
        
        component = self._component_registry[service]
        
        try:
            if service == "postgresql":
                component = await self._check_postgresql_health(component)
            elif service == "duckdb":
                component = await self._check_duckdb_health(component)
            elif service == "redis":
                component = await self._check_redis_health(component)
            elif service == "meilisearch":
                component = await self._check_meilisearch_health(component)
            elif service == "data_sync_service":
                component = await self._check_data_sync_health(component)
            elif service == "hybrid_query_router":
                component = await self._check_hybrid_query_router_health(component)
            elif service == "parquet_pipeline":
                component = await self._check_parquet_pipeline_health(component)
            elif service == "analytics_api":
                component = await self._check_analytics_api_health(component)
            elif service == "firecrawl_api":
                component = await self._check_firecrawl_health(component)
            elif service == "celery_workers":
                component = await self._check_celery_health(component)
            else:
                component.status = HealthStatus.UNKNOWN
                component.issues.append(f"Health check not implemented for {service}")
            
            component.last_check = datetime.utcnow()
            self._component_registry[service] = component
            
            return component.status
            
        except Exception as e:
            logger.error(f"Health check failed for {service}: {e}")
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"Health check error: {str(e)}")
            return HealthStatus.CRITICAL
    
    async def _check_postgresql_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check PostgreSQL database health"""
        try:
            start_time = time.time()
            
            async for db in get_db():
                # Test basic connectivity
                await db.execute(text("SELECT 1"))
                
                # Check active connections
                result = await db.execute(
                    text("SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active'")
                )
                active_connections = result.scalar() or 0
                
                # Check database size
                db_size_result = await db.execute(
                    text("SELECT pg_database_size(current_database())")
                )
                db_size_bytes = db_size_result.scalar() or 0
                
                # Check for long-running queries
                long_queries_result = await db.execute(
                    text("""
                        SELECT COUNT(*) 
                        FROM pg_stat_activity 
                        WHERE state = 'active' 
                        AND query_start < NOW() - INTERVAL '5 minutes'
                        AND query NOT LIKE '%pg_stat_activity%'
                    """)
                )
                long_queries = long_queries_result.scalar() or 0
                
                response_time = (time.time() - start_time) * 1000
                
                component.response_time_ms = response_time
                component.metrics = {
                    "active_connections": active_connections,
                    "database_size_mb": db_size_bytes / (1024 * 1024),
                    "long_running_queries": long_queries,
                    "response_time_ms": response_time
                }
                
                # Health evaluation
                component.issues.clear()
                component.warnings.clear()
                
                if response_time > 1000:  # 1 second
                    component.status = HealthStatus.CRITICAL
                    component.issues.append(f"Slow response time: {response_time:.0f}ms")
                elif response_time > 500:  # 500ms
                    component.status = HealthStatus.DEGRADED
                    component.warnings.append(f"Elevated response time: {response_time:.0f}ms")
                else:
                    component.status = HealthStatus.HEALTHY
                
                if active_connections > 80:
                    component.warnings.append(f"High connection count: {active_connections}")
                    if component.status == HealthStatus.HEALTHY:
                        component.status = HealthStatus.DEGRADED
                
                if long_queries > 0:
                    component.warnings.append(f"Long-running queries: {long_queries}")
                    if component.status == HealthStatus.HEALTHY:
                        component.status = HealthStatus.DEGRADED
                
                break
                
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"PostgreSQL connection failed: {str(e)}")
        
        return component
    
    async def _check_duckdb_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check DuckDB analytics database health"""
        try:
            start_time = time.time()
            
            # Get DuckDB service health
            health_data = await duckdb_service.health_check()
            
            response_time = (time.time() - start_time) * 1000
            
            component.response_time_ms = response_time
            component.metrics = health_data.get("metrics", {})
            component.metrics["response_time_ms"] = response_time
            
            # Health evaluation based on DuckDB service status
            service_status = health_data.get("status", "unknown")
            component.issues.clear()
            component.warnings.clear()
            
            if service_status == "healthy":
                component.status = HealthStatus.HEALTHY
            elif service_status == "unhealthy":
                component.status = HealthStatus.UNHEALTHY
                component.issues.extend(health_data.get("errors", []))
            else:
                component.status = HealthStatus.UNKNOWN
                component.issues.append(f"Unknown DuckDB status: {service_status}")
            
            # Additional checks
            if response_time > 2000:  # 2 seconds
                component.status = HealthStatus.CRITICAL
                component.issues.append(f"Slow DuckDB response: {response_time:.0f}ms")
            elif response_time > 1000:  # 1 second
                if component.status == HealthStatus.HEALTHY:
                    component.status = HealthStatus.DEGRADED
                component.warnings.append(f"Elevated DuckDB response time: {response_time:.0f}ms")
            
            # Check circuit breaker status
            circuit_status = health_data.get("circuit_breaker", {})
            if circuit_status.get("state") != "closed":
                component.warnings.append(f"DuckDB circuit breaker: {circuit_status.get('state')}")
                if component.status == HealthStatus.HEALTHY:
                    component.status = HealthStatus.DEGRADED
                    
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"DuckDB health check failed: {str(e)}")
        
        return component
    
    async def _check_redis_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check Redis cache health"""
        try:
            if not self.redis_client:
                component.status = HealthStatus.CRITICAL
                component.issues.append("Redis client not initialized")
                return component
            
            start_time = time.time()
            
            # Test connectivity
            await self.redis_client.ping()
            
            # Get Redis info
            info = await self.redis_client.info()
            
            response_time = (time.time() - start_time) * 1000
            
            component.response_time_ms = response_time
            component.metrics = {
                "memory_used_mb": info.get("used_memory", 0) / (1024 * 1024),
                "connected_clients": info.get("connected_clients", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "response_time_ms": response_time
            }
            
            # Calculate hit rate
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            if hits + misses > 0:
                hit_rate = (hits / (hits + misses)) * 100
                component.metrics["hit_rate_percent"] = hit_rate
                
                if hit_rate < self._thresholds["cache_hit_rate_critical"]:
                    component.status = HealthStatus.CRITICAL
                    component.issues.append(f"Critical cache hit rate: {hit_rate:.1f}%")
                elif hit_rate < self._thresholds["cache_hit_rate_warning"]:
                    component.status = HealthStatus.DEGRADED
                    component.warnings.append(f"Low cache hit rate: {hit_rate:.1f}%")
                else:
                    component.status = HealthStatus.HEALTHY
            else:
                component.status = HealthStatus.HEALTHY
            
            # Memory warnings
            memory_mb = component.metrics["memory_used_mb"]
            if memory_mb > 1024:  # 1GB
                component.warnings.append(f"High Redis memory usage: {memory_mb:.0f}MB")
                if component.status == HealthStatus.HEALTHY:
                    component.status = HealthStatus.DEGRADED
            
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"Redis connection failed: {str(e)}")
        
        return component
    
    async def _check_meilisearch_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check Meilisearch service health"""
        try:
            start_time = time.time()
            
            # Use MeilisearchService health check
            health_data = await MeilisearchService.health_check()
            
            response_time = (time.time() - start_time) * 1000
            
            component.response_time_ms = response_time
            component.metrics = health_data.get("metrics", {})
            component.metrics["response_time_ms"] = response_time
            
            # Health evaluation
            service_status = health_data.get("status", "unknown")
            component.issues.clear()
            component.warnings.clear()
            
            if service_status == "healthy":
                component.status = HealthStatus.HEALTHY
            elif service_status == "unhealthy":
                component.status = HealthStatus.UNHEALTHY
                component.issues.extend(health_data.get("errors", []))
            else:
                component.status = HealthStatus.UNKNOWN
                component.issues.append(f"Unknown Meilisearch status: {service_status}")
            
            # Response time checks
            if response_time > 3000:  # 3 seconds
                component.status = HealthStatus.CRITICAL
                component.issues.append(f"Slow Meilisearch response: {response_time:.0f}ms")
            elif response_time > 1500:  # 1.5 seconds
                if component.status == HealthStatus.HEALTHY:
                    component.status = HealthStatus.DEGRADED
                component.warnings.append(f"Elevated Meilisearch response time: {response_time:.0f}ms")
                
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"Meilisearch health check failed: {str(e)}")
        
        return component
    
    async def _check_data_sync_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check DataSyncService health"""
        try:
            # Check if dependencies are healthy
            postgres_healthy = self._component_registry["postgresql"].status == HealthStatus.HEALTHY
            duckdb_healthy = self._component_registry["duckdb"].status == HealthStatus.HEALTHY
            
            component.issues.clear()
            component.warnings.clear()
            
            if not postgres_healthy:
                component.issues.append("PostgreSQL dependency unhealthy")
            
            if not duckdb_healthy:
                component.issues.append("DuckDB dependency unhealthy")
            
            # Check sync lag from Redis metrics
            if self.redis_client:
                try:
                    sync_lag = await self.redis_client.get("data_sync:lag_seconds")
                    sync_operations = await self.redis_client.get("data_sync:operations_total")
                    sync_failures = await self.redis_client.get("data_sync:failures_total")
                    
                    component.metrics = {
                        "sync_lag_seconds": float(sync_lag) if sync_lag else 0.0,
                        "operations_total": int(sync_operations) if sync_operations else 0,
                        "failures_total": int(sync_failures) if sync_failures else 0
                    }
                    
                    # Evaluate sync lag
                    lag = float(sync_lag) if sync_lag else 0.0
                    if lag > self._thresholds["sync_lag_critical"]:
                        component.status = HealthStatus.CRITICAL
                        component.issues.append(f"Critical sync lag: {lag:.1f}s")
                    elif lag > self._thresholds["sync_lag_warning"]:
                        component.status = HealthStatus.DEGRADED
                        component.warnings.append(f"High sync lag: {lag:.1f}s")
                    else:
                        component.status = HealthStatus.HEALTHY
                        
                except Exception as e:
                    component.warnings.append(f"Could not read sync metrics: {str(e)}")
                    component.status = HealthStatus.DEGRADED
            else:
                component.status = HealthStatus.DEGRADED
                component.warnings.append("Redis not available for sync metrics")
            
            # Overall health based on dependencies
            if component.issues:
                if component.status != HealthStatus.CRITICAL:
                    component.status = HealthStatus.UNHEALTHY
            elif not postgres_healthy or not duckdb_healthy:
                component.status = HealthStatus.DEGRADED
                component.warnings.append("Service dependencies degraded")
                
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"DataSync health check failed: {str(e)}")
        
        return component
    
    async def _check_hybrid_query_router_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check HybridQueryRouter health"""
        try:
            # Check dependencies
            postgres_healthy = self._component_registry["postgresql"].status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
            duckdb_healthy = self._component_registry["duckdb"].status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
            redis_healthy = self._component_registry["redis"].status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
            
            component.issues.clear()
            component.warnings.clear()
            
            # Check routing metrics from Redis
            if self.redis_client:
                try:
                    route_decisions = await self.redis_client.get("query_router:decisions_total")
                    cache_hits = await self.redis_client.get("query_router:cache_hits_total")
                    avg_optimization_time = await self.redis_client.get("query_router:avg_optimization_time")
                    
                    component.metrics = {
                        "route_decisions": int(route_decisions) if route_decisions else 0,
                        "cache_hits": int(cache_hits) if cache_hits else 0,
                        "avg_optimization_time_ms": float(avg_optimization_time) if avg_optimization_time else 0.0
                    }
                    
                    # Calculate cache hit rate
                    if component.metrics["route_decisions"] > 0:
                        hit_rate = (component.metrics["cache_hits"] / component.metrics["route_decisions"]) * 100
                        component.metrics["cache_hit_rate"] = hit_rate
                        
                        if hit_rate < 50.0:  # Less than 50% cache hit rate
                            component.warnings.append(f"Low query cache hit rate: {hit_rate:.1f}%")
                    
                except Exception as e:
                    component.warnings.append(f"Could not read router metrics: {str(e)}")
            
            # Overall health based on dependencies
            if not postgres_healthy and not duckdb_healthy:
                component.status = HealthStatus.CRITICAL
                component.issues.append("Both PostgreSQL and DuckDB unhealthy")
            elif not postgres_healthy:
                component.status = HealthStatus.DEGRADED
                component.warnings.append("PostgreSQL dependency unhealthy")
            elif not duckdb_healthy:
                component.status = HealthStatus.DEGRADED
                component.warnings.append("DuckDB dependency unhealthy")
            elif not redis_healthy:
                component.status = HealthStatus.DEGRADED
                component.warnings.append("Redis dependency unhealthy")
            else:
                component.status = HealthStatus.HEALTHY
                
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"HybridQueryRouter health check failed: {str(e)}")
        
        return component
    
    async def _check_parquet_pipeline_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check ParquetPipeline health"""
        try:
            # Check DuckDB dependency
            duckdb_healthy = self._component_registry["duckdb"].status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
            
            component.issues.clear()
            component.warnings.clear()
            
            if not duckdb_healthy:
                component.status = HealthStatus.DEGRADED
                component.warnings.append("DuckDB dependency unhealthy")
            
            # Check pipeline metrics from Redis
            if self.redis_client:
                try:
                    processing_rate = await self.redis_client.get("parquet:processing_rate")
                    compression_ratio = await self.redis_client.get("parquet:compression_ratio")
                    queue_size = await self.redis_client.llen("parquet_jobs")
                    
                    component.metrics = {
                        "processing_rate_records_per_sec": float(processing_rate) if processing_rate else 0.0,
                        "compression_ratio": float(compression_ratio) if compression_ratio else 0.0,
                        "queue_size": queue_size
                    }
                    
                    # Check queue backlog
                    if queue_size > 1000:
                        component.status = HealthStatus.CRITICAL
                        component.issues.append(f"Large parquet processing queue: {queue_size}")
                    elif queue_size > 500:
                        if component.status not in [HealthStatus.CRITICAL]:
                            component.status = HealthStatus.DEGRADED
                        component.warnings.append(f"Growing parquet queue: {queue_size}")
                    else:
                        if component.status not in [HealthStatus.CRITICAL, HealthStatus.DEGRADED]:
                            component.status = HealthStatus.HEALTHY
                    
                except Exception as e:
                    component.warnings.append(f"Could not read parquet metrics: {str(e)}")
                    if component.status == HealthStatus.UNKNOWN:
                        component.status = HealthStatus.DEGRADED
            else:
                component.warnings.append("Redis not available for pipeline metrics")
                component.status = HealthStatus.DEGRADED
                
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"ParquetPipeline health check failed: {str(e)}")
        
        return component
    
    async def _check_analytics_api_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check Analytics API health"""
        try:
            # Test API endpoint
            start_time = time.time()
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get("http://localhost:8000/api/v1/health")
                
            response_time = (time.time() - start_time) * 1000
            
            component.response_time_ms = response_time
            component.issues.clear()
            component.warnings.clear()
            
            if response.status_code == 200:
                component.status = HealthStatus.HEALTHY
            else:
                component.status = HealthStatus.UNHEALTHY
                component.issues.append(f"API returned status {response.status_code}")
            
            # Check response time
            if response_time > 5000:  # 5 seconds
                component.status = HealthStatus.CRITICAL
                component.issues.append(f"Slow API response: {response_time:.0f}ms")
            elif response_time > 2000:  # 2 seconds
                if component.status == HealthStatus.HEALTHY:
                    component.status = HealthStatus.DEGRADED
                component.warnings.append(f"Elevated API response time: {response_time:.0f}ms")
            
            # Check WebSocket metrics from Redis
            if self.redis_client:
                try:
                    websocket_connections = await self.redis_client.get("analytics_api:websocket_connections")
                    requests_per_sec = await self.redis_client.get("analytics_api:requests_per_second")
                    
                    component.metrics = {
                        "websocket_connections": int(websocket_connections) if websocket_connections else 0,
                        "requests_per_second": float(requests_per_sec) if requests_per_sec else 0.0,
                        "response_time_ms": response_time
                    }
                    
                except Exception as e:
                    component.warnings.append(f"Could not read API metrics: {str(e)}")
                    
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"Analytics API health check failed: {str(e)}")
        
        return component
    
    async def _check_firecrawl_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check Firecrawl API health"""
        try:
            firecrawl_url = getattr(settings, 'FIRECRAWL_BASE_URL', 'http://localhost:3002')
            start_time = time.time()
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{firecrawl_url}/health")
                
            response_time = (time.time() - start_time) * 1000
            
            component.response_time_ms = response_time
            component.issues.clear()
            component.warnings.clear()
            
            if response.status_code == 200:
                component.status = HealthStatus.HEALTHY
            else:
                component.status = HealthStatus.UNHEALTHY
                component.issues.append(f"Firecrawl returned status {response.status_code}")
            
            # Check response time
            if response_time > 10000:  # 10 seconds
                component.status = HealthStatus.CRITICAL
                component.issues.append(f"Slow Firecrawl response: {response_time:.0f}ms")
            elif response_time > 5000:  # 5 seconds
                if component.status == HealthStatus.HEALTHY:
                    component.status = HealthStatus.DEGRADED
                component.warnings.append(f"Elevated Firecrawl response time: {response_time:.0f}ms")
            
            component.metrics = {"response_time_ms": response_time}
            
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"Firecrawl health check failed: {str(e)}")
        
        return component
    
    async def _check_celery_health(self, component: ComponentHealth) -> ComponentHealth:
        """Check Celery workers health"""
        try:
            component.issues.clear()
            component.warnings.clear()
            
            # Check if Redis dependency is healthy
            redis_healthy = self._component_registry["redis"].status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
            
            if not redis_healthy:
                component.status = HealthStatus.DEGRADED
                component.warnings.append("Redis dependency unhealthy")
            
            # Check queue depths and worker activity from Redis
            if self.redis_client:
                try:
                    total_queue_depth = 0
                    queue_metrics = {}
                    
                    for queue_name in ["celery", "scraping", "indexing", "analytics"]:
                        depth = await self.redis_client.llen(queue_name)
                        queue_metrics[queue_name] = depth
                        total_queue_depth += depth
                    
                    # Check active workers (simplified check via Redis)
                    active_workers = await self.redis_client.get("celery:active_workers")
                    
                    component.metrics = {
                        "total_queue_depth": total_queue_depth,
                        "queue_breakdown": queue_metrics,
                        "active_workers": int(active_workers) if active_workers else 0
                    }
                    
                    # Evaluate health based on queue depth
                    if total_queue_depth > 1000:
                        component.status = HealthStatus.CRITICAL
                        component.issues.append(f"Large total queue depth: {total_queue_depth}")
                    elif total_queue_depth > 500:
                        if component.status not in [HealthStatus.CRITICAL]:
                            component.status = HealthStatus.DEGRADED
                        component.warnings.append(f"Growing queue depth: {total_queue_depth}")
                    else:
                        if component.status not in [HealthStatus.CRITICAL, HealthStatus.DEGRADED]:
                            component.status = HealthStatus.HEALTHY
                    
                    # Check worker count
                    worker_count = component.metrics["active_workers"]
                    if worker_count == 0:
                        component.status = HealthStatus.CRITICAL
                        component.issues.append("No active Celery workers detected")
                    elif worker_count < 2:  # Minimum expected workers
                        component.warnings.append(f"Low worker count: {worker_count}")
                        if component.status == HealthStatus.HEALTHY:
                            component.status = HealthStatus.DEGRADED
                    
                except Exception as e:
                    component.warnings.append(f"Could not read Celery metrics: {str(e)}")
                    if component.status == HealthStatus.UNKNOWN:
                        component.status = HealthStatus.DEGRADED
            else:
                component.warnings.append("Redis not available for Celery metrics")
                component.status = HealthStatus.DEGRADED
                
        except Exception as e:
            component.status = HealthStatus.CRITICAL
            component.issues.append(f"Celery health check failed: {str(e)}")
        
        return component
    
    async def track_performance_metrics(self, metrics: Dict[str, Any]) -> None:
        """Track performance metrics with history"""
        timestamp = datetime.utcnow()
        
        # Store metrics in Redis with expiration
        if self.redis_client:
            try:
                # Store current metrics
                metrics_key = f"performance_metrics:{timestamp.isoformat()}"
                await self.redis_client.setex(
                    metrics_key,
                    3600,  # 1 hour TTL
                    json.dumps(metrics, default=str)
                )
                
                # Update individual metric histories
                for metric_name, value in metrics.items():
                    if isinstance(value, (int, float)):
                        history_key = f"metric_history:{metric_name}"
                        
                        # Add current value with timestamp
                        await self.redis_client.zadd(
                            history_key,
                            {json.dumps({"timestamp": timestamp.isoformat(), "value": value}): timestamp.timestamp()}
                        )
                        
                        # Keep only last 24 hours of data
                        cutoff_time = (timestamp - timedelta(hours=24)).timestamp()
                        await self.redis_client.zremrangebyscore(history_key, 0, cutoff_time)
                        
            except Exception as e:
                logger.warning(f"Failed to store performance metrics: {e}")
        
        # Update in-memory performance history
        for metric_name, value in metrics.items():
            if isinstance(value, (int, float)):
                if metric_name not in self._performance_history:
                    self._performance_history[metric_name] = deque(maxlen=1000)
                
                self._performance_history[metric_name].append((timestamp, value))
    
    async def detect_anomalies(self) -> List[Anomaly]:
        """Detect system anomalies based on performance metrics and thresholds"""
        anomalies = []
        timestamp = datetime.utcnow()
        
        if not self._anomaly_detection_enabled:
            return anomalies
        
        try:
            # Check system metrics
            system_metrics = await self.collect_system_metrics()
            
            # CPU usage anomaly
            if system_metrics.cpu_usage_percent > self._thresholds["cpu_usage_critical"]:
                anomalies.append(Anomaly(
                    id=hashlib.md5(f"cpu_critical_{timestamp}".encode()).hexdigest()[:8],
                    component="system",
                    metric="cpu_usage_percent",
                    severity=AlertSeverity.CRITICAL,
                    description="Critical CPU usage detected",
                    current_value=system_metrics.cpu_usage_percent,
                    expected_range=(0, self._thresholds["cpu_usage_critical"])
                ))
            elif system_metrics.cpu_usage_percent > self._thresholds["cpu_usage_warning"]:
                anomalies.append(Anomaly(
                    id=hashlib.md5(f"cpu_warning_{timestamp}".encode()).hexdigest()[:8],
                    component="system",
                    metric="cpu_usage_percent",
                    severity=AlertSeverity.HIGH,
                    description="High CPU usage detected",
                    current_value=system_metrics.cpu_usage_percent,
                    expected_range=(0, self._thresholds["cpu_usage_warning"])
                ))
            
            # Memory usage anomaly
            if system_metrics.memory_usage_percent > self._thresholds["memory_usage_critical"]:
                anomalies.append(Anomaly(
                    id=hashlib.md5(f"memory_critical_{timestamp}".encode()).hexdigest()[:8],
                    component="system",
                    metric="memory_usage_percent",
                    severity=AlertSeverity.CRITICAL,
                    description="Critical memory usage detected",
                    current_value=system_metrics.memory_usage_percent,
                    expected_range=(0, self._thresholds["memory_usage_critical"])
                ))
            elif system_metrics.memory_usage_percent > self._thresholds["memory_usage_warning"]:
                anomalies.append(Anomaly(
                    id=hashlib.md5(f"memory_warning_{timestamp}".encode()).hexdigest()[:8],
                    component="system",
                    metric="memory_usage_percent",
                    severity=AlertSeverity.HIGH,
                    description="High memory usage detected",
                    current_value=system_metrics.memory_usage_percent,
                    expected_range=(0, self._thresholds["memory_usage_warning"])
                ))
            
            # Disk usage anomaly
            if system_metrics.disk_usage_percent > self._thresholds["disk_usage_critical"]:
                anomalies.append(Anomaly(
                    id=hashlib.md5(f"disk_critical_{timestamp}".encode()).hexdigest()[:8],
                    component="system",
                    metric="disk_usage_percent",
                    severity=AlertSeverity.CRITICAL,
                    description="Critical disk usage detected",
                    current_value=system_metrics.disk_usage_percent,
                    expected_range=(0, self._thresholds["disk_usage_critical"])
                ))
            elif system_metrics.disk_usage_percent > self._thresholds["disk_usage_warning"]:
                anomalies.append(Anomaly(
                    id=hashlib.md5(f"disk_warning_{timestamp}".encode()).hexdigest()[:8],
                    component="system",
                    metric="disk_usage_percent",
                    severity=AlertSeverity.HIGH,
                    description="High disk usage detected",
                    current_value=system_metrics.disk_usage_percent,
                    expected_range=(0, self._thresholds["disk_usage_warning"])
                ))
            
            # Check component health for anomalies
            for component_name, component in self._component_registry.items():
                if component.status == HealthStatus.CRITICAL:
                    for issue in component.issues:
                        anomalies.append(Anomaly(
                            id=hashlib.md5(f"{component_name}_critical_{timestamp}_{issue}".encode()).hexdigest()[:8],
                            component=component_name,
                            metric="health_status",
                            severity=AlertSeverity.CRITICAL,
                            description=f"Critical issue in {component_name}: {issue}",
                            current_value=component.status.value,
                            expected_range=("healthy", "degraded")
                        ))
                
                # Check response time anomalies
                if component.response_time_ms and component.response_time_ms > 10000:  # 10 seconds
                    anomalies.append(Anomaly(
                        id=hashlib.md5(f"{component_name}_slow_response_{timestamp}".encode()).hexdigest()[:8],
                        component=component_name,
                        metric="response_time_ms",
                        severity=AlertSeverity.HIGH,
                        description=f"Slow response time for {component_name}",
                        current_value=component.response_time_ms,
                        expected_range=(0, 5000)
                    ))
            
            # Check queue depth anomalies
            for queue_name, depth in system_metrics.queue_depths.items():
                if depth > 1000:  # Large queue threshold
                    anomalies.append(Anomaly(
                        id=hashlib.md5(f"queue_{queue_name}_large_{timestamp}".encode()).hexdigest()[:8],
                        component="celery",
                        metric=f"queue_depth_{queue_name}",
                        severity=AlertSeverity.HIGH,
                        description=f"Large queue depth in {queue_name}",
                        current_value=depth,
                        expected_range=(0, 100)
                    ))
            
        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}")
            # Add anomaly about the detection system itself
            anomalies.append(Anomaly(
                id=hashlib.md5(f"anomaly_detection_error_{timestamp}".encode()).hexdigest()[:8],
                component="monitoring_service",
                metric="anomaly_detection",
                severity=AlertSeverity.MEDIUM,
                description=f"Anomaly detection system error: {str(e)}",
                current_value="error",
                expected_range=("healthy", "healthy")
            ))
        
        return anomalies
    
    async def generate_health_report(self) -> HealthReport:
        """Generate comprehensive system health report"""
        try:
            # Collect all health information
            components = []
            
            # Check all registered components
            for component_name in self._component_registry.keys():
                await self.check_service_health(component_name)
                components.append(self._component_registry[component_name])
            
            # Collect system and performance metrics
            system_metrics = await self.collect_system_metrics()
            performance_metrics = await self._collect_performance_metrics()
            
            # Detect anomalies
            anomalies = await self.detect_anomalies()
            
            # Calculate overall status
            overall_status = self._calculate_overall_health(components)
            
            # Generate SLA compliance metrics
            sla_compliance = await self._calculate_sla_compliance(components)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(components, system_metrics, anomalies)
            
            return HealthReport(
                overall_status=overall_status,
                components=components,
                system_metrics=system_metrics,
                performance_metrics=performance_metrics,
                anomalies=anomalies,
                sla_compliance=sla_compliance,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"Error generating health report: {e}")
            return HealthReport(
                overall_status=HealthStatus.UNKNOWN,
                anomalies=[Anomaly(
                    id=hashlib.md5(f"health_report_error_{datetime.utcnow()}".encode()).hexdigest()[:8],
                    component="monitoring_service",
                    metric="health_report_generation",
                    severity=AlertSeverity.HIGH,
                    description=f"Health report generation failed: {str(e)}",
                    current_value="error",
                    expected_range=("healthy", "healthy")
                )]
            )
    
    async def _collect_performance_metrics(self) -> PerformanceMetrics:
        """Collect Phase 2 specific performance metrics"""
        try:
            performance_metrics = PerformanceMetrics()
            
            # DuckDB metrics
            duckdb_component = self._component_registry.get("duckdb")
            if duckdb_component and duckdb_component.metrics:
                performance_metrics.duckdb_query_duration_avg = duckdb_component.metrics.get("avg_query_time", 0.0)
                performance_metrics.duckdb_active_connections = duckdb_component.metrics.get("active_connections", 0)
                performance_metrics.duckdb_memory_usage_mb = duckdb_component.metrics.get("memory_usage_mb", 0.0)
            
            # Data sync metrics
            data_sync_component = self._component_registry.get("data_sync_service")
            if data_sync_component and data_sync_component.metrics:
                performance_metrics.sync_lag_seconds = data_sync_component.metrics.get("sync_lag_seconds", 0.0)
                performance_metrics.sync_operations_total = data_sync_component.metrics.get("operations_total", 0)
                performance_metrics.sync_failures_total = data_sync_component.metrics.get("failures_total", 0)
            
            # Query router metrics
            router_component = self._component_registry.get("hybrid_query_router")
            if router_component and router_component.metrics:
                performance_metrics.query_cache_hit_rate = router_component.metrics.get("cache_hit_rate", 0.0)
                performance_metrics.hybrid_query_routing_efficiency = router_component.metrics.get("routing_efficiency", 0.0)
            
            # Analytics API metrics
            api_component = self._component_registry.get("analytics_api")
            if api_component and api_component.metrics:
                performance_metrics.analytics_requests_per_second = api_component.metrics.get("requests_per_second", 0.0)
            
            # Parquet pipeline metrics
            parquet_component = self._component_registry.get("parquet_pipeline")
            if parquet_component and parquet_component.metrics:
                performance_metrics.parquet_processing_rate = parquet_component.metrics.get("processing_rate_records_per_sec", 0.0)
            
            return performance_metrics
            
        except Exception as e:
            logger.error(f"Error collecting performance metrics: {e}")
            return PerformanceMetrics()
    
    def _calculate_overall_health(self, components: List[ComponentHealth]) -> HealthStatus:
        """Calculate overall system health based on component health"""
        if not components:
            return HealthStatus.UNKNOWN
        
        statuses = [comp.status for comp in components]
        
        # Priority order: CRITICAL > UNHEALTHY > DEGRADED > UNKNOWN > HEALTHY
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        elif HealthStatus.UNKNOWN in statuses:
            return HealthStatus.UNKNOWN
        else:
            return HealthStatus.HEALTHY
    
    async def _calculate_sla_compliance(self, components: List[ComponentHealth]) -> Dict[str, float]:
        """Calculate SLA compliance metrics for components"""
        sla_compliance = {}
        
        try:
            for component in components:
                # Calculate uptime percentage (simplified)
                if component.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]:
                    # Consider healthy and degraded as "up"
                    compliance = 100.0 if component.status == HealthStatus.HEALTHY else 95.0
                elif component.status == HealthStatus.UNHEALTHY:
                    compliance = 75.0
                elif component.status == HealthStatus.CRITICAL:
                    compliance = 25.0
                else:
                    compliance = 50.0  # Unknown status
                
                sla_compliance[component.name] = compliance
                
                # Add response time SLA if available
                if component.response_time_ms is not None:
                    response_sla_key = f"{component.name}_response_time"
                    if component.response_time_ms < 1000:  # < 1 second
                        sla_compliance[response_sla_key] = 100.0
                    elif component.response_time_ms < 5000:  # < 5 seconds
                        sla_compliance[response_sla_key] = 80.0
                    else:
                        sla_compliance[response_sla_key] = 50.0
            
            # Overall system SLA
            if sla_compliance:
                overall_sla = sum(sla_compliance.values()) / len(sla_compliance)
                sla_compliance["overall"] = round(overall_sla, 2)
                
        except Exception as e:
            logger.error(f"Error calculating SLA compliance: {e}")
            sla_compliance["error"] = f"SLA calculation failed: {str(e)}"
        
        return sla_compliance
    
    def _generate_recommendations(
        self,
        components: List[ComponentHealth],
        system_metrics: SystemMetrics,
        anomalies: List[Anomaly]
    ) -> List[str]:
        """Generate actionable recommendations based on health status"""
        recommendations = []
        
        try:
            # System resource recommendations
            if system_metrics.memory_usage_percent > 85:
                recommendations.append("Consider increasing system memory or optimizing memory usage")
            
            if system_metrics.cpu_usage_percent > 80:
                recommendations.append("High CPU usage detected - consider scaling or optimizing workloads")
            
            if system_metrics.disk_usage_percent > 90:
                recommendations.append("Disk space critically low - clean up logs or increase storage")
            
            # Component-specific recommendations
            for component in components:
                if component.status == HealthStatus.CRITICAL:
                    recommendations.append(f"URGENT: {component.name} is in critical state - immediate action required")
                
                elif component.status == HealthStatus.UNHEALTHY:
                    recommendations.append(f"Fix issues in {component.name} to restore service health")
                
                # DuckDB specific recommendations
                if component.name == "duckdb" and component.metrics:
                    avg_query_time = component.metrics.get("avg_query_time", 0)
                    if avg_query_time > 5.0:
                        recommendations.append("DuckDB queries are slow - consider query optimization or indexing")
                    
                    memory_usage = component.metrics.get("memory_usage_mb", 0)
                    if memory_usage > 2048:  # 2GB
                        recommendations.append("DuckDB memory usage high - consider tuning memory limits")
                
                # Data sync recommendations
                elif component.name == "data_sync_service" and component.metrics:
                    sync_lag = component.metrics.get("sync_lag_seconds", 0)
                    if sync_lag > 120:
                        recommendations.append("Data synchronization lag is high - check sync service performance")
                
                # Queue recommendations
                elif component.name == "celery_workers" and component.metrics:
                    total_queue_depth = component.metrics.get("total_queue_depth", 0)
                    if total_queue_depth > 500:
                        recommendations.append("Celery queues are backing up - consider adding more workers")
            
            # Cache performance recommendations
            redis_component = next((c for c in components if c.name == "redis"), None)
            if redis_component and redis_component.metrics:
                hit_rate = redis_component.metrics.get("hit_rate_percent", 100)
                if hit_rate < 70:
                    recommendations.append("Low cache hit rate - review caching strategy and TTL settings")
            
            # Anomaly-based recommendations
            critical_anomalies = [a for a in anomalies if a.severity == AlertSeverity.CRITICAL]
            if critical_anomalies:
                recommendations.append(f"Address {len(critical_anomalies)} critical anomalies immediately")
            
            # General recommendations
            if not recommendations:
                recommendations.append("System is healthy - continue monitoring")
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            recommendations.append("Error generating recommendations - manual review required")
        
        return recommendations
    
    async def create_alert(self, alert: Dict[str, Any]) -> str:
        """Create and track an alert"""
        try:
            alert_id = hashlib.md5(
                f"{alert.get('component', 'unknown')}_{alert.get('metric', 'unknown')}_{datetime.utcnow()}".encode()
            ).hexdigest()[:12]
            
            alert_data = {
                "id": alert_id,
                "timestamp": datetime.utcnow().isoformat(),
                "severity": alert.get("severity", AlertSeverity.INFO.value),
                "component": alert.get("component", "unknown"),
                "metric": alert.get("metric", "unknown"),
                "description": alert.get("description", ""),
                "current_value": alert.get("current_value"),
                "threshold": alert.get("threshold"),
                "status": "active"
            }
            
            # Store in Redis
            if self.redis_client:
                await self.redis_client.setex(
                    f"alert:{alert_id}",
                    86400,  # 24 hours TTL
                    json.dumps(alert_data, default=str)
                )
                
                # Add to alerts list
                await self.redis_client.lpush("active_alerts", alert_id)
                
                # Trim to keep only recent alerts
                await self.redis_client.ltrim("active_alerts", 0, 999)
            
            logger.warning(f"Alert created: {alert_data['description']} (ID: {alert_id})")
            
            return alert_id
            
        except Exception as e:
            logger.error(f"Error creating alert: {e}")
            return ""
    
    async def get_performance_trends(self, timerange: str = "1h") -> Dict[str, Any]:
        """Get performance trends for specified timerange"""
        try:
            # Convert timerange to datetime
            if timerange == "1h":
                start_time = datetime.utcnow() - timedelta(hours=1)
            elif timerange == "24h":
                start_time = datetime.utcnow() - timedelta(hours=24)
            elif timerange == "7d":
                start_time = datetime.utcnow() - timedelta(days=7)
            else:
                start_time = datetime.utcnow() - timedelta(hours=1)
            
            trends = {
                "timerange": timerange,
                "start_time": start_time.isoformat(),
                "end_time": datetime.utcnow().isoformat(),
                "metrics": {}
            }
            
            # Get trends from Redis
            if self.redis_client:
                metric_names = [
                    "duckdb_query_duration",
                    "sync_lag_seconds",
                    "memory_usage_percent",
                    "cpu_usage_percent",
                    "cache_hit_rate"
                ]
                
                for metric_name in metric_names:
                    history_key = f"metric_history:{metric_name}"
                    
                    # Get data points within timerange
                    start_timestamp = start_time.timestamp()
                    data_points = await self.redis_client.zrangebyscore(
                        history_key, start_timestamp, "+inf", withscores=True
                    )
                    
                    if data_points:
                        parsed_points = []
                        for data_json, timestamp in data_points:
                            try:
                                data = json.loads(data_json)
                                parsed_points.append({
                                    "timestamp": data["timestamp"],
                                    "value": data["value"]
                                })
                            except (json.JSONDecodeError, KeyError):
                                continue
                        
                        trends["metrics"][metric_name] = {
                            "data_points": parsed_points,
                            "count": len(parsed_points)
                        }
                        
                        if parsed_points:
                            values = [p["value"] for p in parsed_points]
                            trends["metrics"][metric_name].update({
                                "min": min(values),
                                "max": max(values),
                                "avg": sum(values) / len(values),
                                "trend": "increasing" if values[-1] > values[0] else "decreasing" if values[-1] < values[0] else "stable"
                            })
            
            return trends
            
        except Exception as e:
            logger.error(f"Error getting performance trends: {e}")
            return {"error": str(e)}
    
    async def shutdown(self):
        """Cleanup monitoring service resources"""
        try:
            if self.redis_client:
                await self.redis_client.close()
            
            logger.info("MonitoringService shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during MonitoringService shutdown: {e}")


# Global monitoring service instance
monitoring_service = MonitoringService()


# FastAPI dependency
async def get_monitoring_service() -> MonitoringService:
    """FastAPI dependency for monitoring service"""
    if not monitoring_service.redis_client:
        await monitoring_service.initialize()
    return monitoring_service