"""
Shared plumbing for archive.org traffic: Redis client, egress path and headers.

All web.archive.org traffic leaves through ONE identity (see ``archive_rate_limiter``):

* ``WAYBACK_EGRESS=direct`` (default): the host's own IP.
* ``WAYBACK_EGRESS=proxy``: the single proxy in ``WAYBACK_PROXY_URL``, a manual
  fallback (e.g. one Mullvad gateway). No rotation, no pool, no exit selection.

Requests identify themselves with ``WAYBACK_USER_AGENT``; no browser-like or
randomised headers are sent to archive.org.
"""
import asyncio
import logging
import socket
from typing import Dict, List, Optional
from urllib.parse import urlparse

from ..core.config import settings

logger = logging.getLogger(__name__)

# redis.asyncio connections are bound to the event loop they were created on and
# Celery runs each task in its own loop (run_async_in_sync), so clients are keyed
# per loop (and per decode mode: the CDX page cache stores compressed bytes).
_redis_by_loop: dict = {}


def get_redis(decode_responses: bool = True):
    """Shared per-event-loop Redis client (``settings.REDIS_URL``)."""
    import redis.asyncio as aioredis

    loop = asyncio.get_event_loop()
    for key, (stored_loop, _client) in list(_redis_by_loop.items()):
        if stored_loop.is_closed():
            _redis_by_loop.pop(key, None)
    key = (id(loop), decode_responses)
    entry = _redis_by_loop.get(key)
    if entry is None:
        client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=decode_responses,
            socket_connect_timeout=2,
            socket_timeout=5,
        )
        _redis_by_loop[key] = (loop, client)
        return client
    return entry[1]


def wayback_proxy_url() -> Optional[str]:
    """Proxy URL for web.archive.org requests, or None to go out from the host IP."""
    mode = (settings.WAYBACK_EGRESS or "direct").strip().lower()
    if mode == "proxy":
        return settings.WAYBACK_PROXY_URL
    return None


def wayback_headers() -> Dict[str, str]:
    """Headers for web.archive.org requests: just the identifying User-Agent."""
    return {"User-Agent": settings.WAYBACK_USER_AGENT}


def wayback_client_kwargs() -> Dict[str, object]:
    """httpx.AsyncClient kwargs (headers + optional proxy) for one Wayback request."""
    kwargs: Dict[str, object] = {"headers": wayback_headers()}
    proxy = wayback_proxy_url()
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs


def _resolve_ips(host: str) -> List[str]:
    """Resolve a service name to all A records (all replicas)."""
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
        return sorted({info[4][0] for info in infos})
    except Exception as exc:
        logger.warning(f"egress: could not resolve {host}: {exc}")
        return []


async def flaresolverr_base_urls() -> List[str]:
    """
    Resolve the (possibly scaled) flaresolverr service to one base URL per
    replica. Falls back to the configured URL if resolution yields nothing.
    """
    configured = settings.FLARESOLVERR_URL.rstrip("/")
    parsed = urlparse(configured)
    host = parsed.hostname or "flaresolverr"
    port = parsed.port or 8191
    scheme = parsed.scheme or "http"
    ips = await asyncio.get_event_loop().run_in_executor(None, _resolve_ips, host)
    if not ips:
        return [configured]
    return [f"{scheme}://{ip}:{port}" for ip in ips]
