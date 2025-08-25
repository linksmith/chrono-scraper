"""
Advanced Admin Cache Service for Performance Optimization

This service implements multi-level caching strategies with intelligent invalidation,
cache warming, and performance monitoring specifically optimized for admin operations.
"""

import json
import hashlib
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Callable, Tuple
from dataclasses import dataclass
import redis.asyncio as redis
from redis.asyncio import Redis
from pydantic import BaseModel
import pickle
import zlib
from contextlib import asynccontextmanager
from enum import Enum
import time

logger = logging.getLogger(__name__)


class CacheLevel(str, Enum):
    """Cache levels for different data types"""
    MEMORY = "memory"  # In-process memory cache
    REDIS_FAST = "redis_fast"  # Redis with short TTL
    REDIS_MEDIUM = "redis_medium"  # Redis with medium TTL
    REDIS_PERSISTENT = "redis_persistent"  # Redis with long TTL


class CacheStrategy(str, Enum):
    """Caching strategies"""
    WRITE_THROUGH = "write_through"  # Update cache on write
    WRITE_BEHIND = "write_behind"  # Async cache update
    CACHE_ASIDE = "cache_aside"  # Manual cache management
    REFRESH_AHEAD = "refresh_ahead"  # Proactive refresh


@dataclass
class CacheConfig:
    """Configuration for cache behavior"""
    ttl_seconds: int = 300  # 5 minutes default
    compression: bool = False
    serialization: str = "json"  # json, pickle
    prefix: str = "admin"
    strategy: CacheStrategy = CacheStrategy.CACHE_ASIDE
    auto_refresh: bool = False
    refresh_threshold: float = 0.8  # Refresh when TTL is 80% expired


