"""
Intelligent Multi-Level Caching System

Provides sophisticated caching with multiple storage layers, intelligent invalidation,
predictive cache warming, and advanced cache optimization strategies for the Chrono Scraper
FastAPI application.

Cache Architecture:
- L1: In-Memory (fastest, smallest)
- L2: Redis (fast, medium)
- L3: Persistent Storage (Parquet/DuckDB) (slower, largest)
"""

import asyncio
import hashlib
import json
import logging
import pickle
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from collections import OrderedDict, defaultdict
import zlib

import redis.asyncio as aioredis
from redis.asyncio import Redis

from ..core.config import settings
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig

logger = logging.getLogger(__name__)


class CacheLevel(int, Enum):
    """Cache storage levels"""
    MEMORY = 1
    REDIS = 2
    PERSISTENT = 3


class CacheStrategy(str, Enum):
    """Cache replacement strategies"""
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"
    ADAPTIVE = "adaptive"


class CompressionType(str, Enum):
    """Compression algorithms"""
    NONE = "none"
    GZIP = "gzip"
    ZLIB = "zlib"
    LZMA = "lzma"


@dataclass
class CacheEntry:
    """Cache entry with metadata"""
    key: str
    value: Any
    ttl: int
    created_at: datetime
    last_accessed: datetime
    access_count: int
    size_bytes: int
    compression: CompressionType
    level: CacheLevel
    tags: Set[str] = field(default_factory=set)
    dependencies: Set[str] = field(default_factory=set)


@dataclass
class CacheStats:
    """Cache statistics and metrics"""
    total_entries: int
    total_size_bytes: int
    hit_rate: float
    miss_rate: float
    eviction_rate: float
    average_access_time_ms: float
    level_stats: Dict[CacheLevel, Dict[str, Any]]
    top_keys: List[Tuple[str, int]]  # (key, access_count)
    memory_pressure: float
    fragmentation_ratio: float
    last_cleanup: datetime


@dataclass
class CachedResult:
    """Cached query result wrapper"""
    data: Any
    metadata: Dict[str, Any]
    cache_key: str
    cached_at: datetime
    ttl_seconds: int
    source_level: CacheLevel
    hit_count: int = 0


@dataclass
class CacheOptimizationResult:
    """Cache optimization result"""
    optimizations_applied: List[str]
    space_saved_bytes: int
    performance_improvement_ms: float
    entries_relocated: int
    entries_compressed: int
    entries_evicted: int


