"""
Stealth headers for web scraping - user agent rotation and matching browser headers.

Provides realistic browser fingerprints to avoid detection when scraping
Archive.org and Common Crawl CDX APIs.
"""
import random
import logging
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
