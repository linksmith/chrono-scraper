"""
Egress exit selection and exit-health state.

When EGRESS_PROVIDER=mullvad, the wg-gateway compose service is scaled to a pool
of replicas, each bringing up a *different* Mullvad exit (tinyproxy on :8888).
Docker's embedded DNS returns every replica's IP for the ``wg-gateway`` name.

archive.org blocks per IP (rate limit; ignored 429s become a 1h firewall block),
so the strategy is a *few paced exits*, not rotate-on-block:

* ``select_exits()`` returns a deterministic, stable set of up to
  ``EGRESS_MAX_EXITS`` healthy exits (pool ordered by sha1 of the exit id; dead or
  long-parked exits are replaced by the next pool member). Optionally the host's
  own IP is added (``EGRESS_INCLUDE_DIRECT``).
* Pacing (token bucket, AIMD, in-flight cap) lives in ``archive_rate_limiter``,
  which picks the least-loaded exit with capacity. Nothing here "rotates after a
  block"; a blocked exit is simply parked until it may be used again.

Exit state is shared through Redis by every process (API + each Celery fork).
Keys (``{id}`` is the exit id: the replica IP, ``decodo`` or ``direct``):

  egress:park:{id}       parked marker (value = reason); TTL = remaining park time
  egress:parkcount:{id}  firewall-park escalation counter (1h, 2h, 4h, ... cap); TTL 24h
  egress:throttled:{id}  "recent 429/503" marker; TTL WAYBACK_RECENT_429_SECONDS
  egress:throttlecount:{id}  consecutive 429/503 without a success in between (doubles the
                         park: 60s, 120s, ... capped at WAYBACK_FIREWALL_PARK_SECONDS); same TTL
  egress:dead:{id}       DEAD marker (no traffic passes); cleared when a probe passes
  egress:health:{id}     last probe passed; TTL EGRESS_HEALTH_TTL
  egress:probelock:{id}  NX lock so only one process probes an exit at a time

DEAD (tunnel down, proxy unreachable, probe to a neutral endpoint fails) is kept
strictly apart from BLOCKED (archive.org refuses or rate-limits an exit whose
probe still passes): dead exits are excluded until a probe passes, blocked exits
stay in the set and are parked for the time archive.org asked for.
"""
import asyncio
import hashlib
import logging
import socket
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

PARK_KEY = "egress:park:{}"
PARKCOUNT_KEY = "egress:parkcount:{}"
THROTTLED_KEY = "egress:throttled:{}"
THROTTLECOUNT_KEY = "egress:throttlecount:{}"
DEAD_KEY = "egress:dead:{}"
HEALTH_KEY = "egress:health:{}"
PROBELOCK_KEY = "egress:probelock:{}"

_PARKCOUNT_TTL = 86400  # firewall escalation resets after 24h without a firewall park
_DEAD_SAFETY_TTL = 3600  # a dead marker that nobody rechecks still expires eventually
_PROBELOCK_TTL = 30
_DNS_CACHE_TTL = 20.0
_SELECTION_TTL = 10.0

DIRECT_EXIT_ID = "direct"


@dataclass(frozen=True)
class Exit:
    """One egress path. ``proxy_url`` None means the host's own IP."""

    id: str
    proxy_url: Optional[str]


_dns_cache: dict = {"ips": [], "at": 0.0}
_selection_cache: dict = {"exits": [], "at": 0.0, "key": None}

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


# --------------------------------------------------------------------------- pool

def _gateway_host_port() -> tuple[str, int]:
    parsed = urlparse(settings.WG_GATEWAY_HTTP)
    return (parsed.hostname or "wg-gateway"), (parsed.port or 8888)


