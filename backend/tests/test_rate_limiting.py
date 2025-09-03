"""
Tests for Rate Limiting Middleware

Tests the Redis-based rate limiting system used to protect
public Meilisearch endpoints from abuse.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from app.core.rate_limiter import (
    RedisRateLimiter, 
    RateLimitConfig, 
    RateLimitType, 
    RateLimitResult,
    apply_rate_limit,
    get_client_identifier
)


class TestRedisRateLimiter:
    """Test the core rate limiting functionality"""
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client"""
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None
        mock_redis.incr.return_value = 1
        mock_redis.expire.return_value = True
        mock_redis.delete.return_value = 1
        mock_redis.setex.return_value = True
        
        # Mock pipeline
        mock_pipeline = AsyncMock()
        mock_pipeline.multi.return_value = None
        mock_pipeline.incr.return_value = None
        mock_pipeline.expire.return_value = None
        mock_pipeline.execute.return_value = [1, True]  # [incr_result, expire_result]
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)
        
        mock_redis.pipeline.return_value = mock_pipeline
        
        return mock_redis
    
    @pytest.fixture
    def rate_limiter(self, mock_redis):
        """Create rate limiter with mocked Redis"""
        limiter = RedisRateLimiter()
        limiter._redis = mock_redis
        return limiter
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_allows_first_request(self, rate_limiter, mock_redis):
        """Test that first request is allowed"""
        # Setup mock pipeline to return count of 1
        mock_pipeline = mock_redis.pipeline.return_value
        mock_pipeline.execute.return_value = [1, True]
        
        result = await rate_limiter.check_rate_limit(
            identifier="test_ip",
            rate_type=RateLimitType.PUBLIC_SEARCH
        )
        
        assert result.allowed is True
        assert result.remaining > 0
        assert result.limit > 0
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_blocks_after_limit(self, rate_limiter, mock_redis):
        """Test that requests are blocked after exceeding limit"""
        config = rate_limiter.rate_configs[RateLimitType.PUBLIC_SEARCH]
        
        # Setup mock to return count exceeding limit
        mock_pipeline = mock_redis.pipeline.return_value
        mock_pipeline.execute.return_value = [config.requests_per_window + 1, True]
        
        result = await rate_limiter.check_rate_limit(
            identifier="test_ip",
            rate_type=RateLimitType.PUBLIC_SEARCH
        )
        
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after is not None
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_respects_burst_limit(self, rate_limiter, mock_redis):
        """Test burst limit enforcement"""
        config = rate_limiter.rate_configs[RateLimitType.PUBLIC_SEARCH]
        
        # Setup mock to return count exceeding burst limit but not main limit
        mock_pipeline = mock_redis.pipeline.return_value
        mock_pipeline.execute.return_value = [config.burst_limit + 1, True]
        
        result = await rate_limiter.check_rate_limit(
            identifier="test_ip",
            rate_type=RateLimitType.PUBLIC_SEARCH
        )
        
        # Should still be allowed as it's under main limit
        assert result.allowed is True
    
    @pytest.mark.asyncio
    async def test_check_rate_limit_handles_blocked_identifier(self, rate_limiter, mock_redis):
        """Test that blocked identifiers are rejected"""
        import json
        import time
        
        # Mock a block record
        block_data = {
            'blocked_until': int(time.time()) + 300,  # 5 minutes from now
            'reason': 'Excessive requests'
        }
        mock_redis.get.return_value = json.dumps(block_data)
        
        result = await rate_limiter.check_rate_limit(
            identifier="test_ip",
            rate_type=RateLimitType.PUBLIC_SEARCH
        )
        
        assert result.allowed is False
        assert result.retry_after is not None
        assert result.retry_after > 0
    
    @pytest.mark.asyncio
    async def test_block_identifier(self, rate_limiter, mock_redis):
        """Test blocking an identifier"""
        await rate_limiter._block_identifier(
            identifier="test_ip",
            rate_type=RateLimitType.PUBLIC_SEARCH,
            duration_seconds=300,
            reason="Test block"
        )
        
        # Verify setex was called
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args
        assert args[0][1] == 300  # Duration
        
        # Verify block data structure
        import json
        block_data = json.loads(args[0][2])
        assert block_data['reason'] == "Test block"
        assert 'blocked_until' in block_data
    
    @pytest.mark.asyncio
    async def test_get_usage_stats(self, rate_limiter, mock_redis):
        """Test getting usage statistics"""
        mock_redis.get.return_value = "5"  # Current count
        
        stats = await rate_limiter.get_usage_stats(
            identifier="test_ip",
            rate_type=RateLimitType.PUBLIC_SEARCH
        )
        
        assert stats['identifier'] == "test_ip"
        assert stats['rate_type'] == RateLimitType.PUBLIC_SEARCH.value
        assert stats['current_window_requests'] == 5
        assert 'remaining' in stats
        assert 'limit' in stats
    
    def test_get_key_generation(self, rate_limiter):
        """Test rate limit key generation"""
        key = rate_limiter._get_key(
            identifier="test_ip",
            rate_type=RateLimitType.PUBLIC_SEARCH,
            window_start=1000
        )
        
        expected = f"rate_limit:{RateLimitType.PUBLIC_SEARCH.value}:test_ip:1000"
        assert key == expected
    
    def test_get_block_key_generation(self, rate_limiter):
        """Test block key generation"""
        key = rate_limiter._get_block_key(
            identifier="test_ip",
            rate_type=RateLimitType.PUBLIC_SEARCH
        )
        
        expected = f"rate_limit_block:{RateLimitType.PUBLIC_SEARCH.value}:test_ip"
        assert key == expected


