"""
Advanced rate limiting with multiple algorithms and threat detection
Implements sliding window, token bucket, and adaptive rate limiting
"""
import time
import json
from typing import Dict, Optional, Tuple
from redis.asyncio import Redis
from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.security_modules.types import RateLimitAlgorithm, ThreatLevel, RateLimitConfig


class AdvancedRateLimit:
    """Advanced rate limiting with multiple algorithms and threat awareness"""
    
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        
        # Rate limit configurations for different endpoints
        self.rate_limits = {
            # Authentication endpoints (stricter limits)
            "/api/v1/auth/login": RateLimitConfig(
                requests=5,
                window=300,  # 5 minutes
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                adaptive=True
            ),
            "/api/v1/auth/register": RateLimitConfig(
                requests=3,
                window=3600,  # 1 hour
                algorithm=RateLimitAlgorithm.FIXED_WINDOW
            ),
            "/api/v1/auth/password-reset": RateLimitConfig(
                requests=3,
                window=3600,  # 1 hour
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW
            ),
            
            # Admin endpoints (higher limits but threat-aware)
            "/api/v1/admin": RateLimitConfig(
                requests=200,
                window=3600,  # 1 hour
                algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
                adaptive=True,
                burst_multiplier=2.0
            ),
            "/admin": RateLimitConfig(
                requests=100,
                window=3600,  # 1 hour
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
                adaptive=True
            ),
            
            # API endpoints by tier
            "/api/v1/projects": RateLimitConfig(
                requests=1000,
                window=3600,  # 1 hour
                algorithm=RateLimitAlgorithm.TOKEN_BUCKET
            ),
            "/api/v1/pages": RateLimitConfig(
                requests=2000,
                window=3600,  # 1 hour
                algorithm=RateLimitAlgorithm.TOKEN_BUCKET
            ),
            "/api/v1/search": RateLimitConfig(
                requests=500,
                window=3600,  # 1 hour
                algorithm=RateLimitAlgorithm.SLIDING_WINDOW
            ),
            
            # Scraping endpoints (resource intensive)
            "/api/v1/scrape": RateLimitConfig(
                requests=50,
                window=3600,  # 1 hour
                algorithm=RateLimitAlgorithm.LEAKY_BUCKET,
                adaptive=True
            ),
            
            # Global fallback
            "/api/v1": RateLimitConfig(
                requests=10000,
                window=3600,  # 1 hour
                algorithm=RateLimitAlgorithm.TOKEN_BUCKET,
                adaptive=True
            )
        }
    
    async def check_rate_limit(
        self,
        identifier: str,
        endpoint: str,
        user_tier: str = "standard",
        threat_level: ThreatLevel = ThreatLevel.LOW
    ) -> Tuple[bool, Dict[str, any]]:
        """
        Check if request is within rate limit
        Returns: (allowed, metadata)
        """
        config = self._get_rate_limit_config(endpoint)
        if not config:
            return True, {}
        
        # Apply threat-based adjustment
        if config.adaptive:
            config = self._adjust_for_threat_level(config, threat_level)
        
        # Apply user tier adjustment
        config = self._adjust_for_user_tier(config, user_tier)
        
        # Check based on algorithm
        if config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
            return await self._check_sliding_window(identifier, endpoint, config)
        elif config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            return await self._check_token_bucket(identifier, endpoint, config)
        elif config.algorithm == RateLimitAlgorithm.LEAKY_BUCKET:
            return await self._check_leaky_bucket(identifier, endpoint, config)
        elif config.algorithm == RateLimitAlgorithm.FIXED_WINDOW:
            return await self._check_fixed_window(identifier, endpoint, config)
        elif config.algorithm == RateLimitAlgorithm.ADAPTIVE:
            return await self._check_adaptive(identifier, endpoint, config, threat_level)
        
        return True, {}
    
    def _get_rate_limit_config(self, endpoint: str) -> Optional[RateLimitConfig]:
        """Get rate limit configuration for endpoint"""
        # Check for exact match first
        if endpoint in self.rate_limits:
            return self.rate_limits[endpoint]
        
        # Check for prefix matches (most specific first)
        sorted_patterns = sorted(self.rate_limits.keys(), key=len, reverse=True)
        for pattern in sorted_patterns:
            if endpoint.startswith(pattern):
                return self.rate_limits[pattern]
        
        return None
    
    def _adjust_for_threat_level(self, config: RateLimitConfig, threat_level: ThreatLevel) -> RateLimitConfig:
        """Adjust rate limit based on threat level"""
        if not config.adaptive:
            return config
        
        reduction_factor = config.threat_reduction_factor.get(threat_level, 1.0)
        
        # Create adjusted config
        adjusted_config = RateLimitConfig(
            requests=int(config.requests * reduction_factor),
            window=config.window,
            algorithm=config.algorithm,
            burst_multiplier=config.burst_multiplier,
            adaptive=config.adaptive,
            threat_reduction_factor=config.threat_reduction_factor
        )
        
        return adjusted_config
    
    def _adjust_for_user_tier(self, config: RateLimitConfig, user_tier: str) -> RateLimitConfig:
        """Adjust rate limit based on user tier"""
        tier_multipliers = {
            "admin": 5.0,
            "premium": 3.0,
            "professional": 2.0,
            "standard": 1.0,
            "free": 0.5
        }
        
        multiplier = tier_multipliers.get(user_tier, 1.0)
        
        # Create adjusted config
        adjusted_config = RateLimitConfig(
            requests=int(config.requests * multiplier),
            window=config.window,
            algorithm=config.algorithm,
            burst_multiplier=config.burst_multiplier,
            adaptive=config.adaptive,
            threat_reduction_factor=config.threat_reduction_factor
        )
        
        return adjusted_config
    
    async def _check_sliding_window(
        self, identifier: str, endpoint: str, config: RateLimitConfig
    ) -> Tuple[bool, Dict[str, any]]:
        """Sliding window rate limiting"""
        key = f"rate_limit:sliding:{identifier}:{endpoint}"
        current_time = time.time()
        
        pipe = self.redis.pipeline()
        
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, current_time - config.window)
        
        # Count current requests
        pipe.zcard(key)
        
        # Add current request
        pipe.zadd(key, {str(current_time): current_time})
        
        # Set expiry
        pipe.expire(key, config.window)
        
        results = await pipe.execute()
        current_count = results[1]
        
        # Check if within limit
        allowed = current_count < config.requests
        
        # Calculate reset time
        if not allowed:
            # Get oldest request time
            oldest_requests = await self.redis.zrange(key, 0, 0, withscores=True)
            if oldest_requests:
                reset_time = oldest_requests[0][1] + config.window
            else:
                reset_time = current_time + config.window
        else:
            reset_time = current_time + config.window
        
        metadata = {
            "limit": config.requests,
            "remaining": max(0, config.requests - current_count),
            "reset": int(reset_time),
            "algorithm": config.algorithm.value,
            "window": config.window
        }
        
        return allowed, metadata
    
    async def _check_token_bucket(
        self, identifier: str, endpoint: str, config: RateLimitConfig
    ) -> Tuple[bool, Dict[str, any]]:
        """Token bucket rate limiting"""
        key = f"rate_limit:bucket:{identifier}:{endpoint}"
        current_time = time.time()
        
        # Get current bucket state
        bucket_data = await self.redis.get(key)
        
        if bucket_data:
            bucket = json.loads(bucket_data)
            tokens = bucket["tokens"]
            last_refill = bucket["last_refill"]
        else:
            # Initialize bucket
            tokens = config.requests
            last_refill = current_time
        
        # Calculate tokens to add based on time passed
        time_passed = current_time - last_refill
        tokens_to_add = time_passed * (config.requests / config.window)
        
        # Add tokens (up to bucket capacity)
        bucket_capacity = int(config.requests * config.burst_multiplier)
        tokens = min(bucket_capacity, tokens + tokens_to_add)
        
        # Check if request can be served
        if tokens >= 1:
            tokens -= 1
            allowed = True
        else:
            allowed = False
        
        # Update bucket state
        bucket_data = {
            "tokens": tokens,
            "last_refill": current_time
        }
        await self.redis.setex(key, config.window, json.dumps(bucket_data))
        
        # Calculate when bucket will have tokens again
        if not allowed:
            refill_rate = config.requests / config.window
            time_to_next_token = (1 - tokens) / refill_rate
            reset_time = current_time + time_to_next_token
        else:
            reset_time = current_time
        
        metadata = {
            "limit": config.requests,
            "remaining": int(tokens),
            "reset": int(reset_time),
            "algorithm": config.algorithm.value,
            "bucket_capacity": bucket_capacity,
            "refill_rate": config.requests / config.window
        }
        
        return allowed, metadata
    
    async def _check_leaky_bucket(
        self, identifier: str, endpoint: str, config: RateLimitConfig
    ) -> Tuple[bool, Dict[str, any]]:
        """Leaky bucket rate limiting"""
        key = f"rate_limit:leaky:{identifier}:{endpoint}"
        current_time = time.time()
        
        # Get current bucket state
        bucket_data = await self.redis.get(key)
        
        if bucket_data:
            bucket = json.loads(bucket_data)
            level = bucket["level"]
            last_leak = bucket["last_leak"]
        else:
            # Initialize bucket
            level = 0
            last_leak = current_time
        
        # Calculate leak (requests processed)
        time_passed = current_time - last_leak
        leak_rate = config.requests / config.window
        leaked = time_passed * leak_rate
        
        # Update level (subtract leaked requests)
        level = max(0, level - leaked)
        
        # Check if bucket has capacity
        bucket_capacity = int(config.requests * config.burst_multiplier)
        if level < bucket_capacity:
            level += 1
            allowed = True
        else:
            allowed = False
        
        # Update bucket state
        bucket_data = {
            "level": level,
            "last_leak": current_time
        }
        await self.redis.setex(key, config.window * 2, json.dumps(bucket_data))
        
        # Calculate reset time
        if not allowed:
            time_to_drain = (level - bucket_capacity + 1) / leak_rate
            reset_time = current_time + time_to_drain
        else:
            reset_time = current_time
        
        metadata = {
            "limit": config.requests,
            "remaining": max(0, bucket_capacity - int(level)),
            "reset": int(reset_time),
            "algorithm": config.algorithm.value,
            "bucket_capacity": bucket_capacity,
            "leak_rate": leak_rate,
            "current_level": level
        }
        
        return allowed, metadata
    
    async def _check_fixed_window(
        self, identifier: str, endpoint: str, config: RateLimitConfig
    ) -> Tuple[bool, Dict[str, any]]:
        """Fixed window rate limiting"""
        current_time = time.time()
        window_start = int(current_time // config.window) * config.window
        key = f"rate_limit:fixed:{identifier}:{endpoint}:{window_start}"
        
        # Get current count and increment
        current_count = await self.redis.incr(key)
        
        # Set expiry on first increment
        if current_count == 1:
            await self.redis.expire(key, config.window)
        
        allowed = current_count <= config.requests
        
        metadata = {
            "limit": config.requests,
            "remaining": max(0, config.requests - current_count),
            "reset": int(window_start + config.window),
            "algorithm": config.algorithm.value,
            "window": config.window,
            "window_start": window_start
        }
        
        return allowed, metadata
    
    async def _check_adaptive(
        self, identifier: str, endpoint: str, config: RateLimitConfig, threat_level: ThreatLevel
    ) -> Tuple[bool, Dict[str, any]]:
        """Adaptive rate limiting based on system load and threat level"""
        # Get system metrics
        cpu_usage = await self._get_system_cpu_usage()
        memory_usage = await self._get_system_memory_usage()
        
        # Calculate adaptive multiplier
        adaptive_multiplier = 1.0
        
        # Reduce limits under high system load
        if cpu_usage > 80:
            adaptive_multiplier *= 0.5
        elif cpu_usage > 60:
            adaptive_multiplier *= 0.7
        
        if memory_usage > 85:
            adaptive_multiplier *= 0.5
        elif memory_usage > 70:
            adaptive_multiplier *= 0.8
        
        # Apply threat level adjustment
        threat_multiplier = config.threat_reduction_factor.get(threat_level, 1.0)
        adaptive_multiplier *= threat_multiplier
        
        # Create adjusted config
        adjusted_config = RateLimitConfig(
            requests=int(config.requests * adaptive_multiplier),
            window=config.window,
            algorithm=RateLimitAlgorithm.SLIDING_WINDOW,  # Use sliding window as base
            burst_multiplier=config.burst_multiplier,
            adaptive=True,
            threat_reduction_factor=config.threat_reduction_factor
        )
        
        # Use sliding window with adjusted limits
        allowed, metadata = await self._check_sliding_window(identifier, endpoint, adjusted_config)
        
        # Add adaptive metadata
        metadata.update({
            "adaptive": True,
            "original_limit": config.requests,
            "adaptive_multiplier": adaptive_multiplier,
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "threat_level": threat_level.value
        })
        
        return allowed, metadata
    
    async def _get_system_cpu_usage(self) -> float:
        """Get current CPU usage percentage"""
        # In production, integrate with system monitoring
        # For now, return a mock value
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            return 0.0
    
    async def _get_system_memory_usage(self) -> float:
        """Get current memory usage percentage"""
        # In production, integrate with system monitoring
        # For now, return a mock value
        try:
            import psutil
            return psutil.virtual_memory().percent
        except ImportError:
            return 0.0
    
    async def get_rate_limit_status(self, identifier: str, endpoint: str) -> Dict[str, any]:
        """Get current rate limit status for identifier/endpoint"""
        config = self._get_rate_limit_config(endpoint)
        if not config:
            return {"status": "no_limit"}
        
        # Check current status without consuming tokens
        if config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
            key = f"rate_limit:sliding:{identifier}:{endpoint}"
            current_time = time.time()
            
            # Count current requests in window
            count = await self.redis.zcount(key, current_time - config.window, current_time)
            
            return {
                "algorithm": config.algorithm.value,
                "limit": config.requests,
                "remaining": max(0, config.requests - count),
                "reset": int(current_time + config.window),
                "window": config.window
            }
        
        elif config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            key = f"rate_limit:bucket:{identifier}:{endpoint}"
            bucket_data = await self.redis.get(key)
            
            if bucket_data:
                bucket = json.loads(bucket_data)
                return {
                    "algorithm": config.algorithm.value,
                    "limit": config.requests,
                    "remaining": int(bucket["tokens"]),
                    "bucket_capacity": int(config.requests * config.burst_multiplier)
                }
        
        # Default response
        return {
            "algorithm": config.algorithm.value,
            "limit": config.requests,
            "window": config.window
        }


class AdvancedRateLimitMiddleware(BaseHTTPMiddleware):
    """Advanced rate limiting middleware"""
    
    def __init__(self, app, redis_client: Redis):
        super().__init__(app)
        self.rate_limiter = AdvancedRateLimit(redis_client)
    
    async def dispatch(self, request: Request, call_next):
        """Apply advanced rate limiting"""
        # Skip rate limiting for certain conditions
        if await self._should_skip_rate_limiting(request):
            return await call_next(request)
        
        # Get identifier (IP or user ID)
        identifier = self._get_rate_limit_identifier(request)
        
        # Get user tier
        user_tier = await self._get_user_tier(request)
        
        # Get threat level
        threat_level = await self._assess_threat_level(request)
        
        # Check rate limit
        allowed, metadata = await self.rate_limiter.check_rate_limit(
            identifier,
            request.url.path,
            user_tier,
            threat_level
        )
        
        if not allowed:
            # Return rate limit exceeded response
            return self._create_rate_limit_response(metadata)
        
        # Continue with request
        response = await call_next(request)
        
        # Add rate limit headers
        self._add_rate_limit_headers(response, metadata)
        
        return response
    
    async def _should_skip_rate_limiting(self, request: Request) -> bool:
        """Check if rate limiting should be skipped"""
        # Skip for admin users (if configured)
        if hasattr(request.state, "user") and request.state.user:
            user = request.state.user
            if user.is_superuser and not settings.ENABLE_RATE_LIMITING:
                return True
        
        # Skip for health checks
        if request.url.path in ["/health", "/api/v1/health"]:
            return True
        
        return False
    
    def _get_rate_limit_identifier(self, request: Request) -> str:
        """Get identifier for rate limiting"""
        # Use user ID if authenticated
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.id}"
        
        # Use API key if present
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
        if api_key:
            return f"api_key:{api_key[:8]}"
        
        # Use IP address
        return f"ip:{self._get_client_ip(request)}"
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        # Check proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    async def _get_user_tier(self, request: Request) -> str:
        """Get user tier for rate limiting"""
        if hasattr(request.state, "user") and request.state.user:
            user = request.state.user
            if user.is_superuser:
                return "admin"
            # Add logic to get user tier from user model
            # return getattr(user, "tier", "standard")
        
        return "standard"
    
    async def _assess_threat_level(self, request: Request) -> ThreatLevel:
        """Assess threat level for request"""
        # In production, integrate with threat detection system
        # For now, use basic heuristics
        
        threat_score = 0
        
        # Check user agent
        user_agent = request.headers.get("User-Agent", "")
        if not user_agent or "bot" in user_agent.lower():
            threat_score += 1
        
        # Check for suspicious patterns
        suspicious_patterns = [
            "sql", "union", "select", "drop", "insert",
            "script", "alert", "javascript", "<script>",
            "../", "..\\", "passwd", "etc/passwd"
        ]
        
        query_string = str(request.url.query)
        for pattern in suspicious_patterns:
            if pattern in query_string.lower():
                threat_score += 2
                break
        
        # Map score to threat level
        if threat_score >= 4:
            return ThreatLevel.CRITICAL
        elif threat_score >= 3:
            return ThreatLevel.HIGH
        elif threat_score >= 1:
            return ThreatLevel.MEDIUM
        else:
            return ThreatLevel.LOW
    
    def _create_rate_limit_response(self, metadata: Dict[str, any]):
        """Create rate limit exceeded response"""
        from fastapi.responses import JSONResponse
        
        response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Rate limit exceeded",
                "retry_after": metadata.get("reset", 60),
                "limit": metadata.get("limit", 0),
                "window": metadata.get("window", 3600)
            }
        )
        
        self._add_rate_limit_headers(response, metadata)
        return response
    
    def _add_rate_limit_headers(self, response, metadata: Dict[str, any]):
        """Add rate limit headers to response"""
        response.headers["X-RateLimit-Limit"] = str(metadata.get("limit", 0))
        response.headers["X-RateLimit-Remaining"] = str(metadata.get("remaining", 0))
        response.headers["X-RateLimit-Reset"] = str(metadata.get("reset", 0))
        
        if "algorithm" in metadata:
            response.headers["X-RateLimit-Algorithm"] = metadata["algorithm"]
        
        if "window" in metadata:
            response.headers["X-RateLimit-Window"] = str(metadata["window"])
        
        if metadata.get("adaptive"):
            response.headers["X-RateLimit-Adaptive"] = "true"
            response.headers["X-RateLimit-Threat-Level"] = metadata.get("threat_level", "low")