def _resolve_ips(host: str) -> List[str]:
    """Resolve a service name to all A records (all pool replicas)."""
    try:
        infos = socket.getaddrinfo(host, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
        return sorted({info[4][0] for info in infos})
    except Exception as exc:
        logger.warning(f"egress: could not resolve {host}: {exc}")
        return []


def _stable_order_key(exit_id: str) -> str:
    return hashlib.sha1(exit_id.encode()).hexdigest()


def _decodo_proxy() -> Optional[str]:
    ps = settings.PROXY_SERVER
    if not ps:
        return None
    if settings.PROXY_USERNAME and settings.PROXY_PASSWORD:
        base = ps.replace("http://", "").replace("https://", "")
        return f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{base}"
    return ps if ps.startswith("http") else f"http://{ps}"


async def exit_pool() -> List[Exit]:
    """
    Every exit the configured provider offers, in a deterministic order that does
    not depend on health (so the selected set is stable between calls/processes).
    """
    provider = (settings.EGRESS_PROVIDER or "decodo").strip().lower()
    if provider == "none":
        return [Exit(DIRECT_EXIT_ID, None)]
    if provider != "mullvad":
        proxy = _decodo_proxy()
        return [Exit("decodo", proxy)] if proxy else [Exit(DIRECT_EXIT_ID, None)]

    host, port = _gateway_host_port()
    now = time.monotonic()
    if _dns_cache["ips"] and (now - _dns_cache["at"]) < _DNS_CACHE_TTL:
        ips = _dns_cache["ips"]
    else:
        ips = await asyncio.get_event_loop().run_in_executor(None, _resolve_ips, host)
        if ips:
            _dns_cache["ips"] = ips
            _dns_cache["at"] = now
        else:
            ips = _dns_cache["ips"]  # last known good, if any
    if not ips:
        # Pool not resolvable — use the service name directly (single gateway).
        return [Exit(host, f"http://{host}:{port}")]
    return [Exit(ip, f"http://{ip}:{port}") for ip in sorted(ips, key=_stable_order_key)]


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


# ------------------------------------------------------------------------- health

async def probe_exit(exit_: Exit) -> bool:
    """
    True if traffic passes through the exit. Probes a neutral endpoint (never
    archive.org) so an exit that archive.org has blocked still counts as alive.
    """
    urls = [u.strip() for u in settings.EGRESS_PROBE_URLS.split(",") if u.strip()]
    timeout = httpx.Timeout(settings.EGRESS_PROBE_TIMEOUT)
    kwargs = {"proxy": exit_.proxy_url} if exit_.proxy_url else {}
    try:
        async with httpx.AsyncClient(timeout=timeout, **kwargs) as client:
            for url in urls:
                try:
                    resp = await client.get(url)
                except httpx.HTTPError:
                    continue
                if resp.status_code == 200:
                    return True
    except Exception as exc:
        logger.debug(f"egress: probe client error for exit {exit_.id}: {exc}")
    return False


def invalidate_selection() -> None:
    _selection_cache["at"] = 0.0


async def mark_exit_dead(exit_id: str, reason: str) -> None:
    """Exclude an exit until a health probe passes again."""
    r = get_redis()
    await r.set(DEAD_KEY.format(exit_id), reason, ex=_DEAD_SAFETY_TTL)
    await r.delete(HEALTH_KEY.format(exit_id))
    # Hold the probe lock so the next recheck happens after EGRESS_DEAD_RECHECK_SECONDS.
    await r.set(PROBELOCK_KEY.format(exit_id), "1", ex=int(settings.EGRESS_DEAD_RECHECK_SECONDS))
    invalidate_selection()
    logger.warning(f"egress: exit {exit_id} marked DEAD ({reason}); excluded until a probe passes")


async def _check_candidate(r, exit_: Exit, dead: bool, health: bool) -> bool:
    """Decide whether a pool member is usable, probing when its state is unknown."""
    if dead:
        # Re-probe at most once per EGRESS_DEAD_RECHECK_SECONDS across all processes.
        if not await r.set(PROBELOCK_KEY.format(exit_.id), "1", nx=True, ex=int(settings.EGRESS_DEAD_RECHECK_SECONDS)):
            return False
        if await probe_exit(exit_):
            await r.delete(DEAD_KEY.format(exit_.id))
            await r.set(HEALTH_KEY.format(exit_.id), "1", ex=int(settings.EGRESS_HEALTH_TTL))
            logger.info(f"egress: exit {exit_.id} passed its health probe again; back in the pool")
            return True
        return False
    if health:
        return True
    # Unknown health: one process probes, the others optimistically assume healthy.
    if not await r.set(PROBELOCK_KEY.format(exit_.id), "1", nx=True, ex=_PROBELOCK_TTL):
        return True
    if await probe_exit(exit_):
        await r.set(HEALTH_KEY.format(exit_.id), "1", ex=int(settings.EGRESS_HEALTH_TTL))
        return True
    await mark_exit_dead(exit_.id, "health probe failed")
    return False


async def select_exits(max_exits: Optional[int] = None) -> List[Exit]:
    """
    Up to ``max_exits`` (default EGRESS_MAX_EXITS) healthy exits, stable between
    calls: pool order is fixed, so the same exits come back until one dies or is
    parked long enough (EGRESS_REPLACE_PARK_SECONDS) to be swapped for a spare.
    Result is cached in-process for a few seconds; pacing state is checked by the
    limiter on every request regardless.
    """
    limit = max(1, int(max_exits or settings.EGRESS_MAX_EXITS))
    cache_key = (limit, bool(settings.EGRESS_INCLUDE_DIRECT), settings.EGRESS_PROVIDER)
    now = time.monotonic()
    if (
        _selection_cache["exits"]
        and _selection_cache["key"] == cache_key
        and (now - _selection_cache["at"]) < _SELECTION_TTL
    ):
        return list(_selection_cache["exits"])

    pool = await exit_pool()
    chosen: List[Exit] = []
    if (settings.EGRESS_PROVIDER or "decodo").strip().lower() != "mullvad":
        chosen = list(pool)  # single decodo/direct path: no pool to choose from
    else:
        r = get_redis()
        pipe = r.pipeline()
        for e in pool:
            pipe.exists(DEAD_KEY.format(e.id))
            pipe.exists(HEALTH_KEY.format(e.id))
            pipe.pttl(PARK_KEY.format(e.id))
        flat = await pipe.execute()
        replace_ms = float(settings.EGRESS_REPLACE_PARK_SECONDS) * 1000.0
        candidates = []
        for i, e in enumerate(pool):
            dead, health, park_ms = bool(flat[3 * i]), bool(flat[3 * i + 1]), flat[3 * i + 2]
            if park_ms is not None and park_ms > replace_ms:
                continue  # parked for a long time: a spare takes its place meanwhile
            candidates.append((e, dead, health))

        idx = 0
        while len(chosen) < limit and idx < len(candidates):
            batch = candidates[idx : idx + (limit - len(chosen))]
            idx += len(batch)
            verdicts = await asyncio.gather(*(_check_candidate(r, e, d, h) for e, d, h in batch))
            chosen.extend(e for (e, _d, _h), ok in zip(batch, verdicts) if ok)

    if settings.EGRESS_INCLUDE_DIRECT and all(e.id != DIRECT_EXIT_ID for e in chosen):
        chosen.append(Exit(DIRECT_EXIT_ID, None))

    if not chosen:
        logger.error("egress: no healthy exits available")
    elif [e.id for e in chosen] != [e.id for e in _selection_cache["exits"]]:
        logger.info(f"egress: selected exits {[e.id for e in chosen]} (pool of {len(pool)})")

    _selection_cache.update({"exits": list(chosen), "at": now, "key": cache_key})
    return chosen


# --------------------------------------------------------------- parking / blocked

async def park_exit(exit_id: str, seconds: float, reason: str) -> float:
    """
    Stop using an exit for ``seconds`` (never shortens an existing park).
    Returns the park time now in force, in seconds.
    """
    ms = max(1, int(seconds * 1000))
    r = get_redis()
    key = PARK_KEY.format(exit_id)
    current = await r.pttl(key)
    if current is not None and current >= ms:
        return current / 1000.0
    await r.set(key, reason, px=ms)
    logger.info(f"egress: exit {exit_id} parked for {ms / 1000.0:.0f}s ({reason})")
    return ms / 1000.0


async def park_remaining(exit_ids: List[str]) -> Dict[str, float]:
    """Seconds left on each exit's park (0 when not parked)."""
    if not exit_ids:
        return {}
    r = get_redis()
    pipe = r.pipeline()
    for eid in exit_ids:
        pipe.pttl(PARK_KEY.format(eid))
    values = await pipe.execute()
    return {eid: (v / 1000.0 if v is not None and v > 0 else 0.0) for eid, v in zip(exit_ids, values)}


async def note_throttled(exit_id: str) -> int:
    """
    Remember that archive.org just 429/503'd this exit. Returns the number of
    consecutive throttles on it (no success in between), which escalates the park.
    """
    r = get_redis()
    window = int(settings.WAYBACK_RECENT_429_SECONDS)
    await r.set(THROTTLED_KEY.format(exit_id), "1", ex=window)
    streak = int(await r.incr(THROTTLECOUNT_KEY.format(exit_id)))
    await r.expire(THROTTLECOUNT_KEY.format(exit_id), window)
    return streak


async def clear_throttle_streak(exit_id: str) -> None:
    """A request succeeded on this exit: its 429 streak is over."""
    await get_redis().delete(THROTTLECOUNT_KEY.format(exit_id))


async def had_recent_throttle(exit_id: str) -> bool:
    return bool(await get_redis().exists(THROTTLED_KEY.format(exit_id)))


async def firewall_park(exit_id: str) -> float:
    """
    Park for the archive.org firewall block (connection refused/reset after a
    recent 429): WAYBACK_FIREWALL_PARK_SECONDS, doubling on each repeat, capped
    at WAYBACK_FIREWALL_PARK_MAX_SECONDS. Returns the park time in seconds.
    """
    r = get_redis()
    count = int(await r.incr(PARKCOUNT_KEY.format(exit_id)))
    await r.expire(PARKCOUNT_KEY.format(exit_id), _PARKCOUNT_TTL)
    seconds = min(
        float(settings.WAYBACK_FIREWALL_PARK_SECONDS) * (2 ** (count - 1)),
        float(settings.WAYBACK_FIREWALL_PARK_MAX_SECONDS),
    )
    return await park_exit(exit_id, seconds, f"firewall block #{count} (refused/reset after 429)")


async def exit_states(exit_ids: List[str]) -> Dict[str, dict]:
    """Diagnostic snapshot of park/dead/health state for the given exits."""
    r = get_redis()
    pipe = r.pipeline()
    for eid in exit_ids:
        pipe.pttl(PARK_KEY.format(eid))
        pipe.get(PARK_KEY.format(eid))
        pipe.exists(DEAD_KEY.format(eid))
        pipe.exists(HEALTH_KEY.format(eid))
        pipe.get(PARKCOUNT_KEY.format(eid))
    flat = await pipe.execute()
    out: Dict[str, dict] = {}
    for i, eid in enumerate(exit_ids):
        pttl, reason, dead, health, count = flat[5 * i : 5 * i + 5]
        out[eid] = {
            "parked_for_s": round(pttl / 1000.0, 1) if pttl and pttl > 0 else 0.0,
            "park_reason": reason,
            "dead": bool(dead),
            "healthy": bool(health),
            "firewall_parks": int(count or 0),
        }
    return out
