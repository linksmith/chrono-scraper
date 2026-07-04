"""
Stealth headers for web scraping - user agent rotation and matching browser headers.

Provides realistic browser fingerprints to avoid detection when scraping
Archive.org and Common Crawl CDX APIs.
"""
import random
import asyncio
import time
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Current popular user agents (2025-2026 Chrome/Firefox/Edge)
_USER_AGENTS = {
    "chrome_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    ],
    "chrome_macos": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    ],
    "firefox_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    ],
    "firefox_macos": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    ],
    "edge_windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    ],
}

# Weighted by browser market share
_WEIGHTS = {
    "chrome_windows": 0.40,
    "chrome_macos": 0.15,
    "firefox_windows": 0.20,
    "firefox_macos": 0.08,
    "edge_windows": 0.17,
}


def get_random_user_agent() -> str:
    """Get a random user agent weighted by browser market share."""
    category = random.choices(
        list(_WEIGHTS.keys()),
        weights=list(_WEIGHTS.values()),
    )[0]
    return random.choice(_USER_AGENTS[category])


def get_stealth_headers(user_agent: Optional[str] = None) -> Dict[str, str]:
    """
    Get a complete set of realistic browser headers matching the user agent.

    Includes Sec-Ch-Ua, Sec-Fetch, and other headers that modern browsers send.
    This prevents fingerprinting based on header inconsistencies.
    """
    if user_agent is None:
        user_agent = get_random_user_agent()

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    if "Chrome" in user_agent and "Edg" not in user_agent:
        # Chrome-specific client hints
        headers["Sec-Ch-Ua"] = '"Not A(Brand";v="99", "Google Chrome";v="131", "Chromium";v="131"'
        headers["Sec-Ch-Ua-Mobile"] = "?0"
        headers["Sec-Ch-Ua-Platform"] = '"Windows"' if "Windows" in user_agent else '"macOS"'
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
        headers["Sec-Fetch-User"] = "?1"
    elif "Edg" in user_agent:
        headers["Sec-Ch-Ua"] = '"Not A(Brand";v="99", "Microsoft Edge";v="131", "Chromium";v="131"'
        headers["Sec-Ch-Ua-Mobile"] = "?0"
        headers["Sec-Ch-Ua-Platform"] = '"Windows"'
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
    # Firefox doesn't send Sec-Ch-Ua headers

    return headers


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter for Wayback Machine and Common Crawl.

    Wayback Machine: ~60 requests/minute soft limit
    Common Crawl: ~2 second minimum between requests

    Backs off exponentially on 429/503 responses and recovers gradually.
    """

    def __init__(
        self,
        max_requests_per_minute: int = 50,
        min_delay: float = 1.0,
        max_backoff: float = 300.0,
    ):
        self.max_requests_per_minute = max_requests_per_minute
        self.min_delay = min_delay
        self.max_backoff = max_backoff
        self._request_times: deque = deque()
        self._backoff_factor = 1.0
        self._blocked_until: Optional[float] = None
        self._consecutive_errors = 0

    async def wait_if_needed(self):
        """Wait if we're at the rate limit or in a backoff period."""
        now = time.monotonic()

        # Check if in backoff
        if self._blocked_until and now < self._blocked_until:
            wait = self._blocked_until - now
            logger.debug(f"Rate limiter: backing off for {wait:.1f}s")
            await asyncio.sleep(wait)
            self._blocked_until = None

        # Enforce minimum delay
        if self._request_times:
            elapsed = now - self._request_times[-1]
            if elapsed < self.min_delay:
                await asyncio.sleep(self.min_delay - elapsed)

        # Sliding window rate limit
        window_start = now - 60.0
        while self._request_times and self._request_times[0] < window_start:
            self._request_times.popleft()

        if len(self._request_times) >= self.max_requests_per_minute:
            wait = 60.0 - (now - self._request_times[0])
            if wait > 0:
                logger.info(f"Rate limiter: at {self.max_requests_per_minute} req/min, waiting {wait:.1f}s")
                await asyncio.sleep(wait)

        self._request_times.append(time.monotonic())

    def record_success(self):
        """Record a successful request - gradually reduce backoff."""
        self._consecutive_errors = max(0, self._consecutive_errors - 1)
        if self._backoff_factor > 1.0:
            self._backoff_factor = max(1.0, self._backoff_factor * 0.8)

    def record_rate_limit(self, retry_after: Optional[int] = None):
        """Record a 429 response - apply exponential backoff."""
        self._consecutive_errors += 1
        if retry_after:
            backoff = retry_after
        else:
            backoff = min(self._backoff_factor * (2 ** self._consecutive_errors), self.max_backoff)
        self._blocked_until = time.monotonic() + backoff
        self._backoff_factor = min(self._backoff_factor * 1.5, 10.0)
        logger.warning(f"Rate limited (429): backing off for {backoff:.0f}s (consecutive errors: {self._consecutive_errors})")

    def record_server_error(self):
        """Record a 503 response - mild backoff."""
        self._consecutive_errors += 1
        backoff = min(5.0 * self._consecutive_errors, 60.0)
        self._blocked_until = time.monotonic() + backoff
        logger.warning(f"Server error (503): backing off for {backoff:.0f}s")


# Module-level singleton for CDX API rate limiting
_cdx_rate_limiter: Optional[AdaptiveRateLimiter] = None


def get_cdx_rate_limiter() -> AdaptiveRateLimiter:
    """Get or create the singleton CDX API rate limiter."""
    global _cdx_rate_limiter
    if _cdx_rate_limiter is None:
        _cdx_rate_limiter = AdaptiveRateLimiter(
            max_requests_per_minute=50,
            min_delay=1.0,
        )
    return _cdx_rate_limiter
