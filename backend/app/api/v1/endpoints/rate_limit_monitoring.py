"""
Rate Limiting Monitoring and Analytics Endpoints

Provides endpoints for monitoring rate limit usage, abuse patterns,
and analytics for the Meilisearch multi-tenancy system.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....models.user import User
from ....api.deps import get_current_active_user
from ....core.rate_limiter import rate_limiter, RateLimitType, get_client_identifier
from ....core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/rate-limits/stats", response_model=Dict[str, Any])
async def get_rate_limit_stats(
    identifier: Optional[str] = Query(None, description="Specific identifier to check"),
    rate_type: Optional[str] = Query(None, description="Rate limit type to check"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get rate limiting statistics for monitoring
    
    Only accessible by admin users for monitoring purposes.
    """
    try:
        # Check if user is admin (simplified check - in production use proper RBAC)
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        stats = {}
        
        if identifier and rate_type:
            # Get stats for specific identifier and type
            try:
                rate_type_enum = RateLimitType(rate_type)
                usage_stats = await rate_limiter.get_usage_stats(identifier, rate_type_enum)
                stats[f"{identifier}_{rate_type}"] = usage_stats
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid rate type: {rate_type}"
                )
        else:
            # Get general rate limiting health status
            redis_client = await rate_limiter.get_redis()
            
            try:
                # Check Redis connectivity
                await redis_client.ping()
                redis_status = "healthy"
            except Exception as e:
                redis_status = f"error: {str(e)}"
            
            stats = {
                "redis_status": redis_status,
                "rate_limit_types": [t.value for t in RateLimitType],
                "available_configs": {
                    rate_type.value: {
                        "requests_per_window": config.requests_per_window,
                        "window_seconds": config.window_seconds,
                        "burst_limit": config.burst_limit,
                        "block_duration_seconds": config.block_duration_seconds
                    }
                    for rate_type, config in rate_limiter.rate_configs.items()
                }
            }
        
        return {
            "timestamp": datetime.utcnow(),
            "stats": stats
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rate limit stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve rate limit statistics"
        )


