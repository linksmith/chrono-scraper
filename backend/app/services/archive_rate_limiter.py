"""
Redis-backed pacing for archive.org traffic, shared by every worker process.

One token bucket per (host class, exit) so each egress IP stays under what
archive.org tolerates (~60 req/min average per IP; ignoring 429s for more than
about a minute gets the IP firewalled for 1h, doubling on repeat):

* AIMD per bucket: starts at WAYBACK_CDX_RATE_PER_MIN / WAYBACK_CONTENT_RATE_PER_MIN,
  +1 req/min per WAYBACK_AIMD_SUCCESS_STEP successes (cap WAYBACK_MAX_RATE_PER_MIN),
  x0.5 on 429/503 (floor WAYBACK_MIN_RATE_PER_MIN).
* A per-exit in-flight cap (WAYBACK_MAX_INFLIGHT_PER_EXIT) held as leases in a
  Redis sorted set; leases expire, so a crashed worker cannot leak slots.
* A 429/503 parks the exit (all host classes: archive.org limits per IP) for
  max(Retry-After, WAYBACK_MIN_PARK_SECONDS); the park is checked atomically
  before every request. Park/dead state lives in ``egress_rotation``.

Common Crawl traffic is deliberately NOT paced here.

Usage (async)::

    async with limiter.slot(HostClass.WAYBACK_CONTENT) as lease:   # exits default to select_exits()
        resp = await client_for(lease.exit.proxy_url).get(url)
        await lease.success()          # or lease.rate_limited(retry_after) / lease.connection_failed(exc)

Redis keys (prefix ``arl`` by default; ``{hc}`` is the host class, ``{id}`` the exit id):

  arl:bucket:{hc}:{id}   HASH tokens, ts(ms), rate(req/min), succ   TTL 24h
  arl:inflight:{id}      ZSET lease_id -> expiry(ms)                 TTL lease+60s
"""
import asyncio
import logging
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Dict, Optional, Sequence

import httpx

from ..core.config import settings
from . import egress_rotation as egress
from .archive_fetch_errors import ArchiveConnectionError, ArchiveRateLimited
from .egress_rotation import Exit

logger = logging.getLogger(__name__)

_BUCKET_CAPACITY = 2.0  # burst: at most two back-to-back requests after idling

_ACQUIRE_LUA = """
local now = tonumber(ARGV[1])
if redis.call('EXISTS', KEYS[1]) == 1 then return {-2, 0, 0} end
local pttl = redis.call('PTTL', KEYS[2])
if pttl > 0 then return {-1, pttl, 0} end
redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', now)
if redis.call('ZCARD', KEYS[3]) >= tonumber(ARGV[4]) then return {0, 250, 1} end
local cap = tonumber(ARGV[6])
local rate = tonumber(redis.call('HGET', KEYS[4], 'rate') or ARGV[5])
local tokens = tonumber(redis.call('HGET', KEYS[4], 'tokens') or ARGV[6])
local ts = tonumber(redis.call('HGET', KEYS[4], 'ts') or ARGV[1])
if now < ts then ts = now end
tokens = math.min(cap, tokens + (now - ts) * rate / 60000)
if tokens >= 1 then
  tokens = tokens - 1
  redis.call('HSET', KEYS[4], 'tokens', tostring(tokens), 'ts', ARGV[1], 'rate', tostring(rate))
  redis.call('PEXPIRE', KEYS[4], 86400000)
  redis.call('ZADD', KEYS[3], now + tonumber(ARGV[3]), ARGV[2])
  redis.call('PEXPIRE', KEYS[3], tonumber(ARGV[3]) + 60000)
  return {1, 0, 0}
end
redis.call('HSET', KEYS[4], 'tokens', tostring(tokens), 'ts', ARGV[1], 'rate', tostring(rate))
redis.call('PEXPIRE', KEYS[4], 86400000)
return {0, math.ceil((1 - tokens) * 60000 / rate), 0}
"""

