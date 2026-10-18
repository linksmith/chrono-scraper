"""
Egress rotation.

When EGRESS_PROVIDER=mullvad, the wg-gateway compose service is scaled to a pool
of replicas, each bringing up a *different* random Mullvad exit. Docker's
embedded DNS returns every replica's IP for the `wg-gateway` service name, so we
can resolve the whole pool and hand a different exit to each request (and, on a
block, rotate to another). This is what lets a scrape spread its requests across
many exit IPs instead of hammering one and getting rate-limited.

Exit-health bookkeeping lives in Redis so every process that fetches (the API
process and each forked Celery worker) shares one view of which exits are
parked and which were used least recently:

  egress:block:{proxy}      -> parked marker, expires after an adaptive cooldown
  egress:blockcount:{proxy} -> consecutive-block counter (drives the backoff)
  egress:lastused           -> ZSET of checkout times (drives LRU selection)

Million-page scrapes run several worker processes for hours; without shared
state each fork rediscovers blocked exits on its own and re-burns requests on
them. If Redis is unreachable the module degrades to per-process bookkeeping.
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

_BLOCK_KEY = "egress:block:{}"
_COUNT_KEY = "egress:blockcount:{}"
_LASTUSED_ZSET = "egress:lastused"
_COUNT_WINDOW = 3600  # consecutive-block counter resets after an hour of quiet

# In-process fallback state, used only when Redis is unavailable.
_blocked_until: dict = {}
_block_counts: dict = {}

# redis.asyncio connections are bound to the event loop they were created on,
# and Celery runs each task in its own loop (run_async_in_sync) — so clients
# are keyed per loop, like the FlareSolverr semaphore.
_redis_by_loop: dict = {}


def _get_redis():
    import redis.asyncio as aioredis

    loop = asyncio.get_event_loop()
    # Drop clients whose loop is gone so long-lived workers don't accumulate them.
    for key, (stored_loop, _client) in list(_redis_by_loop.items()):
        if stored_loop.is_closed():
            _redis_by_loop.pop(key, None)
    entry = _redis_by_loop.get(id(loop))
    if entry is None:
        client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_by_loop[id(loop)] = (loop, client)
        return client
    return entry[1]


def _cooldown_for(block_count: int) -> float:
    base = float(getattr(settings, "EGRESS_BLOCK_COOLDOWN_SECONDS", 90.0))
    cap = float(getattr(settings, "EGRESS_BLOCK_COOLDOWN_MAX_SECONDS", 1800.0))
    return min(base * (2 ** max(0, block_count - 1)), cap)


async def mark_exit_blocked(proxy_url: Optional[str]) -> None:
    """Park an exit that just returned a block/error, with exponential backoff."""
    if not proxy_url:
        return
    try:
        r = _get_redis()
        count = await r.incr(_COUNT_KEY.format(proxy_url))
        await r.expire(_COUNT_KEY.format(proxy_url), _COUNT_WINDOW)
        cooldown = _cooldown_for(int(count))
        await r.set(_BLOCK_KEY.format(proxy_url), "1", ex=int(cooldown))
        logger.info(f"egress: parked {proxy_url} for {int(cooldown)}s (block #{count})")
    except Exception as exc:
        # Redis down — fall back to per-process bookkeeping.
        _block_counts[proxy_url] = _block_counts.get(proxy_url, 0) + 1
        _blocked_until[proxy_url] = time.monotonic() + _cooldown_for(_block_counts[proxy_url])
        logger.debug(f"egress: Redis unavailable, parked {proxy_url} locally: {exc}")


async def mark_exit_ok(proxy_url: Optional[str]) -> None:
    """Reset an exit's block escalation after a successful fetch through it."""
    if not proxy_url:
        return
    try:
        r = _get_redis()
        await r.delete(_COUNT_KEY.format(proxy_url))
    except Exception:
        _block_counts.pop(proxy_url, None)


def _not_in_cooldown_local(proxy_url: Optional[str]) -> bool:
    until = _blocked_until.get(proxy_url)
    return until is None or time.monotonic() >= until


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


async def flaresolverr_base_urls() -> List[str]:
    """
    Resolve the (possibly scaled) flaresolverr service to one base URL per
    replica, so callers can round-robin across parallel browser instances.
    Falls back to the configured URL if resolution yields nothing.
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


def _decodo_proxy() -> Optional[str]:
    ps = settings.PROXY_SERVER
    if not ps:
        return None
    if settings.PROXY_USERNAME and settings.PROXY_PASSWORD:
        base = ps.replace("http://", "").replace("https://", "")
        return f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{base}"
    return ps if ps.startswith("http") else f"http://{ps}"


async def _order_mullvad_pool(pool: List[str]) -> List[str]:
    """
    Order the pool for the next request: fresh (non-parked) exits first, least
    recently used first, with a random tiebreak so concurrent workers don't all
    pile onto the same exit between checkout updates. Falls back to a local
    shuffle+cooldown if Redis is unavailable.
    """
    try:
        r = _get_redis()
        pipe = r.pipeline()
        pipe.zrange(_LASTUSED_ZSET, 0, -1)
        for p in pool:
            pipe.exists(_BLOCK_KEY.format(p))
        res = await pipe.execute()
        lru_order: List[str] = res[0] or []
        blocked = {p for p, flag in zip(pool, res[1:]) if flag}
        rank = {p: i for i, p in enumerate(lru_order)}
        fresh = [p for p in pool if p not in blocked]
        # Never-used exits (no rank) sort before rank 0; jitter breaks ties.
        ordered = sorted(fresh or pool, key=lambda p: (rank.get(p, -1), random.random()))
        if not fresh:
            logger.warning(
                f"egress: all {len(pool)} exits are parked; trying least-recently-used anyway"
            )
        return ordered
    except Exception as exc:
        logger.debug(f"egress: Redis unavailable, using local rotation: {exc}")
        shuffled = pool[:]
        random.shuffle(shuffled)
        fresh = [p for p in shuffled if _not_in_cooldown_local(p)]
        return fresh or shuffled


async def _touch_used(proxies: List[str]) -> None:
    """Record checkout time for the chosen exits (drives LRU selection)."""
    if not proxies:
        return
    try:
        r = _get_redis()
        now = time.time()
        await r.zadd(_LASTUSED_ZSET, {p: now for p in proxies})
    except Exception:
        pass


async def egress_proxy_candidates(max_candidates: int = 6) -> List[Optional[str]]:
    """
    Ordered proxy candidates to try for the current egress provider.

    - mullvad: fresh exits first, least-recently-used first (shared via Redis)
    - decodo : the single Decodo proxy
    - none   : direct (no proxy)
    """
    provider = (settings.EGRESS_PROVIDER or "decodo").strip().lower()
    if provider == "mullvad":
        pool = await mullvad_proxy_pool()
        ordered = await _order_mullvad_pool(pool)
        chosen = ordered[:max_candidates] if max_candidates else ordered
        await _touch_used(chosen)
        return chosen
    if provider == "none":
        return [None]
    return [_decodo_proxy()]