@router.get("/rate-limits/health", response_model=Dict[str, Any])
async def rate_limit_health_check():
    """
    Health check for rate limiting system
    
    Public endpoint for monitoring system health.
    """
    try:
        redis_client = await rate_limiter.get_redis()
        
        # Test Redis connectivity
        start_time = datetime.utcnow()
        await redis_client.ping()
        response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return {
            "status": "healthy",
            "redis_connection": "active",
            "response_time_ms": response_time,
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Rate limit health check failed: {e}")
        return {
            "status": "unhealthy",
            "redis_connection": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow()
        }


@router.post("/rate-limits/test", response_model=Dict[str, Any])
async def test_rate_limit(
    identifier: str = Query(..., description="Test identifier"),
    rate_type: str = Query(..., description="Rate limit type to test"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Test rate limiting for a specific identifier and type
    
    Admin only endpoint for testing rate limit configurations.
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        try:
            rate_type_enum = RateLimitType(rate_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid rate type: {rate_type}"
            )
        
        # Check rate limit
        result = await rate_limiter.check_rate_limit(identifier, rate_type_enum)
        
        # Get usage stats
        usage_stats = await rate_limiter.get_usage_stats(identifier, rate_type_enum)
        
        return {
            "test_result": {
                "allowed": result.allowed,
                "limit": result.limit,
                "remaining": result.remaining,
                "reset_time": result.reset_time,
                "retry_after": result.retry_after
            },
            "usage_stats": usage_stats,
            "timestamp": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rate limit test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rate limit test failed"
        )


@router.delete("/rate-limits/clear", response_model=Dict[str, Any])
async def clear_rate_limits(
    identifier: Optional[str] = Query(None, description="Specific identifier to clear"),
    rate_type: Optional[str] = Query(None, description="Rate limit type to clear"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Clear rate limits for testing or emergency situations
    
    Admin only endpoint for clearing rate limit counters.
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        redis_client = await rate_limiter.get_redis()
        cleared_keys = []
        
        if identifier and rate_type:
            # Clear specific identifier and type
            try:
                rate_type_enum = RateLimitType(rate_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid rate type: {rate_type}"
                )
            
            # Clear rate limit keys
            current_time = int(datetime.utcnow().timestamp())
            config = rate_limiter.rate_configs.get(rate_type_enum)
            
            if config:
                window_start = current_time // config.window_seconds * config.window_seconds
                rate_key = rate_limiter._get_key(identifier, rate_type_enum, window_start)
                block_key = rate_limiter._get_block_key(identifier, rate_type_enum)
                
                deleted_rate = await redis_client.delete(rate_key)
                deleted_block = await redis_client.delete(block_key)
                
                if deleted_rate or deleted_block:
                    cleared_keys.extend([rate_key, block_key])
        
        elif identifier:
            # Clear all rate limits for identifier
            for rate_type_enum in RateLimitType:
                current_time = int(datetime.utcnow().timestamp())
                config = rate_limiter.rate_configs.get(rate_type_enum)
                
                if config:
                    window_start = current_time // config.window_seconds * config.window_seconds
                    rate_key = rate_limiter._get_key(identifier, rate_type_enum, window_start)
                    block_key = rate_limiter._get_block_key(identifier, rate_type_enum)
                    
                    deleted_rate = await redis_client.delete(rate_key)
                    deleted_block = await redis_client.delete(block_key)
                    
                    if deleted_rate or deleted_block:
                        cleared_keys.extend([rate_key, block_key])
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must specify identifier to clear"
            )
        
        logger.warning(
            f"Rate limits cleared by admin {current_user.id}: "
            f"identifier={identifier}, rate_type={rate_type}, "
            f"cleared_keys={len(cleared_keys)}"
        )
        
        return {
            "message": "Rate limits cleared successfully",
            "cleared_keys_count": len(cleared_keys),
            "cleared_keys": cleared_keys,
            "timestamp": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear rate limits: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear rate limits"
        )


@router.get("/rate-limits/blocked", response_model=Dict[str, Any])
async def get_blocked_identifiers(
    rate_type: Optional[str] = Query(None, description="Filter by rate limit type"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of currently blocked identifiers
    
    Admin only endpoint for monitoring blocked users/IPs.
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        redis_client = await rate_limiter.get_redis()
        blocked_identifiers = []
        
        # Search for block keys
        rate_types_to_check = []
        if rate_type:
            try:
                rate_types_to_check = [RateLimitType(rate_type)]
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid rate type: {rate_type}"
                )
        else:
            rate_types_to_check = list(RateLimitType)
        
        for rate_type_enum in rate_types_to_check:
            pattern = f"rate_limit_block:{rate_type_enum.value}:*"
            
            # Scan for matching keys
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
                
                for key in keys:
                    try:
                        block_info = await redis_client.get(key)
                        if block_info:
                            import json
                            block_data = json.loads(block_info)
                            
                            # Extract identifier from key
                            key_parts = key.split(':')
                            if len(key_parts) >= 4:
                                identifier = ':'.join(key_parts[3:])
                                
                                blocked_identifiers.append({
                                    "identifier": identifier,
                                    "rate_type": rate_type_enum.value,
                                    "blocked_at": block_data.get("blocked_at"),
                                    "blocked_until": block_data.get("blocked_until"),
                                    "reason": block_data.get("reason"),
                                    "remaining_seconds": max(0, block_data.get("blocked_until", 0) - int(datetime.utcnow().timestamp()))
                                })
                    except Exception as e:
                        logger.error(f"Error processing block key {key}: {e}")
                
                if cursor == 0:
                    break
        
        return {
            "blocked_identifiers": blocked_identifiers,
            "total_blocked": len(blocked_identifiers),
            "timestamp": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get blocked identifiers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve blocked identifiers"
        )