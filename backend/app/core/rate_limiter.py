"""
Rate Limiting Middleware for Public Meilisearch Endpoints

This module provides Redis-based rate limiting for public search endpoints
to prevent abuse and ensure fair usage of the search infrastructure.
"""
import time
import json
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from .config import settings

logger = logging.getLogger(__name__)


class RateLimitType(str, Enum):
    """Rate limit types for different endpoints"""
    PUBLIC_SEARCH = "public_search"
    PUBLIC_KEY_ACCESS = "public_key_access"
    TENANT_TOKEN = "tenant_token"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting"""
    requests_per_window: int
    window_seconds: int
    burst_limit: Optional[int] = None
    block_duration_seconds: int = 300  # 5 minutes default block


class RateLimitResult:
    """Result of a rate limit check"""
    
    def __init__(
        self,
        allowed: bool,
        limit: int,
        remaining: int,
        reset_time: int,
        retry_after: Optional[int] = None
    ):
        self.allowed = allowed
        self.limit = limit
        self.remaining = remaining
        self.reset_time = reset_time
        self.retry_after = retry_after


class RedisRateLimiter:
    """Redis-based sliding window rate limiter"""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[redis.Redis] = None
        
        # Default rate limit configurations
        self.rate_configs = {
            RateLimitType.PUBLIC_SEARCH: RateLimitConfig(
                requests_per_window=100,  # 100 requests per hour
                window_seconds=3600,
                burst_limit=10,  # Allow 10 rapid requests
                block_duration_seconds=300
            ),
            RateLimitType.PUBLIC_KEY_ACCESS: RateLimitConfig(
                requests_per_window=50,  # 50 key requests per hour
                window_seconds=3600,
                burst_limit=5,
                block_duration_seconds=600  # 10 minutes
            ),
            RateLimitType.TENANT_TOKEN: RateLimitConfig(
                requests_per_window=200,  # 200 requests per hour for shared access
                window_seconds=3600,
                burst_limit=20,
                block_duration_seconds=300
            )
        }
    
    async def get_redis(self) -> redis.Redis:
        """Get or create Redis connection"""
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
        return self._redis
    
    async def close(self):
        """Close Redis connection"""
        if self._redis:
            await self._redis.close()
    
    def _get_key(
        self, 
        identifier: str, 
        rate_type: RateLimitType, 
        window_start: int
    ) -> str:
        """Generate Redis key for rate limiting"""
        return f"rate_limit:{rate_type.value}:{identifier}:{window_start}"
    
    def _get_block_key(self, identifier: str, rate_type: RateLimitType) -> str:
        """Generate Redis key for blocking"""
        return f"rate_limit_block:{rate_type.value}:{identifier}"
    
    async def check_rate_limit(
        self,
        identifier: str,
        rate_type: RateLimitType,
        config_override: Optional[RateLimitConfig] = None
    ) -> RateLimitResult:
        """
        Check if request is within rate limits using sliding window
        
        Args:
            identifier: Unique identifier (IP, user ID, etc.)
            rate_type: Type of rate limit to apply
            config_override: Optional custom rate limit configuration
            
        Returns:
            RateLimitResult with allow/deny decision and metadata
        """
        config = config_override or self.rate_configs.get(rate_type)
        if not config:
            # No rate limit configured, allow request
            return RateLimitResult(
                allowed=True,
                limit=0,
                remaining=0,
                reset_time=int(time.time())
            )
        
        redis_client = await self.get_redis()
        current_time = int(time.time())
        window_start = current_time // config.window_seconds * config.window_seconds
        
        # Check if identifier is currently blocked
        block_key = self._get_block_key(identifier, rate_type)
        block_info = await redis_client.get(block_key)
        
        if block_info:
            block_data = json.loads(block_info)
            block_until = block_data.get('blocked_until', 0)
            
            if current_time < block_until:
                retry_after = block_until - current_time
                logger.warning(f"Rate limit block active for {identifier}: {rate_type.value}")
                
                return RateLimitResult(
                    allowed=False,
                    limit=config.requests_per_window,
                    remaining=0,
                    reset_time=window_start + config.window_seconds,
                    retry_after=retry_after
                )
            else:
                # Block expired, remove it
                await redis_client.delete(block_key)
        
        # Get current request count for this window
        rate_key = self._get_key(identifier, rate_type, window_start)
        
        async with redis_client.pipeline() as pipe:
            # Use pipeline for atomic operations
            await pipe.multi()
            await pipe.incr(rate_key)
            await pipe.expire(rate_key, config.window_seconds)
            results = await pipe.execute()
            
            current_count = results[0]
        
        # Check burst limit first (short-term limit)
        if config.burst_limit and current_count > config.burst_limit:
            # Check if we need to block for excessive requests
            if current_count > config.requests_per_window * 1.5:  # 50% over limit
                await self._block_identifier(
                    identifier, 
                    rate_type, 
                    config.block_duration_seconds,
                    f"Excessive requests: {current_count} in window"
                )
                
                return RateLimitResult(
                    allowed=False,
                    limit=config.requests_per_window,
                    remaining=0,
                    reset_time=window_start + config.window_seconds,
                    retry_after=config.block_duration_seconds
                )
        
        # Check main rate limit
        if current_count > config.requests_per_window:
            logger.warning(
                f"Rate limit exceeded for {identifier}: {current_count}/{config.requests_per_window} "
                f"({rate_type.value})"
            )
            
            return RateLimitResult(
                allowed=False,
                limit=config.requests_per_window,
                remaining=0,
                reset_time=window_start + config.window_seconds,
                retry_after=window_start + config.window_seconds - current_time
            )
        
        remaining = max(0, config.requests_per_window - current_count)
        
        logger.debug(
            f"Rate limit check passed for {identifier}: {current_count}/{config.requests_per_window} "
            f"({rate_type.value})"
        )
        
        return RateLimitResult(
            allowed=True,
            limit=config.requests_per_window,
            remaining=remaining,
            reset_time=window_start + config.window_seconds
        )
    
    async def _block_identifier(
        self,
        identifier: str,
        rate_type: RateLimitType,
        duration_seconds: int,
        reason: str
    ):
        """Block an identifier for a specified duration"""
        redis_client = await self.get_redis()
        block_key = self._get_block_key(identifier, rate_type)
        current_time = int(time.time())
        
        block_data = {
            'blocked_at': current_time,
            'blocked_until': current_time + duration_seconds,
            'reason': reason,
            'rate_type': rate_type.value
        }
        
        await redis_client.setex(
            block_key,
            duration_seconds,
            json.dumps(block_data)
        )
        
        logger.warning(
            f"Blocked identifier {identifier} for {duration_seconds}s: {reason}"
        )
    
    async def get_usage_stats(
        self, 
        identifier: str, 
        rate_type: RateLimitType
    ) -> Dict[str, Any]:
        """Get usage statistics for an identifier"""
        redis_client = await self.get_redis()
        current_time = int(time.time())
        config = self.rate_configs.get(rate_type)
        
        if not config:
            return {}
        
        window_start = current_time // config.window_seconds * config.window_seconds
        rate_key = self._get_key(identifier, rate_type, window_start)
        
        current_count = await redis_client.get(rate_key)
        current_count = int(current_count) if current_count else 0
        
        # Check for active blocks
        block_key = self._get_block_key(identifier, rate_type)
        block_info = await redis_client.get(block_key)
        
        block_data = None
        if block_info:
            block_data = json.loads(block_info)
        
        return {
            'identifier': identifier,
            'rate_type': rate_type.value,
            'current_window_requests': current_count,
            'limit': config.requests_per_window,
            'remaining': max(0, config.requests_per_window - current_count),
            'window_start': window_start,
            'window_end': window_start + config.window_seconds,
            'blocked': bool(block_data),
            'block_info': block_data
        }


# Global rate limiter instance
rate_limiter = RedisRateLimiter()


def get_client_identifier(request: Request) -> str:
    """
    Extract client identifier from request for rate limiting
    
    Priority order:
    1. X-Forwarded-For header (for proxied requests)
    2. X-Real-IP header
    3. Direct client IP
    4. User-Agent as fallback
    """
    # Check forwarded headers (for load balancers/proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain
        return forwarded_for.split(",")[0].strip()
    
    # Check real IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Use client IP if available
    if hasattr(request, "client") and request.client.host:
        return request.client.host
    
    # Fallback to User-Agent (less reliable but better than nothing)
    user_agent = request.headers.get("User-Agent", "unknown")
    return f"ua:{hash(user_agent) % 1000000}"


async def apply_rate_limit(
    request: Request,
    rate_type: RateLimitType,
    config_override: Optional[RateLimitConfig] = None
) -> RateLimitResult:
    """
    Apply rate limiting to a request
    
    Args:
        request: FastAPI request object
        rate_type: Type of rate limit to apply
        config_override: Optional custom rate limit configuration
        
    Returns:
        RateLimitResult
        
    Raises:
        HTTPException: If rate limit is exceeded
    """
    identifier = get_client_identifier(request)
    
    try:
        result = await rate_limiter.check_rate_limit(
            identifier=identifier,
            rate_type=rate_type,
            config_override=config_override
        )
        
        if not result.allowed:
            headers = {
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(result.reset_time)
            }
            
            if result.retry_after:
                headers["Retry-After"] = str(result.retry_after)
            
            detail = {
                "error": "Rate limit exceeded",
                "limit": result.limit,
                "remaining": result.remaining,
                "reset_time": result.reset_time,
                "retry_after": result.retry_after
            }
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers=headers
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rate limiting error for {identifier}: {e}")
        # On Redis errors, allow the request to proceed
        return RateLimitResult(
            allowed=True,
            limit=0,
            remaining=0,
            reset_time=int(time.time())
        )


# Dependency for FastAPI routes
async def rate_limit_public_search(request: Request) -> RateLimitResult:
    """Rate limiting dependency for public search endpoints"""
    return await apply_rate_limit(request, RateLimitType.PUBLIC_SEARCH)


async def rate_limit_public_key_access(request: Request) -> RateLimitResult:
    """Rate limiting dependency for public key access endpoints"""
    return await apply_rate_limit(request, RateLimitType.PUBLIC_KEY_ACCESS)


async def rate_limit_tenant_token(request: Request) -> RateLimitResult:
    """Rate limiting dependency for tenant token endpoints"""
    return await apply_rate_limit(request, RateLimitType.TENANT_TOKEN)