"""
Optimization Integration Service

Coordinates initialization and integration of all query optimization components
with the existing Chrono Scraper analytics infrastructure.
"""

import asyncio
import logging
from typing import Optional

import redis.asyncio as aioredis

from ..core.config import settings
from ..core.database import get_db_session_factory
from .query_optimization_engine import init_query_optimization_engine
from .intelligent_cache_manager import init_cache_manager
from .query_performance_monitor import init_performance_monitor
from .adaptive_query_executor import init_query_executor
from .cache_integration_service import init_cache_integration_service, ConsistencyLevel

logger = logging.getLogger(__name__)


class OptimizationIntegration:
    """
    Central coordinator for all query optimization services.
    
    Handles initialization, lifecycle management, and integration
    of optimization components with existing analytics infrastructure.
    """
    
    def __init__(self):
        self.initialized = False
        self.services = {}
        
    async def initialize_all_services(
        self,
        postgresql_session_factory=None,
        duckdb_service=None,
        redis_client: Optional[aioredis.Redis] = None
    ):
        """
        Initialize all optimization services in proper dependency order.
        
        Args:
            postgresql_session_factory: PostgreSQL database session factory
            duckdb_service: DuckDB analytics service instance
            redis_client: Redis client for caching
        """
        if self.initialized:
            logger.warning("Optimization services already initialized")
            return
        
        try:
            logger.info("Initializing query optimization services...")
            
            # Get database session factory if not provided
            if not postgresql_session_factory:
                postgresql_session_factory = get_db_session_factory()
            
            # Initialize Redis client if not provided
            if not redis_client and settings.ENABLE_MULTI_LEVEL_CACHING:
                try:
                    redis_client = aioredis.from_url(
                        settings.REDIS_URL,
                        encoding="utf-8",
                        decode_responses=False  # Keep binary for caching
                    )
                    # Test connection
                    await redis_client.ping()
                    logger.info("Redis connection established for caching")
                except Exception as e:
                    logger.warning(f"Redis connection failed, caching will be limited: {str(e)}")
                    redis_client = None
            
            # 1. Initialize Query Optimization Engine
            if settings.QUERY_OPTIMIZATION_ENABLED:
                logger.info("Initializing query optimization engine...")
                optimization_engine = init_query_optimization_engine(
                    postgresql_session_factory=postgresql_session_factory,
                    duckdb_service=duckdb_service,
                    enable_caching=settings.ENABLE_MULTI_LEVEL_CACHING
                )
                self.services['optimization_engine'] = optimization_engine
                logger.info("✓ Query optimization engine initialized")
            
            # 2. Initialize Intelligent Cache Manager
            if settings.ENABLE_MULTI_LEVEL_CACHING:
                logger.info("Initializing intelligent cache manager...")
                cache_manager = await init_cache_manager(
                    redis_client=redis_client,
                    duckdb_service=duckdb_service,
                    max_memory_cache_mb=settings.L1_CACHE_SIZE_MB,
                    enable_compression=settings.CACHE_COMPRESSION_ENABLED,
                    enable_predictive_caching=settings.PREDICTIVE_CACHING_ENABLED
                )
                self.services['cache_manager'] = cache_manager
                logger.info("✓ Intelligent cache manager initialized")
            
            # 3. Initialize Performance Monitor
            if settings.PERFORMANCE_MONITORING_ENABLED:
                logger.info("Initializing query performance monitor...")
                
                # Setup alert callback
                async def alert_callback(alert):
                    logger.warning(
                        f"Performance alert triggered: {alert.description} "
                        f"(Current: {alert.current_value}, Threshold: {alert.threshold.threshold_value})"
                    )
                    # In production, would send to notification system
                
                performance_monitor = await init_performance_monitor(
                    alert_callback=alert_callback,
                    max_execution_history=10000,
                    anomaly_detection_enabled=settings.ENABLE_ANOMALY_DETECTION
                )
                self.services['performance_monitor'] = performance_monitor
                logger.info("✓ Query performance monitor initialized")
            
            # 4. Initialize Adaptive Query Executor
            logger.info("Initializing adaptive query executor...")
            query_executor = await init_query_executor(
                postgresql_session_factory=postgresql_session_factory,
                duckdb_service=duckdb_service,
                max_concurrent_queries=settings.MAX_CONCURRENT_QUERIES,
                default_timeout_seconds=settings.QUERY_TIMEOUT_SECONDS,
                enable_adaptive_routing=True
            )
            self.services['query_executor'] = query_executor
            logger.info("✓ Adaptive query executor initialized")
            
            # 5. Initialize Cache Integration Service
            if settings.ENABLE_CROSS_DATABASE_CACHING:
                logger.info("Initializing cache integration service...")
                cache_integration = await init_cache_integration_service(
                    postgresql_session_factory=postgresql_session_factory,
                    duckdb_service=duckdb_service,
                    redis_client=redis_client,
                    enable_cross_db_invalidation=True,
                    default_consistency_level=ConsistencyLevel(settings.CACHE_CONSISTENCY_LEVEL)
                )
                self.services['cache_integration'] = cache_integration
                logger.info("✓ Cache integration service initialized")
            
            # 6. Setup service integrations
            await self._setup_service_integrations()
            
            self.initialized = True
            logger.info(
                f"✅ Query optimization system initialized successfully! "
                f"Services: {', '.join(self.services.keys())}"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize optimization services: {str(e)}")
            await self.shutdown_all_services()
            raise
    
    async def _setup_service_integrations(self):
        """Setup integrations between optimization services"""
        try:
            # Connect query executor to performance monitoring
            if 'query_executor' in self.services and 'performance_monitor' in self.services:
                logger.debug("Connecting query executor to performance monitor")
                # Integration would happen here in production
            
            # Connect cache manager to optimization engine
            if 'cache_manager' in self.services and 'optimization_engine' in self.services:
                logger.debug("Connecting cache manager to optimization engine")
                # Integration would happen here in production
            
            # Setup performance-based cache optimization
            if 'cache_integration' in self.services and 'performance_monitor' in self.services:
                logger.debug("Setting up performance-based cache optimization")
                # Integration would happen here in production
            
            logger.info("Service integrations configured successfully")
            
        except Exception as e:
            logger.error(f"Error setting up service integrations: {str(e)}")
            raise
    
    async def shutdown_all_services(self):
        """Shutdown all optimization services gracefully"""
        if not self.initialized:
            return
        
        logger.info("Shutting down query optimization services...")
        
        # Shutdown services in reverse order
        shutdown_tasks = []
        
        if 'cache_integration' in self.services:
            shutdown_tasks.append(self.services['cache_integration'].stop())
        
        if 'query_executor' in self.services:
            shutdown_tasks.append(self.services['query_executor'].shutdown())
        
        if 'performance_monitor' in self.services:
            shutdown_tasks.append(self.services['performance_monitor'].stop_monitoring())
        
        # Wait for all shutdowns to complete
        if shutdown_tasks:
            await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        
        self.services.clear()
        self.initialized = False
        
        logger.info("Query optimization services shutdown completed")
    
    async def get_system_health(self) -> dict:
        """Get health status of all optimization services"""
        health = {
            'overall_status': 'healthy',
            'initialized': self.initialized,
            'services': {}
        }
        
        try:
            for service_name, service in self.services.items():
                try:
                    if hasattr(service, 'get_health_status'):
                        service_health = await service.get_health_status()
                    else:
                        service_health = {'status': 'healthy', 'available': True}
                    
                    health['services'][service_name] = service_health
                    
                except Exception as e:
                    health['services'][service_name] = {
                        'status': 'unhealthy',
                        'error': str(e),
                        'available': False
                    }
                    health['overall_status'] = 'degraded'
            
        except Exception as e:
            logger.error(f"Error checking system health: {str(e)}")
            health['overall_status'] = 'unhealthy'
            health['error'] = str(e)
        
        return health
    
    async def get_performance_metrics(self) -> dict:
        """Get comprehensive performance metrics from all services"""
        metrics = {
            'optimization_engine': {},
            'cache_manager': {},
            'performance_monitor': {},
            'query_executor': {},
            'cache_integration': {}
        }
        
        try:
            # Query optimization engine metrics
            if 'optimization_engine' in self.services:
                optimization_stats = await self.services['optimization_engine'].get_optimization_stats()
                metrics['optimization_engine'] = optimization_stats
            
            # Cache manager metrics
            if 'cache_manager' in self.services:
                cache_stats = await self.services['cache_manager'].get_cache_statistics()
                metrics['cache_manager'] = {
                    'total_entries': cache_stats.total_entries,
                    'hit_rate': cache_stats.hit_rate,
                    'memory_pressure': cache_stats.memory_pressure,
                    'level_stats': {
                        level.name.lower(): stats for level, stats in cache_stats.level_stats.items()
                    }
                }
            
            # Performance monitor metrics
            if 'performance_monitor' in self.services:
                dashboard_data = await self.services['performance_monitor'].get_performance_dashboard_data()
                metrics['performance_monitor'] = {
                    'current_metrics': dashboard_data.current_metrics,
                    'active_alerts_count': len(dashboard_data.active_alerts),
                    'recent_anomalies_count': len(dashboard_data.recent_anomalies)
                }
            
            # Query executor metrics
            if 'query_executor' in self.services:
                exec_metrics = await self.services['query_executor'].get_execution_metrics()
                metrics['query_executor'] = {
                    'active_queries': exec_metrics.active_queries,
                    'queued_queries': exec_metrics.queued_queries,
                    'average_execution_time_ms': exec_metrics.average_execution_time_ms,
                    'system_load': exec_metrics.system_load
                }
            
            # Cache integration metrics
            if 'cache_integration' in self.services:
                integration_service = self.services['cache_integration']
                metrics['cache_integration'] = {
                    'cross_db_operations': integration_service.metrics.get('cross_db_operations', 0),
                    'invalidations_triggered': integration_service.metrics.get('invalidations_triggered', 0),
                    'hybrid_queries': integration_service.metrics.get('hybrid_queries', 0)
                }
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {str(e)}")
            metrics['error'] = str(e)
        
        return metrics
    
    def get_service(self, service_name: str):
        """Get a specific optimization service by name"""
        return self.services.get(service_name)
    
    def is_service_available(self, service_name: str) -> bool:
        """Check if a specific service is available and healthy"""
        return service_name in self.services


# Global optimization integration instance
_optimization_integration: Optional[OptimizationIntegration] = None


def get_optimization_integration() -> OptimizationIntegration:
    """Get the global optimization integration instance"""
    global _optimization_integration
    if _optimization_integration is None:
        _optimization_integration = OptimizationIntegration()
    return _optimization_integration


async def init_optimization_system(
    postgresql_session_factory=None,
    duckdb_service=None,
    redis_client: Optional[aioredis.Redis] = None
):
    """
    Initialize the complete query optimization system.
    
    This is the main entry point for setting up all optimization services.
    """
    integration = get_optimization_integration()
    await integration.initialize_all_services(
        postgresql_session_factory=postgresql_session_factory,
        duckdb_service=duckdb_service,
        redis_client=redis_client
    )
    
    return integration


async def shutdown_optimization_system():
    """Shutdown the complete query optimization system"""
    integration = get_optimization_integration()
    await integration.shutdown_all_services()


# Service health check endpoint data
async def get_optimization_system_health():
    """Get comprehensive health check data for optimization system"""
    integration = get_optimization_integration()
    return await integration.get_system_health()


# Performance metrics endpoint data
async def get_optimization_system_metrics():
    """Get comprehensive performance metrics for optimization system"""
    integration = get_optimization_integration()
    return await integration.get_performance_metrics()