class CacheMetrics(BaseModel):
    """Cache performance metrics"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_errors: int = 0
    avg_response_time_ms: float = 0.0
    hit_ratio: float = 0.0
    memory_usage_mb: float = 0.0
    compression_ratio: float = 0.0


class AdminCacheService:
    """
    Advanced caching service optimized for admin system operations.
    
    Features:
    - Multi-level caching (memory + Redis)
    - Intelligent cache invalidation
    - Cache warming strategies
    - Performance monitoring
    - Compression and serialization options
    - Pattern-based bulk operations
    """
    
    def __init__(
        self,
        redis_client: Redis,
        default_ttl: int = 300,
        memory_cache_size: int = 1000,
        enable_compression: bool = True,
        enable_metrics: bool = True
    ):
        self.redis_client = redis_client
        self.default_ttl = default_ttl
        self.memory_cache_size = memory_cache_size
        self.enable_compression = enable_compression
        self.enable_metrics = enable_metrics
        
        # In-memory cache for frequently accessed data
        self._memory_cache: Dict[str, Tuple[Any, datetime, int]] = {}  # key -> (value, expiry, access_count)
        self._memory_cache_access_order: List[str] = []
        
        # Cache configuration by pattern
        self._cache_configs: Dict[str, CacheConfig] = {}
        
        # Metrics tracking
        self._metrics: Dict[str, CacheMetrics] = {}
        
        # Initialize default configurations
        self._setup_default_configs()
    
    def _setup_default_configs(self):
        """Setup default cache configurations for admin operations"""
        
        # Admin dashboard metrics - fast cache with auto-refresh
        self._cache_configs["admin:dashboard:*"] = CacheConfig(
            ttl_seconds=60,  # 1 minute
            compression=True,
            strategy=CacheStrategy.REFRESH_AHEAD,
            auto_refresh=True,
            refresh_threshold=0.7
        )
        
        # User management data - medium cache
        self._cache_configs["admin:users:*"] = CacheConfig(
            ttl_seconds=300,  # 5 minutes
            compression=True,
            strategy=CacheStrategy.WRITE_THROUGH
        )
        
        # Audit log analytics - longer cache with compression
        self._cache_configs["admin:audit:analytics:*"] = CacheConfig(
            ttl_seconds=900,  # 15 minutes
            compression=True,
            strategy=CacheStrategy.CACHE_ASIDE
        )
        
        # Security metrics - fast refresh for real-time monitoring
        self._cache_configs["admin:security:*"] = CacheConfig(
            ttl_seconds=30,  # 30 seconds
            compression=False,  # Prioritize speed over space
            strategy=CacheStrategy.REFRESH_AHEAD,
            auto_refresh=True,
            refresh_threshold=0.5
        )
        
        # System stats - medium cache
        self._cache_configs["admin:system:*"] = CacheConfig(
            ttl_seconds=120,  # 2 minutes
            compression=True,
            strategy=CacheStrategy.WRITE_BEHIND
        )
        
        # Backup metadata - longer cache
        self._cache_configs["admin:backup:*"] = CacheConfig(
            ttl_seconds=600,  # 10 minutes
            compression=True,
            strategy=CacheStrategy.CACHE_ASIDE
        )
        
        # User statistics and analytics
        self._cache_configs["admin:user_stats:*"] = CacheConfig(
            ttl_seconds=300,  # 5 minutes
            compression=True,
            strategy=CacheStrategy.CACHE_ASIDE
        )
        
        # IP blocklist and security config
        self._cache_configs["admin:security_config:*"] = CacheConfig(
            ttl_seconds=180,  # 3 minutes
            compression=False,
            strategy=CacheStrategy.WRITE_THROUGH
        )
    
    def get_config_for_key(self, key: str) -> CacheConfig:
        """Get cache configuration for a specific key"""
        for pattern, config in self._cache_configs.items():
            if self._match_pattern(key, pattern):
                return config
        
        # Return default configuration
        return CacheConfig()
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """Simple pattern matching for cache configurations"""
        if pattern.endswith("*"):
            return key.startswith(pattern[:-1])
        return key == pattern
    
    def _generate_cache_key(self, namespace: str, key: str, **kwargs) -> str:
        """Generate a standardized cache key"""
        base_key = f"admin:{namespace}:{key}"
        
        if kwargs:
            # Sort kwargs for consistent key generation
            sorted_kwargs = sorted(kwargs.items())
            kwargs_str = ":".join(f"{k}={v}" for k, v in sorted_kwargs)
            # Hash long parameter strings to keep keys manageable
            if len(kwargs_str) > 100:
                kwargs_hash = hashlib.md5(kwargs_str.encode()).hexdigest()[:16]
                base_key += f":h_{kwargs_hash}"
            else:
                base_key += f":{kwargs_str}"
        
        return base_key
    
    def _serialize_value(self, value: Any, config: CacheConfig) -> bytes:
        """Serialize value based on configuration"""
        if config.serialization == "pickle":
            data = pickle.dumps(value)
        else:  # json
            data = json.dumps(value, default=str).encode('utf-8')
        
        original_size = len(data)
        
        if config.compression:
            data = zlib.compress(data)
            
        return data
    
    def _deserialize_value(self, data: bytes, config: CacheConfig) -> Any:
        """Deserialize value based on configuration"""
        if config.compression:
            data = zlib.decompress(data)
        
        if config.serialization == "pickle":
            return pickle.loads(data)
        else:  # json
            return json.loads(data.decode('utf-8'))
    
    async def get(
        self,
        namespace: str,
        key: str,
        default: Any = None,
        **kwargs
    ) -> Any:
        """
        Get value from cache with intelligent fallback.
        
        Args:
            namespace: Cache namespace (e.g., 'dashboard', 'users')
            key: Cache key
            default: Default value if not found
            **kwargs: Additional parameters for key generation
        
        Returns:
            Cached value or default
        """
        cache_key = self._generate_cache_key(namespace, key, **kwargs)
        config = self.get_config_for_key(cache_key)
        
        start_time = time.time()
        
        try:
            # Try memory cache first
            if cache_key in self._memory_cache:
                value, expiry, access_count = self._memory_cache[cache_key]
                if datetime.now() < expiry:
                    # Update access count and order
                    self._memory_cache[cache_key] = (value, expiry, access_count + 1)
                    self._update_access_order(cache_key)
                    self._record_cache_hit(cache_key, start_time, "memory")
                    return value
                else:
                    # Remove expired entry
                    del self._memory_cache[cache_key]
                    if cache_key in self._memory_cache_access_order:
                        self._memory_cache_access_order.remove(cache_key)
            
            # Try Redis cache
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                value = self._deserialize_value(cached_data, config)
                
                # Store in memory cache for faster future access
                self._store_in_memory(cache_key, value, config.ttl_seconds)
                
                self._record_cache_hit(cache_key, start_time, "redis")
                return value
            
            self._record_cache_miss(cache_key, start_time)
            return default
            
        except Exception as e:
            logger.error(f"Cache get error for key {cache_key}: {str(e)}")
            self._record_cache_error(cache_key, start_time)
            return default
    
    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        **kwargs
    ) -> bool:
        """
        Set value in cache with intelligent storage strategy.
        
        Args:
            namespace: Cache namespace
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            **kwargs: Additional parameters for key generation
        
        Returns:
            True if successful
        """
        cache_key = self._generate_cache_key(namespace, key, **kwargs)
        config = self.get_config_for_key(cache_key)
        
        effective_ttl = ttl or config.ttl_seconds
        
        try:
            # Serialize value
            serialized_data = self._serialize_value(value, config)
            
            # Store in Redis
            await self.redis_client.setex(cache_key, effective_ttl, serialized_data)
            
            # Store in memory cache
            self._store_in_memory(cache_key, value, effective_ttl)
            
            return True
            
        except Exception as e:
            logger.error(f"Cache set error for key {cache_key}: {str(e)}")
            return False
    
    async def delete(self, namespace: str, key: str, **kwargs) -> bool:
        """Delete value from cache"""
        cache_key = self._generate_cache_key(namespace, key, **kwargs)
        
        try:
            # Remove from memory cache
            if cache_key in self._memory_cache:
                del self._memory_cache[cache_key]
                if cache_key in self._memory_cache_access_order:
                    self._memory_cache_access_order.remove(cache_key)
            
            # Remove from Redis
            await self.redis_client.delete(cache_key)
            return True
            
        except Exception as e:
            logger.error(f"Cache delete error for key {cache_key}: {str(e)}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern"""
        try:
            # Get all keys matching pattern
            keys = await self.redis_client.keys(f"admin:{pattern}")
            
            if keys:
                # Remove from memory cache
                for key in keys:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    if key_str in self._memory_cache:
                        del self._memory_cache[key_str]
                        if key_str in self._memory_cache_access_order:
                            self._memory_cache_access_order.remove(key_str)
                
                # Remove from Redis
                await self.redis_client.delete(*keys)
                return len(keys)
            
            return 0
            
        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {str(e)}")
            return 0
    
    async def get_or_set(
        self,
        namespace: str,
        key: str,
        fetch_function: Callable[[], Any],
        ttl: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        Get value from cache or set it using fetch function.
        
        Args:
            namespace: Cache namespace
            key: Cache key
            fetch_function: Function to fetch data if not in cache
            ttl: Time to live in seconds
            **kwargs: Additional parameters for key generation
        
        Returns:
            Cached or fetched value
        """
        # Try to get from cache first
        value = await self.get(namespace, key, **kwargs)
        
        if value is not None:
            return value
        
        # Fetch the data
        try:
            if asyncio.iscoroutinefunction(fetch_function):
                fetched_value = await fetch_function()
            else:
                fetched_value = fetch_function()
            
            # Store in cache
            await self.set(namespace, key, fetched_value, ttl, **kwargs)
            
            return fetched_value
            
        except Exception as e:
            logger.error(f"Error in get_or_set for {namespace}:{key}: {str(e)}")
            raise
    
    async def warm_admin_cache(self):
        """
        Warm cache with frequently accessed admin data.
        This method should be called during application startup.
        """
        logger.info("Starting admin cache warming...")
        
        warming_tasks = []
        
        # Warm dashboard metrics cache
        async def warm_dashboard_metrics():
            try:
                # These would be actual database queries in real implementation
                mock_metrics = {
                    "total_users": 1000,
                    "active_users": 800,
                    "pending_approvals": 15,
                    "recent_logins": 250,
                    "failed_logins_24h": 5,
                    "system_health": "healthy"
                }
                await self.set("dashboard", "system_metrics", mock_metrics, ttl=60)
                logger.debug("Warmed dashboard metrics cache")
            except Exception as e:
                logger.error(f"Error warming dashboard metrics: {str(e)}")
        
        # Warm security metrics cache
        async def warm_security_metrics():
            try:
                mock_security = {
                    "blocked_ips": 25,
                    "active_threats": 3,
                    "security_incidents_open": 2,
                    "high_risk_sessions": 1
                }
                await self.set("security", "current_status", mock_security, ttl=30)
                logger.debug("Warmed security metrics cache")
            except Exception as e:
                logger.error(f"Error warming security metrics: {str(e)}")
        
        # Warm system stats cache
        async def warm_system_stats():
            try:
                mock_system = {
                    "cpu_usage": 45.2,
                    "memory_usage": 67.8,
                    "disk_usage": 34.1,
                    "active_connections": 150,
                    "uptime_hours": 720
                }
                await self.set("system", "performance", mock_system, ttl=120)
                logger.debug("Warmed system stats cache")
            except Exception as e:
                logger.error(f"Error warming system stats: {str(e)}")
        
        warming_tasks.extend([
            warm_dashboard_metrics(),
            warm_security_metrics(),
            warm_system_stats()
        ])
        
        # Execute all warming tasks concurrently
        await asyncio.gather(*warming_tasks, return_exceptions=True)
        
        logger.info("Completed admin cache warming")
    
    def _store_in_memory(self, key: str, value: Any, ttl_seconds: int):
        """Store value in memory cache with LRU eviction"""
        expiry = datetime.now() + timedelta(seconds=ttl_seconds)
        
        # Add to cache
        self._memory_cache[key] = (value, expiry, 1)  # access_count starts at 1
        
        # Update access order
        self._update_access_order(key)
        
        # Evict if necessary using LRU with access frequency consideration
        while len(self._memory_cache) > self.memory_cache_size:
            # Find least recently used item with lowest access count
            oldest_key = min(
                self._memory_cache_access_order[:10],  # Check first 10 items
                key=lambda k: (
                    self._memory_cache[k][2],  # access count (lower is better for eviction)
                    self._memory_cache_access_order.index(k)  # recency (higher index is better for eviction)
                )
            )
            
            self._memory_cache_access_order.remove(oldest_key)
            if oldest_key in self._memory_cache:
                del self._memory_cache[oldest_key]
    
    def _update_access_order(self, key: str):
        """Update access order for LRU eviction"""
        if key in self._memory_cache_access_order:
            self._memory_cache_access_order.remove(key)
        self._memory_cache_access_order.append(key)
    
    def _record_cache_hit(self, key: str, start_time: float, source: str = "redis"):
        """Record cache hit metrics"""
        if not self.enable_metrics:
            return
        
        namespace = key.split(':')[1] if ':' in key else 'unknown'
        response_time = (time.time() - start_time) * 1000
        
        if namespace not in self._metrics:
            self._metrics[namespace] = CacheMetrics()
        
        metrics = self._metrics[namespace]
        metrics.total_requests += 1
        metrics.cache_hits += 1
        metrics.avg_response_time_ms = (
            (metrics.avg_response_time_ms * (metrics.total_requests - 1) + response_time) /
            metrics.total_requests
        )
        metrics.hit_ratio = metrics.cache_hits / metrics.total_requests
    
    def _record_cache_miss(self, key: str, start_time: float):
        """Record cache miss metrics"""
        if not self.enable_metrics:
            return
        
        namespace = key.split(':')[1] if ':' in key else 'unknown'
        response_time = (time.time() - start_time) * 1000
        
        if namespace not in self._metrics:
            self._metrics[namespace] = CacheMetrics()
        
        metrics = self._metrics[namespace]
        metrics.total_requests += 1
        metrics.cache_misses += 1
        metrics.avg_response_time_ms = (
            (metrics.avg_response_time_ms * (metrics.total_requests - 1) + response_time) /
            metrics.total_requests
        )
        metrics.hit_ratio = metrics.cache_hits / metrics.total_requests if metrics.total_requests > 0 else 0.0
    
    def _record_cache_error(self, key: str, start_time: float):
        """Record cache error metrics"""
        if not self.enable_metrics:
            return
        
        namespace = key.split(':')[1] if ':' in key else 'unknown'
        
        if namespace not in self._metrics:
            self._metrics[namespace] = CacheMetrics()
        
        metrics = self._metrics[namespace]
        metrics.cache_errors += 1
    
    async def get_metrics(self, namespace: Optional[str] = None) -> Dict[str, CacheMetrics]:
        """Get cache performance metrics"""
        if namespace:
            return {namespace: self._metrics.get(namespace, CacheMetrics())}
        return self._metrics.copy()
    
    async def get_cache_info(self) -> Dict[str, Any]:
        """Get detailed cache information"""
        try:
            redis_info = await self.redis_client.info('memory')
            
            return {
                "memory_cache_size": len(self._memory_cache),
                "memory_cache_max_size": self.memory_cache_size,
                "redis_memory_usage": redis_info.get('used_memory_human', 'N/A'),
                "redis_connected_clients": redis_info.get('connected_clients', 'N/A'),
                "cache_configs": len(self._cache_configs),
                "metrics_enabled": self.enable_metrics,
                "compression_enabled": self.enable_compression,
                "total_cache_keys": sum(len(self._metrics[ns].cache_hits) for ns in self._metrics)
            }
        except Exception as e:
            logger.error(f"Error getting cache info: {str(e)}")
            return {
                "error": str(e),
                "memory_cache_size": len(self._memory_cache),
                "memory_cache_max_size": self.memory_cache_size
            }
    
    async def clear_all_caches(self) -> bool:
        """Clear all caches (use with caution)"""
        try:
            # Clear memory cache
            self._memory_cache.clear()
            self._memory_cache_access_order.clear()
            
            # Clear Redis admin namespace
            await self.delete_pattern("*")
            
            # Reset metrics
            self._metrics.clear()
            
            logger.info("All admin caches cleared successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing all caches: {str(e)}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform cache system health check"""
        try:
            # Test Redis connection
            await self.redis_client.ping()
            redis_healthy = True
        except Exception as e:
            redis_healthy = False
            logger.error(f"Redis health check failed: {str(e)}")
        
        # Test basic cache operations
        test_key = "health_check"
        test_value = {"timestamp": datetime.now().isoformat(), "test": True}
        
        cache_operations_healthy = True
        try:
            await self.set("system", test_key, test_value, ttl=60)
            retrieved_value = await self.get("system", test_key)
            if retrieved_value != test_value:
                cache_operations_healthy = False
            await self.delete("system", test_key)
        except Exception as e:
            cache_operations_healthy = False
            logger.error(f"Cache operations health check failed: {str(e)}")
        
        return {
            "redis_healthy": redis_healthy,
            "cache_operations_healthy": cache_operations_healthy,
            "memory_cache_size": len(self._memory_cache),
            "memory_cache_utilization": len(self._memory_cache) / self.memory_cache_size * 100,
            "overall_healthy": redis_healthy and cache_operations_healthy,
            "metrics_summary": {
                namespace: {
                    "hit_ratio": metrics.hit_ratio,
                    "total_requests": metrics.total_requests,
                    "avg_response_time_ms": metrics.avg_response_time_ms
                }
                for namespace, metrics in self._metrics.items()
            }
        }
    
    @asynccontextmanager
    async def cache_lock(self, namespace: str, key: str, timeout: int = 30):
        """Distributed cache lock using Redis"""
        lock_key = self._generate_cache_key("locks", f"{namespace}:{key}")
        lock_value = hashlib.md5(f"{datetime.now().isoformat()}".encode()).hexdigest()
        
        try:
            # Acquire lock
            acquired = await self.redis_client.set(
                lock_key, 
                lock_value, 
                ex=timeout, 
                nx=True
            )
            
            if not acquired:
                raise Exception(f"Could not acquire lock for {namespace}:{key}")
            
            yield
            
        finally:
            # Release lock (only if we own it)
            try:
                current_value = await self.redis_client.get(lock_key)
                if current_value and current_value.decode('utf-8') == lock_value:
                    await self.redis_client.delete(lock_key)
            except Exception as e:
                logger.error(f"Error releasing lock for {namespace}:{key}: {str(e)}")


# Global admin cache service instance
admin_cache_service: Optional[AdminCacheService] = None


async def get_admin_cache_service() -> AdminCacheService:
    """Get the global admin cache service instance"""
    global admin_cache_service
    if admin_cache_service is None:
        raise RuntimeError("Admin cache service not initialized. Call init_admin_cache_service() first.")
    return admin_cache_service


async def init_admin_cache_service(
    redis_client: Redis,
    default_ttl: int = 300,
    memory_cache_size: int = 1000,
    enable_compression: bool = True,
    enable_metrics: bool = True
) -> AdminCacheService:
    """Initialize the global admin cache service"""
    global admin_cache_service
    
    admin_cache_service = AdminCacheService(
        redis_client=redis_client,
        default_ttl=default_ttl,
        memory_cache_size=memory_cache_size,
        enable_compression=enable_compression,
        enable_metrics=enable_metrics
    )
    
    # Perform initial health check
    health = await admin_cache_service.health_check()
    if not health["overall_healthy"]:
        logger.warning("Admin cache service initialized but health check failed")
    else:
        logger.info("Admin cache service initialized successfully")
    
    # Warm the cache
    await admin_cache_service.warm_admin_cache()
    
    return admin_cache_service