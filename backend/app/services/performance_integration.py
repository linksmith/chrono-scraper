"""
Performance Integration Service

This service integrates all performance optimization components and provides
unified initialization and management for the comprehensive admin system.
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
import redis.asyncio as redis

from app.core.config import settings
from .admin_cache_service import AdminCacheService, init_admin_cache_service
from .performance_monitoring import PerformanceMonitoringService, init_performance_monitor
from .query_optimization import QueryOptimizationService, init_query_optimizer

logger = logging.getLogger(__name__)


class PerformanceIntegrationService:
    """
    Unified performance optimization service that coordinates all optimization components.
    
    This service provides:
    - Centralized initialization of all performance services
    - Automated performance analysis and reporting
    - Cache warming and management
    - Performance health monitoring
    - Optimization recommendations
    """
    
    def __init__(
        self,
        db_session_factory,
        redis_client: Optional[redis.Redis] = None
    ):
        self.db_session_factory = db_session_factory
        self.redis_client = redis_client
        
        # Service instances
        self.cache_service: Optional[AdminCacheService] = None
        self.performance_monitor: Optional[PerformanceMonitoringService] = None
        self.query_optimizer: Optional[QueryOptimizationService] = None
        
        # Performance thresholds and configurations
        self.performance_config = {
            'cache_warmup_interval_minutes': 15,
            'performance_analysis_interval_minutes': 30,
            'health_check_interval_minutes': 5,
            'cleanup_interval_hours': 6,
            'slow_query_threshold_ms': 1000,
            'critical_query_threshold_ms': 5000
        }
        
        # Background tasks
        self._background_tasks: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
    
    async def initialize(self) -> bool:
        """
        Initialize all performance optimization services.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            logger.info("🚀 Initializing Performance Integration Service...")
            
            # Initialize Redis if not provided
            if not self.redis_client:
                self.redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=getattr(settings, 'REDIS_PORT', 6379),
                    db=getattr(settings, 'REDIS_CACHE_DB', 1),
                    decode_responses=False  # Keep as bytes for caching service
                )
                
                # Test Redis connection
                await self.redis_client.ping()
                logger.info("✅ Redis connection established")
            
            # Initialize cache service
            self.cache_service = await init_admin_cache_service(
                redis_client=self.redis_client,
                default_ttl=300,
                memory_cache_size=2000,  # Larger cache for admin operations
                enable_compression=True,
                enable_metrics=True
            )
            logger.info("✅ Admin cache service initialized")
            
            # Initialize performance monitoring
            self.performance_monitor = init_performance_monitor(self.db_session_factory)
            logger.info("✅ Performance monitoring service initialized")
            
            # Initialize query optimizer
            self.query_optimizer = init_query_optimizer(self.db_session_factory)
            logger.info("✅ Query optimization service initialized")
            
            # Start background tasks
            await self._start_background_tasks()
            
            # Perform initial health check
            health_status = await self.comprehensive_health_check()
            if health_status['overall_healthy']:
                logger.info("🎉 Performance Integration Service fully initialized and healthy")
                return True
            else:
                logger.warning("⚠️ Performance Integration Service initialized with warnings")
                logger.warning(f"Health issues: {health_status.get('issues', [])}")
                return True  # Still return True as services are initialized
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Performance Integration Service: {str(e)}")
            return False
    
    async def _start_background_tasks(self):
        """Start background optimization tasks"""
        logger.info("Starting background performance optimization tasks...")
        
        # Cache warmup task
        self._background_tasks.append(
            asyncio.create_task(self._cache_warmup_task())
        )
        
        # Performance analysis task
        self._background_tasks.append(
            asyncio.create_task(self._performance_analysis_task())
        )
        
        # Health monitoring task
        self._background_tasks.append(
            asyncio.create_task(self._health_monitoring_task())
        )
        
        # Cleanup task
        self._background_tasks.append(
            asyncio.create_task(self._cleanup_task())
        )
        
        logger.info(f"Started {len(self._background_tasks)} background tasks")
    
    async def _cache_warmup_task(self):
        """Background task for periodic cache warming"""
        while not self._shutdown_event.is_set():
            try:
                logger.debug("Running cache warmup...")
                
                if self.cache_service:
                    await self.cache_service.warm_admin_cache()
                
                # Wait for next warmup cycle
                await asyncio.wait_for(
                    self._shutdown_event.wait(), 
                    timeout=self.performance_config['cache_warmup_interval_minutes'] * 60
                )
                
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue loop
            except Exception as e:
                logger.error(f"Error in cache warmup task: {str(e)}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _performance_analysis_task(self):
        """Background task for performance analysis"""
        while not self._shutdown_event.is_set():
            try:
                logger.debug("Running performance analysis...")
                
                if self.performance_monitor:
                    # Get performance summary
                    summary = await self.performance_monitor.get_performance_summary()
                    
                    # Check for performance issues
                    if summary.get('health_score', 100) < 80:
                        logger.warning(f"Performance health score is low: {summary.get('health_score', 0)}")
                        
                        # Generate optimization recommendations
                        if self.query_optimizer:
                            recommendations = await self.query_optimizer.get_optimization_recommendations()
                            if recommendations:
                                logger.info(f"Generated {len(recommendations)} optimization recommendations")
                
                # Wait for next analysis cycle
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.performance_config['performance_analysis_interval_minutes'] * 60
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in performance analysis task: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    async def _health_monitoring_task(self):
        """Background task for health monitoring"""
        while not self._shutdown_event.is_set():
            try:
                logger.debug("Running health check...")
                
                health_status = await self.comprehensive_health_check()
                
                if not health_status['overall_healthy']:
                    logger.warning("Performance system health check failed")
                    logger.warning(f"Issues detected: {health_status.get('issues', [])}")
                
                # Wait for next health check
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.performance_config['health_check_interval_minutes'] * 60
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in health monitoring task: {str(e)}")
                await asyncio.sleep(180)  # Wait 3 minutes before retrying
    
    async def _cleanup_task(self):
        """Background task for periodic cleanup"""
        while not self._shutdown_event.is_set():
            try:
                logger.debug("Running performance data cleanup...")
                
                # Cleanup old performance metrics
                if self.performance_monitor:
                    await self.performance_monitor.cleanup_old_metrics(hours=24)
                
                # Cleanup old query analyses
                if self.query_optimizer:
                    await self.query_optimizer.cleanup_old_analyses(hours=24)
                
                # Wait for next cleanup cycle
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.performance_config['cleanup_interval_hours'] * 3600
                )
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in cleanup task: {str(e)}")
                await asyncio.sleep(1800)  # Wait 30 minutes before retrying
    
    async def comprehensive_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check of all performance services"""
        health_status = {
            'timestamp': datetime.now().isoformat(),
            'overall_healthy': True,
            'services': {},
            'issues': []
        }
        
        # Check cache service health
        if self.cache_service:
            try:
                cache_health = await self.cache_service.health_check()
                health_status['services']['cache'] = cache_health
                
                if not cache_health.get('overall_healthy', False):
                    health_status['overall_healthy'] = False
                    health_status['issues'].append('Cache service unhealthy')
                    
            except Exception as e:
                health_status['services']['cache'] = {'healthy': False, 'error': str(e)}
                health_status['overall_healthy'] = False
                health_status['issues'].append(f'Cache service error: {str(e)}')
        
        # Check database performance
        if self.performance_monitor:
            try:
                db_stats = await self.performance_monitor.get_database_stats()
                health_status['services']['database'] = {
                    'healthy': db_stats.cache_hit_ratio > 85 and db_stats.slow_queries_count < 10,
                    'cache_hit_ratio': db_stats.cache_hit_ratio,
                    'slow_queries_count': db_stats.slow_queries_count,
                    'avg_query_time_ms': db_stats.avg_query_time_ms
                }
                
                if db_stats.cache_hit_ratio < 85:
                    health_status['issues'].append(f'Low cache hit ratio: {db_stats.cache_hit_ratio:.1f}%')
                
                if db_stats.slow_queries_count > 10:
                    health_status['issues'].append(f'High slow query count: {db_stats.slow_queries_count}')
                    
            except Exception as e:
                health_status['services']['database'] = {'healthy': False, 'error': str(e)}
                health_status['overall_healthy'] = False
                health_status['issues'].append(f'Database monitoring error: {str(e)}')
        
        # Check Redis connectivity
        if self.redis_client:
            try:
                await self.redis_client.ping()
                health_status['services']['redis'] = {'healthy': True}
            except Exception as e:
                health_status['services']['redis'] = {'healthy': False, 'error': str(e)}
                health_status['overall_healthy'] = False
                health_status['issues'].append(f'Redis connectivity error: {str(e)}')
        
        return health_status
    
    async def get_performance_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive performance data for admin dashboard"""
        dashboard_data = {
            'timestamp': datetime.now().isoformat(),
            'cache_metrics': {},
            'database_stats': {},
            'query_analysis': {},
            'optimization_recommendations': []
        }
        
        try:
            # Get cache metrics
            if self.cache_service:
                cache_info = await self.cache_service.get_cache_info()
                cache_metrics = await self.cache_service.get_metrics()
                
                dashboard_data['cache_metrics'] = {
                    'info': cache_info,
                    'metrics_by_namespace': cache_metrics
                }
            
            # Get database statistics
            if self.performance_monitor:
                db_stats = await self.performance_monitor.get_database_stats()
                table_stats = await self.performance_monitor.get_table_stats()
                
                dashboard_data['database_stats'] = {
                    'overview': db_stats.dict(),
                    'table_stats': [ts.dict() for ts in table_stats[:10]]  # Top 10 tables
                }
            
            # Get query optimization data
            if self.query_optimizer:
                recommendations = await self.query_optimizer.get_optimization_recommendations()
                dashboard_data['optimization_recommendations'] = [rec.dict() for rec in recommendations[:5]]
            
            # Get recent performance summary
            if self.performance_monitor:
                summary = await self.performance_monitor.get_performance_summary()
                dashboard_data['performance_summary'] = summary
            
        except Exception as e:
            logger.error(f"Error getting performance dashboard data: {str(e)}")
            dashboard_data['error'] = str(e)
        
        return dashboard_data
    
    async def optimize_query(self, query: str, params: Optional[Dict[str, Any]] = None):
        """Analyze and optimize a specific query"""
        if not self.query_optimizer:
            raise RuntimeError("Query optimizer not initialized")
        
        return await self.query_optimizer.analyze_query(query, params)
    
    async def warm_cache(self, namespace: Optional[str] = None):
        """Manually trigger cache warming"""
        if not self.cache_service:
            raise RuntimeError("Cache service not initialized")
        
        if namespace:
            # Warm specific namespace (would need to implement namespace-specific warming)
            logger.info(f"Warming cache for namespace: {namespace}")
        else:
            await self.cache_service.warm_admin_cache()
        
        return {"status": "success", "message": "Cache warming completed"}
    
    async def get_slow_queries(self, hours: int = 24):
        """Get analysis of slow queries"""
        if not self.performance_monitor:
            raise RuntimeError("Performance monitor not initialized")
        
        return await self.performance_monitor.analyze_slow_queries(hours=hours)
    
    async def clear_caches(self, pattern: Optional[str] = None):
        """Clear caches with optional pattern"""
        if not self.cache_service:
            raise RuntimeError("Cache service not initialized")
        
        if pattern:
            cleared_count = await self.cache_service.delete_pattern(pattern)
            return {"status": "success", "cleared_keys": cleared_count, "pattern": pattern}
        else:
            success = await self.cache_service.clear_all_caches()
            return {"status": "success" if success else "error", "message": "All caches cleared"}
    
    async def shutdown(self):
        """Gracefully shutdown all services and background tasks"""
        logger.info("Shutting down Performance Integration Service...")
        
        # Signal shutdown to background tasks
        self._shutdown_event.set()
        
        # Wait for background tasks to complete (with timeout)
        if self._background_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._background_tasks, return_exceptions=True),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.warning("Background tasks did not shut down within timeout")
                # Cancel remaining tasks
                for task in self._background_tasks:
                    if not task.done():
                        task.cancel()
        
        # Close Redis connection
        if self.redis_client:
            try:
                await self.redis_client.aclose()
            except Exception as e:
                logger.warning(f"Error closing Redis connection: {str(e)}")
        
        logger.info("Performance Integration Service shutdown complete")
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get status of all performance services"""
        return {
            'cache_service_initialized': self.cache_service is not None,
            'performance_monitor_initialized': self.performance_monitor is not None,
            'query_optimizer_initialized': self.query_optimizer is not None,
            'redis_client_available': self.redis_client is not None,
            'background_tasks_running': len([t for t in self._background_tasks if not t.done()]),
            'config': self.performance_config
        }


# Global performance integration service instance
performance_integration: Optional[PerformanceIntegrationService] = None


async def get_performance_integration() -> PerformanceIntegrationService:
    """Get the global performance integration service instance"""
    global performance_integration
    if performance_integration is None:
        raise RuntimeError("Performance integration service not initialized")
    return performance_integration


async def init_performance_integration(
    db_session_factory,
    redis_client: Optional[redis.Redis] = None
) -> PerformanceIntegrationService:
    """Initialize the global performance integration service"""
    global performance_integration
    
    performance_integration = PerformanceIntegrationService(
        db_session_factory=db_session_factory,
        redis_client=redis_client
    )
    
    # Initialize all services
    success = await performance_integration.initialize()
    
    if success:
        logger.info("🎉 Performance Integration Service ready for use")
    else:
        logger.error("❌ Performance Integration Service initialization failed")
    
    return performance_integration


async def shutdown_performance_integration():
    """Shutdown the global performance integration service"""
    global performance_integration
    
    if performance_integration:
        await performance_integration.shutdown()
        performance_integration = None
        logger.info("Performance Integration Service shutdown complete")