"""
Redis caching decorator system for performance optimization
"""
import json
import hashlib
from functools import wraps
from typing import Callable, Optional, Union
import pickle
import logging

import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis client instance
_redis_client: Optional[redis.Redis] = None

async def get_redis_client() -> redis.Redis:
    """Get Redis client instance"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=6379,
            db=2,  # Use database 2 for caching (separate from Celery)
            decode_responses=False,  # We'll handle encoding manually for complex objects
            socket_keepalive=True,
            socket_keepalive_options={},
            retry_on_timeout=True,
            health_check_interval=30
        )
    return _redis_client


def cache_key_generator(*args, **kwargs) -> str:
    """Generate a unique cache key from function arguments"""
    # Create a stable representation of arguments
    key_data = {
        "args": args,
        "kwargs": sorted(kwargs.items())  # Sort for consistency
    }
    
    # Serialize and hash the key data
    key_str = json.dumps(key_data, sort_keys=True, default=str)
    return hashlib.md5(key_str.encode()).hexdigest()


def cache_result(
    ttl: int = 300,
    prefix: str = "",
    serialize_method: str = "json",
    invalidate_on_error: bool = True
):
    """
    Caching decorator for async functions
    
    Args:
        ttl: Time-to-live in seconds (default: 5 minutes)
        prefix: Cache key prefix for namespace organization
        serialize_method: 'json' or 'pickle' for serialization
        invalidate_on_error: Whether to invalidate cache on function errors
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            redis_client = await get_redis_client()
            
            # Generate cache key
            func_key = f"{func.__module__}.{func.__name__}"
            arg_key = cache_key_generator(*args, **kwargs)
            cache_key = f"cache:{prefix}:{func_key}:{arg_key}" if prefix else f"cache:{func_key}:{arg_key}"
            
            try:
                # Try to get from cache first
                cached_data = await redis_client.get(cache_key)
                if cached_data is not None:
                    logger.debug(f"Cache HIT for {cache_key}")
                    if serialize_method == "pickle":
                        return pickle.loads(cached_data)
                    else:
                        return json.loads(cached_data.decode())
                
                logger.debug(f"Cache MISS for {cache_key}")
                
                # Execute the function
                result = await func(*args, **kwargs)
                
                # Serialize and cache the result
                try:
                    if serialize_method == "pickle":
                        serialized_data = pickle.dumps(result)
                    else:
                        serialized_data = json.dumps(result, default=str).encode()
                    
                    await redis_client.setex(cache_key, ttl, serialized_data)
                    logger.debug(f"Cached result for {cache_key} (TTL: {ttl}s)")
                    
                except (TypeError, ValueError) as e:
                    logger.warning(f"Failed to serialize result for caching: {e}")
                
                return result
                
            except Exception as e:
                logger.error(f"Cache operation failed for {cache_key}: {e}")
                
                # If caching fails, still execute the function
                result = await func(*args, **kwargs)
                
                # Optionally invalidate cache on errors
                if invalidate_on_error:
                    try:
                        await redis_client.delete(cache_key)
                    except Exception:
                        pass  # Ignore cache invalidation errors
                
                return result
                
        return wrapper
    return decorator


def cache_invalidate(patterns: Union[str, list]):
    """
    Decorator to invalidate cache entries matching patterns after function execution
    
    Args:
        patterns: Single pattern or list of patterns to invalidate
    """
    if isinstance(patterns, str):
        patterns = [patterns]
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # Invalidate cache entries after successful execution
            redis_client = await get_redis_client()
            
            for pattern in patterns:
                try:
                    # Use SCAN to find matching keys (more efficient than KEYS)
                    keys_to_delete = []
                    async for key in redis_client.scan_iter(match=f"cache:{pattern}*"):
                        keys_to_delete.append(key)
                    
                    if keys_to_delete:
                        await redis_client.delete(*keys_to_delete)
                        logger.debug(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
                        
                except Exception as e:
                    logger.warning(f"Failed to invalidate cache pattern '{pattern}': {e}")
            
            return result
        return wrapper
    return decorator


class CacheManager:
    """Utility class for manual cache management"""
    
    @staticmethod
    async def clear_all():
        """Clear all cache entries"""
        redis_client = await get_redis_client()
        try:
            keys_to_delete = []
            async for key in redis_client.scan_iter(match="cache:*"):
                keys_to_delete.append(key)
            
            if keys_to_delete:
                await redis_client.delete(*keys_to_delete)
                logger.info(f"Cleared {len(keys_to_delete)} cache entries")
                return len(keys_to_delete)
            return 0
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return 0
    
    @staticmethod
    async def clear_pattern(pattern: str):
        """Clear cache entries matching a pattern"""
        redis_client = await get_redis_client()
        try:
            keys_to_delete = []
            async for key in redis_client.scan_iter(match=f"cache:{pattern}*"):
                keys_to_delete.append(key)
            
            if keys_to_delete:
                await redis_client.delete(*keys_to_delete)
                logger.info(f"Cleared {len(keys_to_delete)} cache entries matching '{pattern}'")
                return len(keys_to_delete)
            return 0
        except Exception as e:
            logger.error(f"Failed to clear cache pattern '{pattern}': {e}")
            return 0
    
    @staticmethod
    async def get_cache_stats():
        """Get cache statistics"""
        redis_client = await get_redis_client()
        try:
            total_keys = 0
            total_memory = 0
            
            async for key in redis_client.scan_iter(match="cache:*"):
                total_keys += 1
                try:
                    memory_usage = await redis_client.memory_usage(key)
                    if memory_usage:
                        total_memory += memory_usage
                except Exception:
                    pass  # Ignore individual key errors
            
            info = await redis_client.info()
            
            return {
                "cache_keys": total_keys,
                "cache_memory_bytes": total_memory,
                "cache_memory_mb": round(total_memory / (1024 * 1024), 2),
                "redis_memory_used": info.get("used_memory_human", "unknown"),
                "redis_connected_clients": info.get("connected_clients", 0),
                "redis_ops_per_sec": info.get("instantaneous_ops_per_sec", 0)
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}


# Convenient cache decorators with pre-configured settings
cache_short = cache_result(ttl=60, prefix="short")          # 1 minute
cache_medium = cache_result(ttl=300, prefix="medium")       # 5 minutes  
cache_long = cache_result(ttl=1800, prefix="long")          # 30 minutes
cache_project_stats = cache_result(ttl=600, prefix="project_stats")  # 10 minutes