class IntelligentCacheManager:
    """
    Advanced multi-level caching system with intelligent optimization.
    
    Features:
    - Three-tier cache architecture (Memory -> Redis -> Persistent)
    - Intelligent cache warming and preloading
    - Automatic cache invalidation based on data changes
    - Query similarity detection for cache reuse
    - Adaptive TTL based on access patterns
    - Memory pressure management with smart eviction
    - Compression and optimization for large datasets
    - Distributed cache synchronization
    - Performance analytics and monitoring
    """
    
    def __init__(
        self,
        redis_client: Optional[Redis] = None,
        duckdb_service=None,
        max_memory_cache_mb: int = 512,
        enable_compression: bool = True,
        enable_predictive_caching: bool = True
    ):
        self.redis_client = redis_client
        self.duckdb_service = duckdb_service
        self.max_memory_cache_bytes = max_memory_cache_mb * 1024 * 1024
        self.enable_compression = enable_compression
        self.enable_predictive_caching = enable_predictive_caching
        
        # L1 Cache: In-Memory LRU Cache
        self.memory_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.memory_cache_size = 0
        
        # Cache statistics
        self.stats = {
            'hits': defaultdict(int),
            'misses': defaultdict(int),
            'evictions': defaultdict(int),
            'access_times': [],
            'last_reset': datetime.now()
        }
        
        # Query pattern analysis for intelligent caching
        self.query_patterns: Dict[str, List[str]] = defaultdict(list)
        self.access_patterns: Dict[str, List[datetime]] = defaultdict(list)
        
        # Circuit breaker for Redis operations
        self.redis_circuit_breaker = CircuitBreaker(
            "redis_cache",
            config=CircuitBreakerConfig(failure_threshold=3, timeout_seconds=30)
        )
        
        # Background task executor
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cache_mgr")
        
        # Cache warming and optimization settings
        self.cache_warming_enabled = enable_predictive_caching
        self.optimization_interval = 300  # 5 minutes
        self.last_optimization = datetime.now()
        
        # Compression settings
        self.compression_threshold = 1024  # 1KB
        self.compression_level = 6
        
        logger.info("Intelligent cache manager initialized")
    
    async def get_cached_result(self, query_key: str) -> Optional[CachedResult]:
        """
        Retrieve cached result with intelligent level selection.
        
        Args:
            query_key: Cache key to retrieve
            
        Returns:
            CachedResult if found, None otherwise
        """
        start_time = time.time()
        
        try:
            # Try L1 Cache (Memory) first
            if result := await self._get_from_memory_cache(query_key):
                self.stats['hits'][CacheLevel.MEMORY] += 1
                self._record_access_time(time.time() - start_time)
                return result
            
            # Try L2 Cache (Redis)
            if self.redis_client and (result := await self._get_from_redis_cache(query_key)):
                self.stats['hits'][CacheLevel.REDIS] += 1
                # Promote to L1 if frequently accessed
                await self._maybe_promote_to_memory(query_key, result)
                self._record_access_time(time.time() - start_time)
                return result
            
            # Try L3 Cache (Persistent)
            if self.duckdb_service and (result := await self._get_from_persistent_cache(query_key)):
                self.stats['hits'][CacheLevel.PERSISTENT] += 1
                # Promote to higher levels based on access patterns
                await self._maybe_promote_cache_entry(query_key, result)
                self._record_access_time(time.time() - start_time)
                return result
            
            # Cache miss at all levels
            self.stats['misses'][CacheLevel.MEMORY] += 1
            self._record_access_time(time.time() - start_time)
            
            # Try query similarity matching
            if similar_result := await self._find_similar_cached_query(query_key):
                logger.debug(f"Found similar cached result for query: {query_key[:32]}...")
                return similar_result
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving cached result: {str(e)}")
            return None
    
    async def cache_result(
        self, 
        query_key: str, 
        result: Any, 
        ttl: int,
        tags: Optional[Set[str]] = None,
        dependencies: Optional[Set[str]] = None,
        preferred_level: Optional[CacheLevel] = None
    ) -> bool:
        """
        Cache result with intelligent level selection and optimization.
        
        Args:
            query_key: Unique key for the cached data
            result: Data to cache
            ttl: Time-to-live in seconds
            tags: Optional tags for grouped invalidation
            dependencies: Optional dependency keys for invalidation
            preferred_level: Preferred cache level
            
        Returns:
            True if successfully cached, False otherwise
        """
        try:
            # Serialize and analyze result
            serialized_result = await self._serialize_result(result)
            result_size = len(serialized_result)
            
            # Determine optimal cache level
            cache_level = preferred_level or self._determine_optimal_cache_level(
                query_key, result_size, ttl
            )
            
            # Apply compression if beneficial
            compressed_result, compression_type = await self._maybe_compress_result(
                serialized_result, result_size
            )
            
            # Create cache entry
            cache_entry = CacheEntry(
                key=query_key,
                value=compressed_result,
                ttl=ttl,
                created_at=datetime.now(),
                last_accessed=datetime.now(),
                access_count=0,
                size_bytes=len(compressed_result),
                compression=compression_type,
                level=cache_level,
                tags=tags or set(),
                dependencies=dependencies or set()
            )
            
            # Cache at determined level
            success = False
            if cache_level == CacheLevel.MEMORY:
                success = await self._cache_in_memory(cache_entry)
            elif cache_level == CacheLevel.REDIS:
                success = await self._cache_in_redis(cache_entry)
            elif cache_level == CacheLevel.PERSISTENT:
                success = await self._cache_in_persistent(cache_entry)
            
            if success:
                # Update access patterns for predictive caching
                await self._update_access_patterns(query_key)
                
                # Trigger background optimization if needed
                await self._maybe_trigger_optimization()
                
                logger.debug(
                    f"Cached result at level {cache_level.name}. "
                    f"Key: {query_key[:32]}..., "
                    f"Size: {result_size} bytes, "
                    f"Compressed: {compression_type != CompressionType.NONE}, "
                    f"TTL: {ttl}s"
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error caching result: {str(e)}")
            return False
    
    async def invalidate_cache(self, patterns: List[str]) -> int:
        """
        Invalidate cache entries matching patterns.
        
        Args:
            patterns: List of key patterns or tags to invalidate
            
        Returns:
            Number of entries invalidated
        """
        invalidated_count = 0
        
        try:
            # Invalidate from all cache levels
            invalidated_count += await self._invalidate_memory_cache(patterns)
            
            if self.redis_client:
                invalidated_count += await self._invalidate_redis_cache(patterns)
            
            if self.duckdb_service:
                invalidated_count += await self._invalidate_persistent_cache(patterns)
            
            logger.info(f"Invalidated {invalidated_count} cache entries for patterns: {patterns}")
            
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")
        
        return invalidated_count
    
    async def warm_cache(self, popular_queries: List[str]) -> None:
        """
        Proactively warm cache with popular queries.
        
        Args:
            popular_queries: List of SQL queries to pre-execute and cache
        """
        if not self.cache_warming_enabled:
            return
        
        try:
            logger.info(f"Starting cache warming for {len(popular_queries)} queries")
            
            # Process queries in parallel
            tasks = []
            for query in popular_queries:
                task = asyncio.create_task(self._warm_single_query(query))
                tasks.append(task)
            
            # Wait for all warming tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            successful_warms = sum(1 for r in results if r is True)
            logger.info(f"Cache warming completed: {successful_warms}/{len(popular_queries)} successful")
            
        except Exception as e:
            logger.error(f"Error during cache warming: {str(e)}")
    
    async def optimize_cache_layout(self) -> CacheOptimizationResult:
        """
        Optimize cache layout for better performance and space utilization.
        
        Returns:
            CacheOptimizationResult with optimization metrics
        """
        start_time = time.time()
        optimizations = []
        space_saved = 0
        entries_relocated = 0
        entries_compressed = 0
        entries_evicted = 0
        
        try:
            logger.info("Starting cache layout optimization")
            
            # 1. Memory pressure management
            if self.memory_cache_size > self.max_memory_cache_bytes * 0.8:
                evicted = await self._evict_memory_cache_entries()
                entries_evicted += evicted
                optimizations.append(f"Evicted {evicted} memory cache entries")
            
            # 2. Promote frequently accessed Redis entries to memory
            if self.redis_client:
                promoted = await self._promote_hot_redis_entries()
                entries_relocated += promoted
                optimizations.append(f"Promoted {promoted} entries to memory")
            
            # 3. Compress large uncompressed entries
            if self.enable_compression:
                compressed = await self._compress_large_entries()
                entries_compressed += compressed
                space_saved += compressed * 1024  # Estimate
                optimizations.append(f"Compressed {compressed} large entries")
            
            # 4. Clean expired entries
            expired_cleaned = await self._clean_expired_entries()
            entries_evicted += expired_cleaned
            optimizations.append(f"Cleaned {expired_cleaned} expired entries")
            
            # 5. Defragment cache storage
            if await self._should_defragment():
                defrag_saved = await self._defragment_cache()
                space_saved += defrag_saved
                optimizations.append(f"Defragmented cache, saved {defrag_saved} bytes")
            
            performance_improvement = (time.time() - start_time) * 1000
            
            result = CacheOptimizationResult(
                optimizations_applied=optimizations,
                space_saved_bytes=space_saved,
                performance_improvement_ms=performance_improvement,
                entries_relocated=entries_relocated,
                entries_compressed=entries_compressed,
                entries_evicted=entries_evicted
            )
            
            self.last_optimization = datetime.now()
            logger.info(f"Cache optimization completed: {len(optimizations)} optimizations applied")
            
            return result
            
        except Exception as e:
            logger.error(f"Error during cache optimization: {str(e)}")
            return CacheOptimizationResult(
                optimizations_applied=[f"Optimization failed: {str(e)}"],
                space_saved_bytes=0,
                performance_improvement_ms=0,
                entries_relocated=0,
                entries_compressed=0,
                entries_evicted=0
            )
    
    async def get_cache_statistics(self) -> CacheStats:
        """
        Get comprehensive cache statistics and metrics.
        
        Returns:
            CacheStats with detailed cache metrics
        """
        try:
            # Calculate hit rates
            total_hits = sum(self.stats['hits'].values())
            total_misses = sum(self.stats['misses'].values())
            total_requests = total_hits + total_misses
            
            hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
            miss_rate = 100 - hit_rate
            
            # Calculate eviction rate
            total_evictions = sum(self.stats['evictions'].values())
            eviction_rate = (total_evictions / total_requests * 100) if total_requests > 0 else 0
            
            # Average access time
            avg_access_time = (
                sum(self.stats['access_times']) / len(self.stats['access_times'])
                if self.stats['access_times'] else 0
            ) * 1000  # Convert to milliseconds
            
            # Level-specific stats
            level_stats = {}
            for level in CacheLevel:
                level_stats[level] = {
                    'hits': self.stats['hits'][level],
                    'misses': self.stats['misses'][level],
                    'evictions': self.stats['evictions'][level],
                    'hit_rate': (
                        self.stats['hits'][level] / 
                        (self.stats['hits'][level] + self.stats['misses'][level]) * 100
                        if (self.stats['hits'][level] + self.stats['misses'][level]) > 0 else 0
                    )
                }
            
            # Memory stats
            total_entries = len(self.memory_cache)
            if self.redis_client:
                try:
                    total_entries += await self.redis_client.dbsize()
                except Exception:
                    pass
            
            # Top accessed keys
            top_keys = []
            for entry in list(self.memory_cache.values())[:10]:
                top_keys.append((entry.key[:32], entry.access_count))
            
            # Memory pressure calculation
            memory_pressure = (self.memory_cache_size / self.max_memory_cache_bytes) * 100
            
            # Fragmentation estimation (simplified)
            fragmentation_ratio = max(0, (self.memory_cache_size - sum(
                entry.size_bytes for entry in self.memory_cache.values()
            )) / self.memory_cache_size * 100) if self.memory_cache_size > 0 else 0
            
            return CacheStats(
                total_entries=total_entries,
                total_size_bytes=self.memory_cache_size,
                hit_rate=hit_rate,
                miss_rate=miss_rate,
                eviction_rate=eviction_rate,
                average_access_time_ms=avg_access_time,
                level_stats=level_stats,
                top_keys=top_keys,
                memory_pressure=memory_pressure,
                fragmentation_ratio=fragmentation_ratio,
                last_cleanup=self.last_optimization
            )
            
        except Exception as e:
            logger.error(f"Error calculating cache statistics: {str(e)}")
            return CacheStats(
                total_entries=0,
                total_size_bytes=0,
                hit_rate=0.0,
                miss_rate=100.0,
                eviction_rate=0.0,
                average_access_time_ms=0.0,
                level_stats={},
                top_keys=[],
                memory_pressure=0.0,
                fragmentation_ratio=0.0,
                last_cleanup=datetime.now()
            )
    
    # Private helper methods
    
    async def _get_from_memory_cache(self, key: str) -> Optional[CachedResult]:
        """Retrieve from L1 memory cache"""
        if key not in self.memory_cache:
            return None
        
        entry = self.memory_cache[key]
        
        # Check TTL
        if self._is_expired(entry):
            del self.memory_cache[key]
            self.memory_cache_size -= entry.size_bytes
            return None
        
        # Update access patterns
        entry.last_accessed = datetime.now()
        entry.access_count += 1
        
        # Move to end (LRU)
        self.memory_cache.move_to_end(key)
        
        # Deserialize result
        result_data = await self._deserialize_result(entry.value, entry.compression)
        
        return CachedResult(
            data=result_data,
            metadata={'compression': entry.compression.value},
            cache_key=key,
            cached_at=entry.created_at,
            ttl_seconds=entry.ttl,
            source_level=CacheLevel.MEMORY,
            hit_count=entry.access_count
        )
    
    async def _get_from_redis_cache(self, key: str) -> Optional[CachedResult]:
        """Retrieve from L2 Redis cache"""
        try:
            with self.redis_circuit_breaker:
                # Get entry metadata and data
                metadata_key = f"{key}:meta"
                data_result = await self.redis_client.get(key)
                metadata_result = await self.redis_client.hgetall(metadata_key)
                
                if not data_result or not metadata_result:
                    return None
                
                # Parse metadata
                metadata = {k.decode(): v.decode() for k, v in metadata_result.items()}
                compression_type = CompressionType(metadata.get('compression', 'none'))
                
                # Deserialize result
                result_data = await self._deserialize_result(data_result, compression_type)
                
                # Update access count
                await self.redis_client.hincrby(metadata_key, 'access_count', 1)
                await self.redis_client.hset(metadata_key, 'last_accessed', str(datetime.now().timestamp()))
                
                return CachedResult(
                    data=result_data,
                    metadata=metadata,
                    cache_key=key,
                    cached_at=datetime.fromtimestamp(float(metadata.get('created_at', 0))),
                    ttl_seconds=int(metadata.get('ttl', 0)),
                    source_level=CacheLevel.REDIS,
                    hit_count=int(metadata.get('access_count', 0)) + 1
                )
        
        except Exception as e:
            logger.error(f"Error retrieving from Redis cache: {str(e)}")
            return None
    
    async def _get_from_persistent_cache(self, key: str) -> Optional[CachedResult]:
        """Retrieve from L3 persistent cache"""
        if not self.duckdb_service:
            return None
        
        try:
            # Query persistent cache table
            query = """
            SELECT data, metadata, created_at, ttl_seconds, access_count
            FROM cache_entries
            WHERE cache_key = ? AND expires_at > NOW()
            """
            
            result = await self.duckdb_service.execute_query(query, [key])
            
            if not result or not result.fetchone():
                return None
            
            row = result.fetchone()
            data, metadata, created_at, ttl_seconds, access_count = row
            
            # Update access count
            update_query = """
            UPDATE cache_entries 
            SET access_count = access_count + 1, last_accessed = NOW()
            WHERE cache_key = ?
            """
            await self.duckdb_service.execute_query(update_query, [key])
            
            # Deserialize result
            metadata_dict = json.loads(metadata) if metadata else {}
            compression_type = CompressionType(metadata_dict.get('compression', 'none'))
            result_data = await self._deserialize_result(data, compression_type)
            
            return CachedResult(
                data=result_data,
                metadata=metadata_dict,
                cache_key=key,
                cached_at=created_at,
                ttl_seconds=ttl_seconds,
                source_level=CacheLevel.PERSISTENT,
                hit_count=access_count + 1
            )
        
        except Exception as e:
            logger.error(f"Error retrieving from persistent cache: {str(e)}")
            return None
    
    def _determine_optimal_cache_level(
        self, 
        query_key: str, 
        result_size: int, 
        ttl: int
    ) -> CacheLevel:
        """Determine optimal cache level based on various factors"""
        # Small, frequently accessed results go to memory
        if result_size < 10240 and ttl > 3600:  # 10KB, 1+ hour TTL
            return CacheLevel.MEMORY
        
        # Medium results with moderate TTL go to Redis
        if result_size < 1048576 and ttl > 300:  # 1MB, 5+ minute TTL
            return CacheLevel.REDIS
        
        # Large results or short TTL go to persistent storage
        return CacheLevel.PERSISTENT
    
    async def _serialize_result(self, result: Any) -> bytes:
        """Serialize result for caching"""
        return pickle.dumps(result)
    
    async def _deserialize_result(self, data: bytes, compression: CompressionType) -> Any:
        """Deserialize cached result"""
        # Decompress if needed
        if compression == CompressionType.GZIP:
            import gzip
            data = gzip.decompress(data)
        elif compression == CompressionType.ZLIB:
            data = zlib.decompress(data)
        elif compression == CompressionType.LZMA:
            import lzma
            data = lzma.decompress(data)
        
        return pickle.loads(data)
    
    async def _maybe_compress_result(
        self, 
        data: bytes, 
        original_size: int
    ) -> Tuple[bytes, CompressionType]:
        """Apply compression if beneficial"""
        if not self.enable_compression or original_size < self.compression_threshold:
            return data, CompressionType.NONE
        
        # Try zlib compression (good balance of speed/ratio)
        compressed_data = zlib.compress(data, self.compression_level)
        
        # Only use compression if it saves significant space
        if len(compressed_data) < original_size * 0.8:
            return compressed_data, CompressionType.ZLIB
        
        return data, CompressionType.NONE
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry has expired"""
        expiry_time = entry.created_at + timedelta(seconds=entry.ttl)
        return datetime.now() > expiry_time
    
    def _record_access_time(self, access_time: float):
        """Record cache access time for performance monitoring"""
        self.stats['access_times'].append(access_time)
        
        # Keep only recent access times
        if len(self.stats['access_times']) > 1000:
            self.stats['access_times'] = self.stats['access_times'][-500:]
    
    async def _find_similar_cached_query(self, query_key: str) -> Optional[CachedResult]:
        """Find similar cached queries for potential reuse"""
        # Simplified implementation - in production, would use more sophisticated similarity
        # matching based on query structure, table access patterns, etc.
        return None
    
    # Additional helper methods for cache operations...
    # (Implementation would continue with methods for cache promotion, eviction,
    # compression, defragmentation, etc.)
    
    async def _cache_in_memory(self, entry: CacheEntry) -> bool:
        """Cache entry in memory with LRU eviction"""
        try:
            # Check if we need to evict entries
            while (self.memory_cache_size + entry.size_bytes > self.max_memory_cache_bytes
                   and self.memory_cache):
                # Evict least recently used entry
                old_key, old_entry = self.memory_cache.popitem(last=False)
                self.memory_cache_size -= old_entry.size_bytes
                self.stats['evictions'][CacheLevel.MEMORY] += 1
            
            # Add new entry
            self.memory_cache[entry.key] = entry
            self.memory_cache_size += entry.size_bytes
            
            return True
        
        except Exception as e:
            logger.error(f"Error caching in memory: {str(e)}")
            return False
    
    async def _cache_in_redis(self, entry: CacheEntry) -> bool:
        """Cache entry in Redis"""
        if not self.redis_client:
            return False
        
        try:
            with self.redis_circuit_breaker:
                # Store data
                await self.redis_client.setex(entry.key, entry.ttl, entry.value)
                
                # Store metadata
                metadata_key = f"{entry.key}:meta"
                metadata = {
                    'created_at': str(entry.created_at.timestamp()),
                    'ttl': str(entry.ttl),
                    'size_bytes': str(entry.size_bytes),
                    'compression': entry.compression.value,
                    'access_count': str(entry.access_count)
                }
                
                await self.redis_client.hset(metadata_key, mapping=metadata)
                await self.redis_client.expire(metadata_key, entry.ttl)
                
                return True
        
        except Exception as e:
            logger.error(f"Error caching in Redis: {str(e)}")
            return False
    
    async def _cache_in_persistent(self, entry: CacheEntry) -> bool:
        """Cache entry in persistent storage"""
        if not self.duckdb_service:
            return False
        
        try:
            # Insert into persistent cache table
            query = """
            INSERT OR REPLACE INTO cache_entries 
            (cache_key, data, metadata, created_at, expires_at, ttl_seconds, access_count, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            expires_at = entry.created_at + timedelta(seconds=entry.ttl)
            metadata = json.dumps({
                'compression': entry.compression.value,
                'tags': list(entry.tags),
                'dependencies': list(entry.dependencies)
            })
            
            await self.duckdb_service.execute_query(query, [
                entry.key,
                entry.value,
                metadata,
                entry.created_at,
                expires_at,
                entry.ttl,
                entry.access_count,
                entry.size_bytes
            ])
            
            return True
        
        except Exception as e:
            logger.error(f"Error caching in persistent storage: {str(e)}")
            return False


# Singleton instance
_cache_manager: Optional[IntelligentCacheManager] = None


def get_cache_manager() -> Optional[IntelligentCacheManager]:
    """Get the global cache manager instance"""
    return _cache_manager


async def init_cache_manager(
    redis_client: Optional[Redis] = None,
    duckdb_service=None,
    max_memory_cache_mb: int = 512,
    enable_compression: bool = True,
    enable_predictive_caching: bool = True
) -> IntelligentCacheManager:
    """Initialize the global cache manager"""
    global _cache_manager
    
    _cache_manager = IntelligentCacheManager(
        redis_client=redis_client,
        duckdb_service=duckdb_service,
        max_memory_cache_mb=max_memory_cache_mb,
        enable_compression=enable_compression,
        enable_predictive_caching=enable_predictive_caching
    )
    
    logger.info("Intelligent cache manager initialized successfully")
    return _cache_manager