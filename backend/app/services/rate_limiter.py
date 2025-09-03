"""
Rate limiting service for API endpoints and bulk operations
"""
import time
from typing import Dict, Optional, List
import redis.asyncio as redis
from fastapi import HTTPException, status

from app.core.config import settings


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded"""
    def __init__(self, detail: str = "Rate limit exceeded", retry_after: int = None):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers={"Retry-After": str(retry_after)} if retry_after else None
        )


class RateLimiter:
    """Redis-based rate limiter with sliding window"""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[redis.Redis] = None
        
        # In-memory fallback for when Redis is unavailable
        self._memory_store: Dict[str, List[float]] = {}
        self._memory_cleanup_interval = 300  # 5 minutes
        self._last_cleanup = time.time()
    
    async def get_redis(self) -> redis.Redis:
        """Get Redis connection"""
        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                # Test connection
                await self._redis.ping()
            except Exception:
                # Redis unavailable, will fall back to memory store
                self._redis = None
        return self._redis
    
    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        cost: int = 1
    ) -> bool:
        """
        Check if request is within rate limit
        
        Args:
            key: Unique identifier for the rate limit (e.g., user_id, ip_address)
            max_requests: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds
            cost: Cost of this request (default 1)
            
        Returns:
            True if within limits, raises RateLimitExceeded if not
        """
        try:
            redis_client = await self.get_redis()
            if redis_client:
                return await self._check_redis_rate_limit(
                    redis_client, key, max_requests, window_seconds, cost
                )
            else:
                return await self._check_memory_rate_limit(
                    key, max_requests, window_seconds, cost
                )
        except RateLimitExceeded:
            raise
        except Exception as e:
            # If rate limiting fails, log error but allow request
            # This prevents rate limiting from breaking the application
            print(f"Rate limiting error: {str(e)}")
            return True
    
    async def _check_redis_rate_limit(
        self,
        redis_client: redis.Redis,
        key: str,
        max_requests: int,
        window_seconds: int,
        cost: int = 1
    ) -> bool:
        """Redis-based sliding window rate limiting"""
        now = time.time()
        window_start = now - window_seconds
        
        pipe = redis_client.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count current requests
        pipe.zcard(key)
        
        # Execute pipeline
        results = await pipe.execute()
        current_count = results[1]
        
        # Check if adding this request would exceed limit
        if current_count + cost > max_requests:
            # Get oldest entry to calculate retry time
            oldest_entry = await redis_client.zrange(key, 0, 0, withscores=True)
            if oldest_entry:
                retry_after = int(oldest_entry[0][1] + window_seconds - now) + 1
            else:
                retry_after = window_seconds
            
            raise RateLimitExceeded(
                detail=f"Rate limit exceeded. {current_count}/{max_requests} requests in {window_seconds}s window",
                retry_after=max(retry_after, 1)
            )
        
        # Add current request(s)
        for _ in range(cost):
            await redis_client.zadd(key, {str(now + (_ * 0.001)): now})
        
        # Set expiration
        await redis_client.expire(key, window_seconds + 60)
        
        return True
    
    async def _check_memory_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
        cost: int = 1
    ) -> bool:
        """In-memory sliding window rate limiting (fallback)"""
        now = time.time()
        window_start = now - window_seconds
        
        # Cleanup old entries periodically
        if now - self._last_cleanup > self._memory_cleanup_interval:
            await self._cleanup_memory_store()
        
        # Get or create request list for this key
        if key not in self._memory_store:
            self._memory_store[key] = []
        
        requests = self._memory_store[key]
        
        # Remove old entries
        self._memory_store[key] = [req_time for req_time in requests if req_time > window_start]
        requests = self._memory_store[key]
        
        # Check limit
        if len(requests) + cost > max_requests:
            oldest_time = min(requests) if requests else now
            retry_after = int(oldest_time + window_seconds - now) + 1
            
            raise RateLimitExceeded(
                detail=f"Rate limit exceeded. {len(requests)}/{max_requests} requests in {window_seconds}s window",
                retry_after=max(retry_after, 1)
            )
        
        # Add current request(s)
        for i in range(cost):
            self._memory_store[key].append(now + (i * 0.001))
        
        return True
    
    async def _cleanup_memory_store(self):
        """Clean up old entries from memory store"""
        now = time.time()
        keys_to_remove = []
        
        for key, requests in self._memory_store.items():
            # Remove requests older than 1 hour
            cleaned_requests = [req_time for req_time in requests if now - req_time < 3600]
            if cleaned_requests:
                self._memory_store[key] = cleaned_requests
            else:
                keys_to_remove.append(key)
        
        # Remove empty keys
        for key in keys_to_remove:
            del self._memory_store[key]
        
        self._last_cleanup = now
    
    async def get_rate_limit_info(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> Dict[str, int]:
        """Get current rate limit information"""
        try:
            redis_client = await self.get_redis()
            now = time.time()
            window_start = now - window_seconds
            
            if redis_client:
                current_count = await redis_client.zcount(key, window_start, now)
            else:
                if key in self._memory_store:
                    requests = [req for req in self._memory_store[key] if req > window_start]
                    current_count = len(requests)
                else:
                    current_count = 0
            
            remaining = max(0, max_requests - current_count)
            reset_time = int(now + window_seconds)
            
            return {
                "limit": max_requests,
                "remaining": remaining,
                "reset_time": reset_time,
                "window_seconds": window_seconds
            }
            
        except Exception:
            # Return default values if unable to get info
            return {
                "limit": max_requests,
                "remaining": max_requests,
                "reset_time": int(time.time() + window_seconds),
                "window_seconds": window_seconds
            }
    
    async def reset_rate_limit(self, key: str) -> bool:
        """Reset rate limit for a key (admin function)"""
        try:
            redis_client = await self.get_redis()
            if redis_client:
                await redis_client.delete(key)
            
            if key in self._memory_store:
                del self._memory_store[key]
            
            return True
            
        except Exception:
            return False
    
    async def bulk_reset_rate_limits(self, pattern: str) -> int:
        """Reset all rate limits matching pattern (admin function)"""
        try:
            redis_client = await self.get_redis()
            if redis_client:
                keys = await redis_client.keys(pattern)
                if keys:
                    await redis_client.delete(*keys)
                    count = len(keys)
                else:
                    count = 0
            else:
                count = 0
            
            # Also clean memory store
            memory_keys_to_remove = [
                key for key in self._memory_store.keys()
                if self._pattern_matches(key, pattern)
            ]
            for key in memory_keys_to_remove:
                del self._memory_store[key]
            
            count += len(memory_keys_to_remove)
            return count
            
        except Exception:
            return 0
    
    def _pattern_matches(self, key: str, pattern: str) -> bool:
        """Simple pattern matching for memory store cleanup"""
        if '*' not in pattern:
            return key == pattern
        
        # Simple wildcard matching
        parts = pattern.split('*')
        if len(parts) == 2:
            prefix, suffix = parts
            return key.startswith(prefix) and key.endswith(suffix)
        
        return False


# Rate limit configurations for different operations
class RateLimitConfig:
    """Configuration for different rate limits"""
    
    # API endpoints
    API_DEFAULT = {"max_requests": 100, "window_seconds": 60}  # 100 req/min
    API_AUTH = {"max_requests": 10, "window_seconds": 60}      # 10 req/min for auth
    API_SEARCH = {"max_requests": 50, "window_seconds": 60}    # 50 req/min for search
    
    # Bulk operations
    BULK_OPERATIONS = {"max_requests": 5, "window_seconds": 3600}  # 5 bulk ops/hour
    BULK_DELETE = {"max_requests": 2, "window_seconds": 3600}      # 2 bulk deletes/hour
    
    # Data export
    EXPORT_OPERATIONS = {"max_requests": 3, "window_seconds": 3600}  # 3 exports/hour
    
    # Email operations
    BULK_EMAIL = {"max_requests": 10, "window_seconds": 3600}  # 10 bulk emails/hour
    
    # Admin operations
    ADMIN_OPERATIONS = {"max_requests": 20, "window_seconds": 300}  # 20 ops/5min


async def rate_limit_dependency(
    request,
    rate_limiter: RateLimiter,
    config: Dict[str, int],
    key_prefix: str = ""
):
    """FastAPI dependency for rate limiting"""
    # Get client IP
    client_ip = getattr(request.client, 'host', '127.0.0.1')
    
    # Create rate limit key
    key = f"{key_prefix}:{client_ip}" if key_prefix else client_ip
    
    await rate_limiter.check_rate_limit(**config, key=key)
    
    return True