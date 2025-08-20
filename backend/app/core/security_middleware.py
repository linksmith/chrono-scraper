"""
Security middleware for Chrono Scraper
"""
import time
import json
from typing import Dict, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from redis.asyncio import Redis

from app.core.config import settings
from app.services.session_store import get_session_store


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis"""
    
    def __init__(self, app, redis_client: Optional[Redis] = None):
        super().__init__(app)
        self.redis_client = redis_client
        
        # Rate limit configurations per endpoint pattern
        self.rate_limits = {
            # Authentication endpoints
            "/api/v1/auth/login": {"requests": 5, "window": 300},  # 5 requests per 5 minutes
            "/api/v1/auth/register": {"requests": 3, "window": 3600},  # 3 requests per hour
            "/api/v1/auth/register-with-invitation": {"requests": 5, "window": 3600},  # 5 requests per hour
            "/api/v1/auth/password-reset": {"requests": 3, "window": 3600},  # 3 requests per hour
            
            # Admin endpoints
            "/api/v1/admin": {"requests": 100, "window": 3600},  # 100 requests per hour
            
            # General API endpoints
            "/api/v1": {"requests": 1000, "window": 3600},  # 1000 requests per hour (general limit)
            
            # Scraping endpoints (more restrictive)
            "/api/v1/scrape": {"requests": 50, "window": 3600},  # 50 requests per hour
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Apply rate limiting to requests"""
        # Lazy initialize Redis client if not set
        if not self.redis_client:
            try:
                session_store = await get_session_store()
                self.redis_client = session_store.redis
            except Exception:
                # If initialization fails, proceed without rate limiting
                pass

        # Skip rate limiting for admin users
        if await self._is_admin_user(request):
            return await call_next(request)
        
        # Skip if Redis is not available
        if not self.redis_client:
            return await call_next(request)
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Find applicable rate limit
        rate_limit = self._get_rate_limit_for_path(request.url.path)
        
        if rate_limit:
            # Check rate limit
            is_allowed, retry_after = await self._check_rate_limit(
                client_ip, 
                request.url.path,
                rate_limit["requests"],
                rate_limit["window"]
            )
            
            if not is_allowed:
                return JSONResponse(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Rate limit exceeded. Please try again later.",
                        "retry_after": retry_after
                    },
                    headers={"Retry-After": str(retry_after)}
                )
        
        # Add rate limit headers to response
        response = await call_next(request)
        
        if rate_limit:
            current_count = await self._get_current_count(client_ip, request.url.path)
            response.headers["X-RateLimit-Limit"] = str(rate_limit["requests"])
            response.headers["X-RateLimit-Remaining"] = str(max(0, rate_limit["requests"] - current_count))
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + rate_limit["window"])
        
        return response
    
    async def _is_admin_user(self, request: Request) -> bool:
        """Check if the request is from an admin user"""
        try:
            session_store = await get_session_store()
            session_id = request.cookies.get("session_id")
            
            if session_id:
                session_data = await session_store.get_session(session_id)
                if session_data:
                    return session_data.get("is_admin", False) or session_data.get("is_superuser", False)
        except Exception:
            pass
        
        return False
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        # Check for forwarded headers (proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"
    
    def _get_rate_limit_for_path(self, path: str) -> Optional[Dict[str, int]]:
        """Get rate limit configuration for a path"""
        # Check for exact matches first
        if path in self.rate_limits:
            return self.rate_limits[path]
        
        # Check for prefix matches (most specific first)
        sorted_patterns = sorted(self.rate_limits.keys(), key=len, reverse=True)
        for pattern in sorted_patterns:
            if path.startswith(pattern):
                return self.rate_limits[pattern]
        
        return None
    
    async def _check_rate_limit(self, client_ip: str, path: str, max_requests: int, window: int) -> tuple[bool, int]:
        """Check if request is within rate limit"""
        try:
            key = f"ratelimit:{client_ip}:{path}"
            current_time = int(time.time())
            
            # Use Redis sliding window counter
            pipe = self.redis_client.pipeline()
            
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, current_time - window)
            
            # Count current requests
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiry
            pipe.expire(key, window)
            
            results = await pipe.execute()
            current_count = results[1]  # Count after cleanup
            
            if current_count >= max_requests:
                # Calculate retry after time
                oldest_request = await self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_request:
                    retry_after = int(oldest_request[0][1]) + window - current_time
                    return False, max(1, retry_after)
                return False, window
            
            return True, 0
            
        except Exception as e:
            # If Redis fails, allow the request (fail open)
            print(f"Rate limiting error: {e}")
            return True, 0
    
    async def _get_current_count(self, client_ip: str, path: str) -> int:
        """Get current request count for rate limit headers"""
        try:
            key = f"ratelimit:{client_ip}:{path}"
            return await self.redis_client.zcard(key)
        except Exception:
            return 0


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to responses"""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to all responses"""
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # HSTS (HTTP Strict Transport Security) for production
        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        # Content Security Policy
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "img-src 'self' data: https:",
            "font-src 'self' https://cdnjs.cloudflare.com",
            "connect-src 'self'",
            "form-action 'self'",
            "base-uri 'self'",
            "frame-ancestors 'none'",
            "object-src 'none'"
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log security-relevant requests"""
    
    def __init__(self, app, log_sensitive_endpoints: bool = True):
        super().__init__(app)
        self.log_sensitive_endpoints = log_sensitive_endpoints
        
        # Endpoints to log for security monitoring
        self.sensitive_endpoints = {
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/password-reset",
            "/api/v1/admin",
            "/admin"
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Log requests to sensitive endpoints"""
        start_time = time.time()
        
        # Log request if it's to a sensitive endpoint
        should_log = any(
            request.url.path.startswith(endpoint) 
            for endpoint in self.sensitive_endpoints
        ) if self.log_sensitive_endpoints else False
        
        if should_log:
            client_ip = self._get_client_ip(request)
            user_agent = request.headers.get("User-Agent", "Unknown")
            
            log_data = {
                "timestamp": time.time(),
                "method": request.method,
                "path": request.url.path,
                "client_ip": client_ip,
                "user_agent": user_agent
            }
        
        response = await call_next(request)
        
        if should_log:
            processing_time = time.time() - start_time
            log_data.update({
                "status_code": response.status_code,
                "processing_time": processing_time
            })
            
            # Log failed authentication attempts
            if request.url.path.startswith("/api/v1/auth/login") and response.status_code >= 400:
                print(f"SECURITY: Failed login attempt - IP: {client_ip}, Status: {response.status_code}")
            
            # Log admin access
            if request.url.path.startswith("/admin") or request.url.path.startswith("/api/v1/admin"):
                print(f"SECURITY: Admin access - IP: {client_ip}, Path: {request.url.path}, Status: {response.status_code}")
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else "unknown"


class SessionSecurityMiddleware(BaseHTTPMiddleware):
    """Enhanced session security middleware"""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Apply session security measures"""
        response = await call_next(request)
        
        # Set secure session cookie attributes
        if "set-cookie" in response.headers:
            # Modify session cookies to be secure
            cookies = response.headers.getlist("set-cookie")
            new_cookies = []
            
            for cookie in cookies:
                if "session" in cookie.lower():
                    # Add security attributes
                    if "HttpOnly" not in cookie:
                        cookie += "; HttpOnly"
                    if "SameSite" not in cookie:
                        cookie += "; SameSite=Lax"
                    if settings.ENVIRONMENT == "production" and "Secure" not in cookie:
                        cookie += "; Secure"
                
                new_cookies.append(cookie)
            
            # Replace cookies (remove existing header instances safely)
            try:
                del response.headers["set-cookie"]
            except KeyError:
                pass
            for cookie in new_cookies:
                response.headers.append("set-cookie", cookie)
        
        return response