"""
Redis-based caching service for page lookups and deduplication
"""
import redis
import json
import logging
from typing import Optional, List, Tuple, Dict
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)


class PageCacheService:
    """Redis-based caching for page lookups and deduplication"""
    
    def __init__(self):
        try:
            self.redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=getattr(settings, 'REDIS_PORT', 6379),
                db=getattr(settings, 'REDIS_DB', 0),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.redis.ping()
            self.ttl = 3600  # 1 hour TTL
            logger.info("Page cache service initialized successfully")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Redis not available, using mock cache: {e}")
            self.redis = None
            self.ttl = 3600
    
    def _get_page_key(self, url: str, timestamp: int) -> str:
        """Generate cache key for page existence"""
        return f"page_exists:{hash(url)}:{timestamp}"
    
    def _get_project_pages_key(self, project_id: int) -> str:
        """Generate cache key for project pages"""
        return f"project_pages:{project_id}"
    
    def _get_user_projects_key(self, user_id: int) -> str:
        """Generate cache key for user projects"""
        return f"user_projects:{user_id}"
    
    async def get_page_exists(self, url: str, timestamp: int) -> Optional[UUID]:
        """Check if page exists in cache"""
        if not self.redis:
            return None
        
        try:
            key = self._get_page_key(url, timestamp)
            page_id_str = self.redis.get(key)
            return UUID(page_id_str) if page_id_str else None
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None
    
    async def set_page_exists(self, url: str, timestamp: int, page_id: UUID) -> None:
        """Cache page existence"""
        if not self.redis:
            return
        
        try:
            key = self._get_page_key(url, timestamp)
            self.redis.setex(key, self.ttl, str(page_id))
        except Exception as e:
            logger.warning(f"Cache set error: {e}")
    
    async def bulk_check_pages(
        self,
        url_timestamp_pairs: List[Tuple[str, int]]
    ) -> Dict[Tuple[str, int], UUID]:
        """Bulk check cache for existing pages"""
        if not self.redis or not url_timestamp_pairs:
            return {}
        
        try:
            pipeline = self.redis.pipeline()
            keys = []
            
            for url, timestamp in url_timestamp_pairs:
                key = self._get_page_key(url, timestamp)
                keys.append(key)
                pipeline.get(key)
            
            results = pipeline.execute()
            
            existing = {}
            for (url, timestamp), page_id_str in zip(url_timestamp_pairs, results):
                if page_id_str:
                    try:
                        existing[(url, timestamp)] = UUID(page_id_str)
                    except ValueError:
                        logger.warning(f"Invalid UUID in cache: {page_id_str}")
            
            return existing
            
        except Exception as e:
            logger.warning(f"Bulk cache check error: {e}")
            return {}
    
    async def bulk_set_pages(
        self,
        page_data: List[Tuple[str, int, UUID]]
    ) -> None:
        """Bulk cache page existence"""
        if not self.redis or not page_data:
            return
        
        try:
            pipeline = self.redis.pipeline()
            
            for url, timestamp, page_id in page_data:
                key = self._get_page_key(url, timestamp)
                pipeline.setex(key, self.ttl, str(page_id))
            
            pipeline.execute()
            
        except Exception as e:
            logger.warning(f"Bulk cache set error: {e}")
    
    async def invalidate_page(self, url: str, timestamp: int) -> None:
        """Remove page from cache"""
        if not self.redis:
            return
        
        try:
            key = self._get_page_key(url, timestamp)
            self.redis.delete(key)
        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
    
    async def cache_project_pages(
        self,
        project_id: int,
        page_ids: List[UUID],
        ttl: Optional[int] = None
    ) -> None:
        """Cache list of page IDs for a project"""
        if not self.redis:
            return
        
        try:
            key = self._get_project_pages_key(project_id)
            page_ids_str = json.dumps([str(pid) for pid in page_ids])
            cache_ttl = ttl or self.ttl
            self.redis.setex(key, cache_ttl, page_ids_str)
        except Exception as e:
            logger.warning(f"Project pages cache error: {e}")
    
    async def get_project_pages(self, project_id: int) -> Optional[List[UUID]]:
        """Get cached page IDs for a project"""
        if not self.redis:
            return None
        
        try:
            key = self._get_project_pages_key(project_id)
            page_ids_str = self.redis.get(key)
            if page_ids_str:
                page_ids_list = json.loads(page_ids_str)
                return [UUID(pid) for pid in page_ids_list]
            return None
        except Exception as e:
            logger.warning(f"Project pages cache get error: {e}")
            return None
    
    async def invalidate_project_pages(self, project_id: int) -> None:
        """Invalidate cached project pages"""
        if not self.redis:
            return
        
        try:
            key = self._get_project_pages_key(project_id)
            self.redis.delete(key)
        except Exception as e:
            logger.warning(f"Project pages cache invalidation error: {e}")
    
    async def cache_user_projects(
        self,
        user_id: int,
        project_ids: List[int],
        ttl: Optional[int] = None
    ) -> None:
        """Cache user's accessible project IDs"""
        if not self.redis:
            return
        
        try:
            key = self._get_user_projects_key(user_id)
            cache_ttl = ttl or self.ttl
            self.redis.setex(key, cache_ttl, json.dumps(project_ids))
        except Exception as e:
            logger.warning(f"User projects cache error: {e}")
    
    async def get_user_projects(self, user_id: int) -> Optional[List[int]]:
        """Get cached project IDs for a user"""
        if not self.redis:
            return None
        
        try:
            key = self._get_user_projects_key(user_id)
            project_ids_str = self.redis.get(key)
            if project_ids_str:
                return json.loads(project_ids_str)
            return None
        except Exception as e:
            logger.warning(f"User projects cache get error: {e}")
            return None
    
    async def invalidate_user_projects(self, user_id: int) -> None:
        """Invalidate cached user projects"""
        if not self.redis:
            return
        
        try:
            key = self._get_user_projects_key(user_id)
            self.redis.delete(key)
        except Exception as e:
            logger.warning(f"User projects cache invalidation error: {e}")
    
    async def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        if not self.redis:
            return {"status": "unavailable", "reason": "Redis not connected"}
        
        try:
            info = self.redis.info()
            return {
                "status": "available",
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                )
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage"""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)
    
    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching a pattern"""
        if not self.redis:
            return 0
        
        try:
            keys = self.redis.keys(pattern)
            if keys:
                return self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache pattern clear error: {e}")
            return 0
    
    async def warm_cache_for_project(
        self,
        project_id: int,
        pages_data: List[Tuple[str, int, UUID]]
    ) -> None:
        """Warm cache with page data for a project"""
        if not pages_data:
            return
        
        # Bulk cache page existence
        await self.bulk_set_pages(pages_data)
        
        # Cache project page list
        page_ids = [page_id for _, _, page_id in pages_data]
        await self.cache_project_pages(project_id, page_ids)
        
        logger.info(f"Warmed cache with {len(pages_data)} pages for project {project_id}")


class MockCacheService(PageCacheService):
    """Mock cache service for testing without Redis"""
    
    def __init__(self):
        self.redis = None
        self.ttl = 3600
        self._data = {}
        logger.info("Using mock cache service (Redis not available)")
    
    async def get_page_exists(self, url: str, timestamp: int) -> Optional[UUID]:
        key = self._get_page_key(url, timestamp)
        page_id_str = self._data.get(key)
        return UUID(page_id_str) if page_id_str else None
    
    async def set_page_exists(self, url: str, timestamp: int, page_id: UUID) -> None:
        key = self._get_page_key(url, timestamp)
        self._data[key] = str(page_id)
    
    async def bulk_check_pages(
        self,
        url_timestamp_pairs: List[Tuple[str, int]]
    ) -> Dict[Tuple[str, int], UUID]:
        existing = {}
        for url, timestamp in url_timestamp_pairs:
            page_id = await self.get_page_exists(url, timestamp)
            if page_id:
                existing[(url, timestamp)] = page_id
        return existing