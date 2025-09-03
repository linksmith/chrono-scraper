"""
URL fetching service with proxy support and rate limiting
"""
import asyncio
import aiohttp
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlparse
import logging
from dataclasses import dataclass
import random

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Proxy configuration"""
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    enabled: bool = True


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    requests_per_second: float = 1.0
    burst_size: int = 5
    delay_between_requests: float = 1.0


@dataclass
class FetchConfig:
    """Fetch configuration"""
    timeout: int = 30
    max_redirects: int = 10
    max_retries: int = 3
    retry_delay: float = 1.0
    user_agent: str = "chrono-scraper/1.0 (research tool)"
    headers: Optional[Dict[str, str]] = None
    proxy: Optional[ProxyConfig] = None
    rate_limit: Optional[RateLimitConfig] = None


class RateLimiter:
    """Token bucket rate limiter"""
    
    def __init__(self, requests_per_second: float = 1.0, burst_size: int = 5):
        self.requests_per_second = requests_per_second
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """Acquire a token, blocking if necessary"""
        async with self._lock:
            now = time.time()
            time_passed = now - self.last_update
            self.last_update = now
            
            # Add tokens based on time passed
            self.tokens = min(
                self.burst_size,
                self.tokens + time_passed * self.requests_per_second
            )
            
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            else:
                # Calculate wait time
                wait_time = (1 - self.tokens) / self.requests_per_second
                await asyncio.sleep(wait_time)
                self.tokens = 0
                return True


class URLFetchService:
    """Service for fetching URLs with proxy support and rate limiting"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limiters: Dict[str, RateLimiter] = {}
        self.last_request_times: Dict[str, float] = {}
    
    async def get_session(self, config: FetchConfig) -> aiohttp.ClientSession:
        """Get or create aiohttp session with proxy support"""
        if not self.session or self.session.closed:
            connector_kwargs = {}
            
            # Set up proxy if configured
            if config.proxy and config.proxy.enabled:
                if config.proxy.username and config.proxy.password:
                    # Proxy with authentication
                    proxy_auth = aiohttp.BasicAuth(
                        config.proxy.username,
                        config.proxy.password
                    )
                    connector_kwargs["proxy"] = config.proxy.url
                    connector_kwargs["proxy_auth"] = proxy_auth
                else:
                    # Proxy without authentication
                    connector_kwargs["proxy"] = config.proxy.url
            
            # Create connector
            connector = aiohttp.TCPConnector(**connector_kwargs)
            
            # Set up timeout
            timeout = aiohttp.ClientTimeout(total=config.timeout)
            
            # Set up headers
            headers = {
                "User-Agent": config.user_agent
            }
            if config.headers:
                headers.update(config.headers)
            
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers=headers
            )
        
        return self.session
    
    async def close_session(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    def get_rate_limiter(self, domain: str, config: FetchConfig) -> Optional[RateLimiter]:
        """Get rate limiter for a domain"""
        if not config.rate_limit:
            return None
        
        if domain not in self.rate_limiters:
            self.rate_limiters[domain] = RateLimiter(
                requests_per_second=config.rate_limit.requests_per_second,
                burst_size=config.rate_limit.burst_size
            )
        
        return self.rate_limiters[domain]
    
    async def apply_rate_limiting(self, url: str, config: FetchConfig):
        """Apply rate limiting for a URL"""
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Apply rate limiter if configured
        rate_limiter = self.get_rate_limiter(domain, config)
        if rate_limiter:
            await rate_limiter.acquire()
        
        # Apply simple delay if configured
        if config.rate_limit and config.rate_limit.delay_between_requests > 0:
            last_request = self.last_request_times.get(domain, 0)
            time_since_last = time.time() - last_request
            
            if time_since_last < config.rate_limit.delay_between_requests:
                delay = config.rate_limit.delay_between_requests - time_since_last
                await asyncio.sleep(delay)
        
        # Update last request time
        self.last_request_times[domain] = time.time()
    
    async def fetch_url(
        self,
        url: str,
        config: Optional[FetchConfig] = None,
        method: str = "GET",
        data: Optional[Union[str, bytes, Dict]] = None
    ) -> Dict[str, Any]:
        """
        Fetch a single URL with retry logic
        
        Args:
            url: URL to fetch
            config: Fetch configuration
            method: HTTP method
            data: Request data for POST/PUT
        
        Returns:
            Dictionary with response data and metadata
        """
        if config is None:
            config = FetchConfig()
        
        session = await self.get_session(config)
        
        # Apply rate limiting
        await self.apply_rate_limiting(url, config)
        
        last_exception = None
        
        for attempt in range(config.max_retries + 1):
            try:
                logger.debug(f"Fetching {url} (attempt {attempt + 1})")
                
                # Add random jitter to avoid thundering herd
                if attempt > 0:
                    jitter = random.uniform(0.1, 0.5)
                    await asyncio.sleep(config.retry_delay + jitter)
                
                async with session.request(
                    method,
                    url,
                    data=data,
                    max_redirects=config.max_redirects,
                    allow_redirects=True
                ) as response:
                    content = await response.read()
                    text_content = None
                    
                    # Try to decode as text
                    try:
                        text_content = content.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            text_content = content.decode('latin-1')
                        except UnicodeDecodeError:
                            logger.warning(f"Could not decode content as text for {url}")
                    
                    return {
                        "url": str(response.url),
                        "original_url": url,
                        "status_code": response.status,
                        "headers": dict(response.headers),
                        "content": content,
                        "text": text_content,
                        "content_type": response.headers.get("content-type", ""),
                        "content_length": len(content),
                        "encoding": response.charset,
                        "final_url": str(response.url),
                        "redirected": str(response.url) != url,
                        "fetch_time": datetime.utcnow(),
                        "attempt": attempt + 1,
                        "success": True
                    }
                    
            except asyncio.TimeoutError as e:
                last_exception = e
                logger.warning(f"Timeout fetching {url} (attempt {attempt + 1})")
                
            except aiohttp.ClientError as e:
                last_exception = e
                logger.warning(f"Client error fetching {url} (attempt {attempt + 1}): {str(e)}")
                
            except Exception as e:
                last_exception = e
                logger.error(f"Unexpected error fetching {url} (attempt {attempt + 1}): {str(e)}")
        
        # All retries failed
        return {
            "url": url,
            "original_url": url,
            "status_code": None,
            "headers": {},
            "content": None,
            "text": None,
            "content_type": "",
            "content_length": 0,
            "encoding": None,
            "final_url": url,
            "redirected": False,
            "fetch_time": datetime.utcnow(),
            "attempt": config.max_retries + 1,
            "success": False,
            "error": str(last_exception) if last_exception else "Unknown error"
        }
    
    async def fetch_urls_batch(
        self,
        urls: List[str],
        config: Optional[FetchConfig] = None,
        concurrency: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fetch multiple URLs concurrently with rate limiting
        
        Args:
            urls: List of URLs to fetch
            config: Fetch configuration
            concurrency: Maximum concurrent requests
        
        Returns:
            List of response dictionaries
        """
        if config is None:
            config = FetchConfig()
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def fetch_with_semaphore(url: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.fetch_url(url, config)
        
        tasks = [fetch_with_semaphore(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "url": urls[i],
                    "original_url": urls[i],
                    "status_code": None,
                    "success": False,
                    "error": str(result),
                    "fetch_time": datetime.utcnow()
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def check_url_availability(
        self,
        url: str,
        config: Optional[FetchConfig] = None
    ) -> Dict[str, Any]:
        """
        Check if a URL is available using HEAD request
        
        Args:
            url: URL to check
            config: Fetch configuration
        
        Returns:
            Dictionary with availability information
        """
        if config is None:
            config = FetchConfig(timeout=10)  # Shorter timeout for HEAD requests
        
        result = await self.fetch_url(url, config, method="HEAD")
        
        return {
            "url": url,
            "available": result["success"] and 200 <= (result["status_code"] or 0) < 400,
            "status_code": result["status_code"],
            "final_url": result["final_url"],
            "redirected": result["redirected"],
            "content_type": result["content_type"],
            "content_length": result.get("content_length", 0),
            "checked_at": result["fetch_time"],
            "error": result.get("error")
        }
    
    async def fetch_with_fallback_user_agents(
        self,
        url: str,
        config: Optional[FetchConfig] = None,
        user_agents: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Fetch URL with fallback user agents if blocked
        
        Args:
            url: URL to fetch
            config: Fetch configuration
            user_agents: List of user agents to try
        
        Returns:
            Dictionary with response data
        """
        if user_agents is None:
            user_agents = [
                "chrono-scraper/1.0 (research tool)",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ]
        
        if config is None:
            config = FetchConfig()
        
        for user_agent in user_agents:
            # Create new config with different user agent
            ua_config = FetchConfig(
                timeout=config.timeout,
                max_redirects=config.max_redirects,
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
                user_agent=user_agent,
                headers=config.headers,
                proxy=config.proxy,
                rate_limit=config.rate_limit
            )
            
            result = await self.fetch_url(url, ua_config)
            
            # If successful or client error (not server error), return result
            if result["success"] or (result["status_code"] and 400 <= result["status_code"] < 500):
                return result
            
            # Add small delay between user agent attempts
            await asyncio.sleep(0.5)
        
        # Return last result if all user agents failed
        return result
    
    def create_default_config(
        self,
        requests_per_second: float = 1.0,
        timeout: int = 30,
        use_proxy: bool = False
    ) -> FetchConfig:
        """
        Create a default fetch configuration
        
        Args:
            requests_per_second: Rate limit for requests
            timeout: Request timeout in seconds
            use_proxy: Whether to use proxy if available
        
        Returns:
            FetchConfig instance
        """
        proxy_config = None
        if use_proxy and hasattr(settings, 'PROXY_URL') and settings.PROXY_URL:
            proxy_config = ProxyConfig(
                url=settings.PROXY_URL,
                username=getattr(settings, 'PROXY_USERNAME', None),
                password=getattr(settings, 'PROXY_PASSWORD', None)
            )
        
        rate_limit_config = RateLimitConfig(
            requests_per_second=requests_per_second,
            burst_size=max(5, int(requests_per_second * 2)),
            delay_between_requests=1.0 / requests_per_second
        )
        
        return FetchConfig(
            timeout=timeout,
            proxy=proxy_config,
            rate_limit=rate_limit_config
        )


# Global service instance
fetch_service = URLFetchService()