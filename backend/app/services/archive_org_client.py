"""
Specialized Archive.org client with rate limiting, browser headers, and retry logic
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import random

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

logger = logging.getLogger(__name__)


class ArchiveOrgRateLimiter:
    """Rate limiter for Archive.org (15 requests/minute = 4 seconds between requests)"""
    
    def __init__(self, requests_per_minute: int = 15):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute  # 4 seconds for 15/min
        self.last_request_time = 0.0
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self):
        """Wait if necessary to comply with rate limiting"""
        async with self._lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                logger.info(f"Rate limiting: waiting {wait_time:.1f}s before Archive.org request")
                await asyncio.sleep(wait_time)
            
            self.last_request_time = time.time()


class ArchiveOrgClient:
    """
    Specialized client for Archive.org with browser-like behavior and rate limiting
    """
    
    def __init__(self):
        self.rate_limiter = ArchiveOrgRateLimiter(requests_per_minute=15)
        self.session_created = datetime.now()
        self.request_count = 0
        
        # Configure proxy settings for Archive.org access
        from app.core.config import settings
        self.proxy_settings = {}
        proxy_server = getattr(settings, 'PROXY_SERVER', None)
        proxy_username = getattr(settings, 'PROXY_USERNAME', None)
        proxy_password = getattr(settings, 'PROXY_PASSWORD', None)
        
        if proxy_server:
            if proxy_username and proxy_password:
                # Authenticated proxy
                proxy_url = f"http://{proxy_username}:{proxy_password}@{proxy_server.replace('http://', '')}"
            else:
                # Unauthenticated proxy
                proxy_url = proxy_server if proxy_server.startswith('http') else f"http://{proxy_server}"
            
            self.proxy_settings = {
                "http://": proxy_url,
                "https://": proxy_url
            }
            logger.info(f"Archive.org client configured with proxy: {proxy_server}")
        
        # Browser-like headers
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        }
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delays = [30, 120, 300]  # 30s, 2min, 5min
        self.timeout = 180  # 3 minutes
    
    def _get_headers_for_url(self, url: str) -> Dict[str, str]:
        """Get appropriate headers for the given URL"""
        headers = self.default_headers.copy()
        
        # Add referrer for Wayback Machine URLs to look more natural
        if "web.archive.org" in url:
            headers["Referer"] = "https://web.archive.org/"
        
        # Vary some headers slightly to look more human
        if random.random() < 0.3:  # 30% chance
            headers["Accept-Language"] = random.choice([
                "en-US,en;q=0.9",
                "en-US,en;q=0.8,es;q=0.6",
                "en-GB,en;q=0.9,en-US;q=0.8"
            ])
        
        return headers
    
    @retry(
        stop=stop_after_attempt(4),  # 1 initial + 3 retries
        wait=wait_exponential(multiplier=1, min=30, max=300),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError)),
        before_sleep=before_sleep_log(logger, logging.INFO),
        reraise=True
    )
    async def _make_request(self, url: str, method: str = "GET", **kwargs) -> httpx.Response:
        """Make HTTP request with retries and error handling"""
        await self.rate_limiter.wait_if_needed()
        
        headers = kwargs.pop("headers", {})
        request_headers = self._get_headers_for_url(url)
        request_headers.update(headers)
        
        timeout = httpx.Timeout(
            connect=60.0,    # 1 minute to connect
            read=self.timeout,   # 3 minutes to read
            write=30.0,      # 30 seconds to write
            pool=10.0        # 10 seconds to get connection from pool
        )
        
        self.request_count += 1
        
        logger.info(f"Archive.org request #{self.request_count}: {method} {url}")
        
        # Configure client with proxy support
        client_kwargs = {
            "timeout": timeout,
            "limits": httpx.Limits(max_keepalive_connections=5, max_connections=10),
            "follow_redirects": True
        }
        
        if self.proxy_settings:
            # httpx uses a single proxy string, not a dict like requests
            proxy_url = self.proxy_settings.get("http://") or self.proxy_settings.get("https://")
            client_kwargs["proxy"] = proxy_url
        
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=request_headers,
                **kwargs
            )
            
            # Handle specific Archive.org error codes
            if response.status_code == 522:
                logger.warning(f"Archive.org returned 522 (Connection Timeout) for {url}")
                raise httpx.HTTPStatusError(
                    "Archive.org connection timeout (522)", 
                    request=response.request, 
                    response=response
                )
            elif response.status_code == 429:
                logger.warning(f"Archive.org rate limit exceeded (429) for {url}")
                # Wait longer for rate limiting
                await asyncio.sleep(60)
                raise httpx.HTTPStatusError(
                    "Archive.org rate limit (429)", 
                    request=response.request, 
                    response=response
                )
            elif response.status_code >= 500:
                logger.warning(f"Archive.org server error {response.status_code} for {url}")
                raise httpx.HTTPStatusError(
                    f"Archive.org server error ({response.status_code})", 
                    request=response.request, 
                    response=response
                )
            
            response.raise_for_status()
            return response
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """GET request with Archive.org optimizations"""
        return await self._make_request(url, "GET", **kwargs)
    
    async def head(self, url: str, **kwargs) -> httpx.Response:
        """HEAD request with Archive.org optimizations"""
        return await self._make_request(url, "HEAD", **kwargs)
    
    async def fetch_content(self, url: str) -> str:
        """Fetch content from Archive.org URL with optimizations"""
        response = await self.get(url)
        return response.text
    
    async def test_connectivity(self, test_url: Optional[str] = None) -> Dict[str, Any]:
        """Test connectivity to Archive.org"""
        test_url = test_url or "https://web.archive.org/"
        
        try:
            start_time = time.time()
            response = await self.head(test_url)
            duration = time.time() - start_time
            
            return {
                "success": True,
                "status_code": response.status_code,
                "duration_seconds": duration,
                "headers": dict(response.headers),
                "message": f"Successfully connected to Archive.org in {duration:.1f}s"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "message": f"Failed to connect to Archive.org: {e}"
            }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        uptime = datetime.now() - self.session_created
        
        return {
            "session_uptime_seconds": uptime.total_seconds(),
            "total_requests": self.request_count,
            "rate_limit_rps": self.rate_limiter.requests_per_minute / 60,
            "average_requests_per_minute": (self.request_count / uptime.total_seconds()) * 60 if uptime.total_seconds() > 0 else 0,
            "last_request_time": self.rate_limiter.last_request_time
        }


# Global instance for reuse across requests
_archive_client = None

def get_archive_client() -> ArchiveOrgClient:
    """Get singleton Archive.org client"""
    global _archive_client
    if _archive_client is None:
        _archive_client = ArchiveOrgClient()
    return _archive_client