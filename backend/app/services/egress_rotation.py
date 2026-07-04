"""
Egress rotation.

When EGRESS_PROVIDER=mullvad, the wg-gateway compose service is scaled to a pool
of replicas, each bringing up a *different* random Mullvad exit. Docker's
embedded DNS returns every replica's IP for the `wg-gateway` service name, so we
can resolve the whole pool and hand a different exit to each request (and, on a
block, rotate to another). This is what lets a scrape spread its requests across
many exit IPs instead of hammering one and getting rate-limited.
"""
import asyncio
import logging
import random
import socket
import time
from typing import List, Optional
from urllib.parse import urlparse

from ..core.config import settings

logger = logging.getLogger(__name__)

# Cache the resolved replica IPs briefly so we don't hit DNS on every request.
_cache: dict = {"ips": [], "at": 0.0}
_CACHE_TTL = 20.0  # seconds


def _gateway_host_port() -> tuple[str, int]:
    parsed = urlparse(settings.WG_GATEWAY_HTTP)
    return (parsed.hostname or "wg-gateway"), (parsed.port or 8888)


def _resolve_ips(host: str) -> List[str]:
    """Resolve a service name to all A records (all pool replicas)."""
    try:
        # getaddrinfo returns one entry per replica IP for a scaled compose service.
        infos = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
        ips = sorted({info[4][0] for info in infos})
        return ips
    except Exception as exc:
        logger.warning(f"egress_rotation: could not resolve {host}: {exc}")
        return []


async def mullvad_proxy_pool() -> List[str]:
    """Return proxy URLs for every wg-gateway replica currently resolvable."""
    host, port = _gateway_host_port()
    now = time.monotonic()
    if _cache["ips"] and (now - _cache["at"]) < _CACHE_TTL:
        ips = _cache["ips"]
    else:
        # getaddrinfo is blocking; keep it off the event loop.
        ips = await asyncio.get_event_loop().run_in_executor(None, _resolve_ips, host)
        if ips:
            _cache["ips"] = ips
            _cache["at"] = now
        else:
            ips = _cache["ips"]  # fall back to last known good, if any
    if not ips:
        # No pool resolvable — use the service name directly (single gateway).
        return [f"http://{host}:{port}"]
    return [f"http://{ip}:{port}" for ip in ips]


def _decodo_proxy() -> Optional[str]:
    ps = settings.PROXY_SERVER
    if not ps:
        return None
    if settings.PROXY_USERNAME and settings.PROXY_PASSWORD:
        base = ps.replace("http://", "").replace("https://", "")
        return f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{base}"
    return ps if ps.startswith("http") else f"http://{ps}"


async def egress_proxy_candidates(max_candidates: int = 6) -> List[Optional[str]]:
    """
    Ordered proxy candidates to try for the current egress provider.

    - mullvad: a shuffled slice of the replica pool (rotate across exits)
    - decodo : the single Decodo proxy
    - none   : direct (no proxy)
    """
    provider = (settings.EGRESS_PROVIDER or "decodo").strip().lower()
    if provider == "mullvad":
        pool = await mullvad_proxy_pool()
        random.shuffle(pool)
        return pool[:max_candidates] if max_candidates else pool
    if provider == "none":
        return [None]
    return [_decodo_proxy()]