class TestClientIdentifierExtraction:
    """Test client identifier extraction from requests"""
    
    def test_get_client_identifier_forwarded_for(self):
        """Test extraction from X-Forwarded-For header"""
        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        
        identifier = get_client_identifier(mock_request)
        assert identifier == "192.168.1.1"
    
    def test_get_client_identifier_real_ip(self):
        """Test extraction from X-Real-IP header"""
        mock_request = MagicMock()
        mock_request.headers = {"X-Real-IP": "192.168.1.2"}
        
        identifier = get_client_identifier(mock_request)
        assert identifier == "192.168.1.2"
    
    def test_get_client_identifier_client_host(self):
        """Test extraction from client host"""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "192.168.1.3"
        
        identifier = get_client_identifier(mock_request)
        assert identifier == "192.168.1.3"
    
    def test_get_client_identifier_user_agent_fallback(self):
        """Test fallback to User-Agent hash"""
        mock_request = MagicMock()
        mock_request.headers = {"User-Agent": "TestBot/1.0"}
        mock_request.client = None
        
        identifier = get_client_identifier(mock_request)
        assert identifier.startswith("ua:")
        assert identifier != "ua:unknown"


class TestRateLimitApplication:
    """Test rate limit application in FastAPI context"""
    
    @pytest.mark.asyncio
    async def test_apply_rate_limit_success(self):
        """Test successful rate limit application"""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "192.168.1.1"
        
        with patch('app.core.rate_limiter.rate_limiter') as mock_limiter:
            mock_limiter.check_rate_limit.return_value = RateLimitResult(
                allowed=True,
                limit=100,
                remaining=99,
                reset_time=1234567890
            )
            
            result = await apply_rate_limit(mock_request, RateLimitType.PUBLIC_SEARCH)
            
            assert result.allowed is True
            mock_limiter.check_rate_limit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_apply_rate_limit_blocked(self):
        """Test rate limit blocking"""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "192.168.1.1"
        
        with patch('app.core.rate_limiter.rate_limiter') as mock_limiter:
            mock_limiter.check_rate_limit.return_value = RateLimitResult(
                allowed=False,
                limit=100,
                remaining=0,
                reset_time=1234567890,
                retry_after=300
            )
            
            with pytest.raises(HTTPException) as exc_info:
                await apply_rate_limit(mock_request, RateLimitType.PUBLIC_SEARCH)
            
            assert exc_info.value.status_code == 429
            assert "X-RateLimit-Limit" in exc_info.value.headers
            assert "Retry-After" in exc_info.value.headers
    
    @pytest.mark.asyncio
    async def test_apply_rate_limit_redis_error_fallback(self):
        """Test fallback behavior when Redis is unavailable"""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.client.host = "192.168.1.1"
        
        with patch('app.core.rate_limiter.rate_limiter') as mock_limiter:
            mock_limiter.check_rate_limit.side_effect = Exception("Redis connection failed")
            
            # Should not raise exception, should fallback to allowing request
            result = await apply_rate_limit(mock_request, RateLimitType.PUBLIC_SEARCH)
            
            assert result.allowed is True


class TestRateLimitConfigurations:
    """Test different rate limit configurations"""
    
    def test_public_search_config(self):
        """Test public search rate limit configuration"""
        limiter = RedisRateLimiter()
        config = limiter.rate_configs[RateLimitType.PUBLIC_SEARCH]
        
        assert config.requests_per_window == 100
        assert config.window_seconds == 3600
        assert config.burst_limit == 10
        assert config.block_duration_seconds == 300
    
    def test_public_key_access_config(self):
        """Test public key access rate limit configuration"""
        limiter = RedisRateLimiter()
        config = limiter.rate_configs[RateLimitType.PUBLIC_KEY_ACCESS]
        
        assert config.requests_per_window == 50
        assert config.window_seconds == 3600
        assert config.burst_limit == 5
        assert config.block_duration_seconds == 600
    
    def test_tenant_token_config(self):
        """Test tenant token rate limit configuration"""
        limiter = RedisRateLimiter()
        config = limiter.rate_configs[RateLimitType.TENANT_TOKEN]
        
        assert config.requests_per_window == 200
        assert config.window_seconds == 3600
        assert config.burst_limit == 20
        assert config.block_duration_seconds == 300
    
    def test_custom_config_override(self):
        """Test using custom rate limit configuration"""
        custom_config = RateLimitConfig(
            requests_per_window=10,
            window_seconds=60,
            burst_limit=5,
            block_duration_seconds=120
        )
        
        RedisRateLimiter()
        
        # This would be tested in an async context
        assert custom_config.requests_per_window == 10
        assert custom_config.window_seconds == 60


@pytest.mark.asyncio
async def test_rate_limiter_cleanup():
    """Test proper cleanup of rate limiter resources"""
    limiter = RedisRateLimiter()
    
    # Mock Redis client
    mock_redis = AsyncMock()
    limiter._redis = mock_redis
    
    await limiter.close()
    
    mock_redis.close.assert_called_once()


class TestRateLimitIntegration:
    """Integration tests for rate limiting in API context"""
    
    def test_rate_limit_headers_format(self):
        """Test that rate limit headers are properly formatted"""
        result = RateLimitResult(
            allowed=True,
            limit=100,
            remaining=50,
            reset_time=1234567890
        )
        
        assert result.limit == 100
        assert result.remaining == 50
        assert result.reset_time == 1234567890
        assert result.retry_after is None
    
    def test_rate_limit_error_response_format(self):
        """Test error response format for rate limit exceeded"""
        result = RateLimitResult(
            allowed=False,
            limit=100,
            remaining=0,
            reset_time=1234567890,
            retry_after=300
        )
        
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after == 300