_REPORT_LUA = """
local rate = tonumber(redis.call('HGET', KEYS[1], 'rate') or ARGV[5])
local succ = tonumber(redis.call('HGET', KEYS[1], 'succ') or '0')
if ARGV[1] == 'ok' then
  succ = succ + 1
  if succ >= tonumber(ARGV[2]) then
    rate = math.min(tonumber(ARGV[3]), rate + 1)
    succ = 0
  end
  redis.call('HSET', KEYS[1], 'rate', tostring(rate), 'succ', tostring(succ))
else
  rate = math.max(tonumber(ARGV[4]), rate * 0.5)
  redis.call('HSET', KEYS[1], 'rate', tostring(rate), 'succ', '0', 'tokens', '0', 'ts', ARGV[6])
end
redis.call('PEXPIRE', KEYS[1], 86400000)
return tostring(rate)
"""


class HostClass(str, Enum):
    WAYBACK_CDX = "wayback_cdx"
    WAYBACK_CONTENT = "wayback_content"


def parse_retry_after(value: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    """
    Parse a Retry-After header (delta-seconds or HTTP-date) into seconds from now.
    Returns None when absent or unparseable; never negative.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return max(0.0, (when - current).total_seconds())


def _start_rate(host_class: HostClass) -> float:
    if host_class is HostClass.WAYBACK_CDX:
        return float(settings.WAYBACK_CDX_RATE_PER_MIN)
    return float(settings.WAYBACK_CONTENT_RATE_PER_MIN)


@dataclass
class Lease:
    """A granted request slot on one exit. Report the outcome, then it is released."""

    exit: Exit
    host_class: HostClass
    lease_id: str
    started: float
    _limiter: "ArchiveRateLimiter"

    @property
    def elapsed(self) -> float:
        """Seconds since the slot was granted (use as the fetch duration)."""
        return time.monotonic() - self.started

    async def success(self) -> None:
        await self._limiter.record_success(self.exit, self.host_class)

    async def rate_limited(self, retry_after: Optional[float] = None) -> float:
        """Report 429/503. Returns the park time now in force (seconds)."""
        return await self._limiter.record_rate_limited(self.exit, self.host_class, retry_after)

    async def connection_failed(self, exc: BaseException) -> str:
        """Report a connect/read failure. Returns 'dead', 'blocked' or 'transient'."""
        return await self._limiter.record_connection_failure(self.exit, exc)


class ArchiveRateLimiter:
    def __init__(self, prefix: str = "arl", clock: Callable[[], float] = time.time):
        self.prefix = prefix
        self._clock = clock

    # ------------------------------------------------------------------ keys
    def _bucket_key(self, hc: HostClass, exit_id: str) -> str:
        return f"{self.prefix}:bucket:{hc.value}:{exit_id}"

    def _inflight_key(self, exit_id: str) -> str:
        return f"{self.prefix}:inflight:{exit_id}"

    def _now_ms(self) -> int:
        return int(self._clock() * 1000)

    # --------------------------------------------------------------- acquire
    async def _try_acquire(self, hc: HostClass, exit_: Exit, lease_id: str):
        r = egress.get_redis()
        script = r.register_script(_ACQUIRE_LUA)
        res = await script(
            keys=[
                egress.DEAD_KEY.format(exit_.id),
                egress.PARK_KEY.format(exit_.id),
                self._inflight_key(exit_.id),
                self._bucket_key(hc, exit_.id),
            ],
            args=[
                self._now_ms(),
                lease_id,
                int(float(settings.WAYBACK_INFLIGHT_LEASE_SECONDS) * 1000),
                int(settings.WAYBACK_MAX_INFLIGHT_PER_EXIT),
                _start_rate(hc),
                _BUCKET_CAPACITY,
            ],
        )
        return int(res[0]), int(res[1])

    async def _order_by_load(self, exits: Sequence[Exit]) -> list:
        r = egress.get_redis()
        pipe = r.pipeline()
        for e in exits:
            pipe.zcard(self._inflight_key(e.id))
        loads = await pipe.execute()
        jittered = sorted(zip(loads, (random.random() for _ in exits), range(len(exits))))
        return [exits[i] for _load, _jitter, i in jittered]

    async def acquire(
        self,
        host_class: HostClass,
        exits: Optional[Sequence[Exit]] = None,
        *,
        exclude: Sequence[str] = (),
        timeout: Optional[float] = None,
    ) -> Lease:
        """
        Take a slot on the least-loaded exit that has tokens and in-flight room.
        Waits (bounded by ``timeout``, default WAYBACK_ACQUIRE_TIMEOUT) for tokens;
        never waits out a park. Raises ArchiveRateLimited (with retry_after) when
        every usable exit is parked or capacity does not free up in time, and
        ArchiveConnectionError when no exit is usable at all.
        """
        if exits is None:
            exits = await egress.select_exits()
        excluded = set(exclude)
        usable = [e for e in exits if e.id not in excluded]
        if not usable:
            raise ArchiveConnectionError("no egress exit available for this request")
        budget = float(settings.WAYBACK_ACQUIRE_TIMEOUT if timeout is None else timeout)
        deadline = time.monotonic() + budget
        lease_id = uuid.uuid4().hex

        while True:
            try:
                ordered = await self._order_by_load(usable)
                soonest_ms: Optional[int] = None  # an exit that will have capacity shortly
                parked_ms: Optional[int] = None  # shortest park among parked exits
                for exit_ in ordered:
                    status, wait_ms = await self._try_acquire(host_class, exit_, lease_id)
                    if status == 1:
                        return Lease(exit_, host_class, lease_id, time.monotonic(), self)
                    if status == 0:
                        soonest_ms = wait_ms if soonest_ms is None else min(soonest_ms, wait_ms)
                    elif status == -1:
                        parked_ms = wait_ms if parked_ms is None else min(parked_ms, wait_ms)
            except Exception as exc:
                # Fail closed: without shared state we cannot keep archive.org's per-IP limit.
                logger.error(f"archive_rate_limiter: Redis unavailable, refusing request: {exc}")
                raise ArchiveRateLimited(
                    f"rate limiter unavailable: {exc}", retry_after=30.0
                ) from exc

            if soonest_ms is None:
                if parked_ms is not None:
                    raise ArchiveRateLimited(
                        f"all {len(usable)} exits parked for {host_class.value}",
                        retry_after=parked_ms / 1000.0,
                    )
                raise ArchiveConnectionError(
                    f"all {len(usable)} exits are dead for {host_class.value}"
                )
            if time.monotonic() + soonest_ms / 1000.0 > deadline:
                raise ArchiveRateLimited(
                    f"no {host_class.value} capacity within {budget:.0f}s",
                    retry_after=soonest_ms / 1000.0,
                )
            await asyncio.sleep(soonest_ms / 1000.0 + random.uniform(0.0, 0.1))

    async def release(self, lease: Lease) -> None:
        try:
            await egress.get_redis().zrem(self._inflight_key(lease.exit.id), lease.lease_id)
        except Exception as exc:
            logger.warning(f"archive_rate_limiter: could not release lease on {lease.exit.id}: {exc}")

    @asynccontextmanager
    async def slot(
        self,
        host_class: HostClass,
        exits: Optional[Sequence[Exit]] = None,
        *,
        exclude: Sequence[str] = (),
        timeout: Optional[float] = None,
    ) -> AsyncIterator[Lease]:
        lease = await self.acquire(host_class, exits, exclude=exclude, timeout=timeout)
        try:
            yield lease
        finally:
            await self.release(lease)

    # --------------------------------------------------------------- outcomes
    async def _report(self, kind: str, hc: HostClass, exit_id: str) -> float:
        r = egress.get_redis()
        script = r.register_script(_REPORT_LUA)
        rate = await script(
            keys=[self._bucket_key(hc, exit_id)],
            args=[
                kind,
                int(settings.WAYBACK_AIMD_SUCCESS_STEP),
                float(settings.WAYBACK_MAX_RATE_PER_MIN),
                float(settings.WAYBACK_MIN_RATE_PER_MIN),
                _start_rate(hc),
                self._now_ms(),
            ],
        )
        return float(rate)

    async def record_success(self, exit_: Exit, hc: HostClass) -> None:
        before = await self.current_rate(exit_, hc)
        after = await self._report("ok", hc, exit_.id)
        await egress.clear_throttle_streak(exit_.id)
        if after > before:
            logger.info(
                f"archive_rate_limiter: exit={exit_.id} host_class={hc.value} "
                f"rate {before:.0f} -> {after:.0f}/min (additive increase)"
            )

    async def record_rate_limited(
        self, exit_: Exit, hc: HostClass, retry_after: Optional[float] = None
    ) -> float:
        new_rate = await self._report("limited", hc, exit_.id)
        streak = await egress.note_throttled(exit_.id)
        # max(Retry-After, 60s); consecutive 429s with no success in between double the
        # floor (an IP archive.org keeps throttling gets probed ever less often), capped
        # at the firewall park. An explicit longer Retry-After is always honoured.
        escalated = min(
            float(settings.WAYBACK_MIN_PARK_SECONDS) * (2 ** (streak - 1)),
            float(settings.WAYBACK_FIREWALL_PARK_SECONDS),
        )
        park_s = max(float(retry_after or 0.0), escalated)
        park_s = await egress.park_exit(
            exit_.id, park_s, f"{hc.value} 429/503 #{streak} (Retry-After={retry_after})"
        )
        logger.warning(
            f"archive_rate_limiter: exit={exit_.id} host_class={hc.value} rate-limited (#{streak} in a row): "
            f"rate -> {new_rate:.1f}/min, exit parked {park_s:.0f}s (Retry-After={retry_after})"
        )
        return park_s

    async def record_connection_failure(self, exit_: Exit, exc: BaseException) -> str:
        """
        Classify a connect/read failure and apply the matching state:

        * cannot connect to the exit's own proxy -> DEAD (excluded until a probe passes)
        * probe to a neutral endpoint fails      -> DEAD
        * probe passes, recent 429 on this exit  -> BLOCKED: firewall park (1h, doubling)
        * probe passes, no recent 429            -> transient: a read timeout changes nothing (a
          slow capture is not a bad exit); anything else parks the exit for
          WAYBACK_MIN_PARK_SECONDS

        A refused upstream surfaces through tinyproxy as a 502/closed tunnel
        (httpx.ProxyError / RemoteProtocolError), whereas httpx.ConnectError or
        ConnectTimeout with a proxy configured means the proxy itself is unreachable.
        """
        r = egress.get_redis()
        if exit_.proxy_url and isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            await egress.mark_exit_dead(exit_.id, f"proxy unreachable ({type(exc).__name__})")
            return "dead"
        probed_by_us = await r.set(egress.PROBELOCK_KEY.format(exit_.id), "1", nx=True, ex=30)
        if probed_by_us:
            if not await egress.probe_exit(exit_):
                await egress.mark_exit_dead(exit_.id, f"{type(exc).__name__} and probe failed")
                return "dead"
        elif await r.exists(egress.DEAD_KEY.format(exit_.id)):
            return "dead"
        if await egress.had_recent_throttle(exit_.id):
            seconds = await egress.firewall_park(exit_.id)
            logger.warning(
                f"archive_rate_limiter: exit={exit_.id} connection {type(exc).__name__} after a "
                f"recent 429: BLOCKED, parked {seconds:.0f}s"
            )
            return "blocked"
        if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
            return "transient"
        await egress.park_exit(
            exit_.id, float(settings.WAYBACK_MIN_PARK_SECONDS), f"transient {type(exc).__name__}"
        )
        return "transient"

    # ------------------------------------------------------------ inspection
    async def current_rate(self, exit_: Exit, hc: HostClass) -> float:
        raw = await egress.get_redis().hget(self._bucket_key(hc, exit_.id), "rate")
        return float(raw) if raw is not None else _start_rate(hc)

    async def snapshot(self, exits: Sequence[Exit]) -> Dict[str, dict]:
        """Limiter + park/dead state per exit, for logs and smoke tests."""
        r = egress.get_redis()
        states = await egress.exit_states([e.id for e in exits])
        out: Dict[str, dict] = {}
        for e in exits:
            entry = dict(states[e.id])
            entry["inflight"] = int(await r.zcard(self._inflight_key(e.id)))
            for hc in HostClass:
                bucket = await r.hgetall(self._bucket_key(hc, e.id))
                entry[hc.value] = {
                    "rate_per_min": float(bucket["rate"]) if "rate" in bucket else _start_rate(hc),
                    "tokens": round(float(bucket["tokens"]), 2) if "tokens" in bucket else None,
                    "successes_since_step": int(bucket.get("succ", 0)),
                }
            out[e.id] = entry
        return out


_limiter: Optional[ArchiveRateLimiter] = None


def get_archive_rate_limiter() -> ArchiveRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = ArchiveRateLimiter()
    return _limiter
