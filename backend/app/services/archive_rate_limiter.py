"""
One global, Redis-backed limiter for ALL web.archive.org traffic (CDX + content),
shared by every worker process.

Internet Archive asks for an average of about 60 requests/min and firewalls IPs
that keep going after 429s (connection refused for 1h, doubling on repeat). So
every Wayback request, whatever it is for, goes through this one identity:

* A single token bucket. A CDX query costs WAYBACK_CDX_REQUEST_COST tokens (it is far
  heavier for archive.org than a capture fetch); the bucket may go into debt for it,
  so bursts stay at two requests while the average rate stays honest. AIMD: starts at WAYBACK_GLOBAL_RATE_PER_MIN, +1 req/min per
  WAYBACK_AIMD_SUCCESS_STEP successes (cap WAYBACK_GLOBAL_MAX_RATE_PER_MIN), x0.5 on
  429/503 (floor WAYBACK_MIN_RATE_PER_MIN).
* A global in-flight cap (WAYBACK_MAX_INFLIGHT) held as leases in a Redis sorted set;
  leases expire, so a crashed worker cannot leak slots.
* A global pause. A 429/503 pauses ALL Wayback traffic for max(Retry-After,
  WAYBACK_MIN_PAUSE_SECONDS doubled per consecutive 429/503, capped at
  WAYBACK_FIREWALL_PAUSE_SECONDS). A refused/reset connection shortly after a
  429/503 means archive.org firewalled the egress IP: pause
  WAYBACK_FIREWALL_PAUSE_SECONDS, doubling on repeat (cap
  WAYBACK_FIREWALL_PAUSE_MAX_SECONDS), and log an ERROR.

``acquire`` waits (bounded by WAYBACK_ACQUIRE_TIMEOUT) for tokens, a slot or the end
of a pause. If that does not work out it raises ArchiveDeferred: NO request was sent,
so callers must re-queue without counting an attempt.

Common Crawl traffic is deliberately NOT paced here.

Usage (async)::

    async with limiter.slot("content") as lease:
        resp = await client.get(url)
        await lease.success()          # or lease.rate_limited(retry_after) / lease.connection_failed(exc)

Redis keys (prefix ``arl`` by default):

  arl:bucket      HASH tokens, ts(ms), rate(req/min), succ     TTL 24h
  arl:inflight    ZSET lease_id -> expiry(ms)                  TTL lease+60s
  arl:pause       pause marker (value = reason); TTL = remaining pause
  arl:streak      consecutive 429/503 without a success; TTL WAYBACK_RECENT_429_SECONDS
  arl:throttled   "recent 429/503" marker; TTL WAYBACK_RECENT_429_SECONDS
  arl:fwcount     firewall-pause escalation counter; TTL 24h
  arl:fwlatch     one escalation per firewall incident: concurrent in-flight failures
                  share it; TTL WAYBACK_FIREWALL_INCIDENT_SECONDS
"""
import asyncio
import logging
import random
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import AsyncIterator, Callable, Dict, Optional

import httpx

from ..core.config import settings
from . import egress_rotation as egress
from .archive_fetch_errors import ArchiveDeferred

logger = logging.getLogger(__name__)

_BUCKET_CAPACITY = 2.0  # burst: at most two back-to-back requests after idling
_FIREWALL_COUNT_TTL = 86400  # firewall escalation resets after 24h without one

_ACQUIRE_LUA = """
local now = tonumber(ARGV[1])
local pttl = redis.call('PTTL', KEYS[1])
if pttl > 0 then return {-1, pttl} end
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', now)
if redis.call('ZCARD', KEYS[2]) >= tonumber(ARGV[4]) then return {0, 250} end
local cap = tonumber(ARGV[6])
local rate = tonumber(redis.call('HGET', KEYS[3], 'rate') or ARGV[5])
local tokens = tonumber(redis.call('HGET', KEYS[3], 'tokens') or ARGV[6])
local ts = tonumber(redis.call('HGET', KEYS[3], 'ts') or ARGV[1])
if now < ts then ts = now end
tokens = math.min(cap, tokens + (now - ts) * rate / 60000)
if tokens >= 1 then
  -- a weighted request (CDX) may push the bucket into debt: later requests wait it off
  tokens = tokens - tonumber(ARGV[7])
  redis.call('HSET', KEYS[3], 'tokens', tostring(tokens), 'ts', ARGV[1], 'rate', tostring(rate))
  redis.call('PEXPIRE', KEYS[3], 86400000)
  redis.call('ZADD', KEYS[2], now + tonumber(ARGV[3]), ARGV[2])
  redis.call('PEXPIRE', KEYS[2], tonumber(ARGV[3]) + 60000)
  return {1, 0}
end
redis.call('HSET', KEYS[3], 'tokens', tostring(tokens), 'ts', ARGV[1], 'rate', tostring(rate))
redis.call('PEXPIRE', KEYS[3], 86400000)
return {0, math.ceil((1 - tokens) * 60000 / rate)}
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


def request_cost(purpose: str) -> float:
    """Tokens one request of ``purpose`` takes from the global bucket."""
    if purpose == "cdx":
        return max(1.0, float(settings.WAYBACK_CDX_REQUEST_COST))
    return 1.0


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


@dataclass
class Lease:
    """A granted request slot. Report the outcome, then release it."""

    purpose: str
    lease_id: str
    started: float
    _limiter: "ArchiveRateLimiter"

    @property
    def elapsed(self) -> float:
        """Seconds since the slot was granted (use as the fetch duration)."""
        return time.monotonic() - self.started

    async def success(self) -> None:
        await self._limiter.record_success()

    async def rate_limited(self, retry_after: Optional[float] = None) -> float:
        """Report 429/503. Returns the pause now in force (seconds)."""
        return await self._limiter.record_rate_limited(retry_after, self.purpose)

    async def connection_failed(self, exc: BaseException) -> str:
        """Report a connect/read failure. Returns 'blocked', 'proxy_down' or 'transient'."""
        return await self._limiter.record_connection_failure(exc, self.purpose)


class ArchiveRateLimiter:
    def __init__(self, prefix: str = "arl", clock: Callable[[], float] = time.time):
        self.prefix = prefix
        self._clock = clock

    # ------------------------------------------------------------------ keys
    def _key(self, name: str) -> str:
        return f"{self.prefix}:{name}"

    def _now_ms(self) -> int:
        return int(self._clock() * 1000)

    # --------------------------------------------------------------- acquire
    async def _try_acquire(self, lease_id: str, cost: float = 1.0):
        r = egress.get_redis()
        script = r.register_script(_ACQUIRE_LUA)
        res = await script(
            keys=[self._key("pause"), self._key("inflight"), self._key("bucket")],
            args=[
                self._now_ms(),
                lease_id,
                int(float(settings.WAYBACK_INFLIGHT_LEASE_SECONDS) * 1000),
                int(settings.WAYBACK_MAX_INFLIGHT),
                float(settings.WAYBACK_GLOBAL_RATE_PER_MIN),
                _BUCKET_CAPACITY,
                cost,
            ],
        )
        return int(res[0]), int(res[1])

    async def acquire(self, purpose: str = "wayback", *, timeout: Optional[float] = None) -> Lease:
        """
        Take a slot in the global Wayback budget. Waits (bounded by ``timeout``,
        default WAYBACK_ACQUIRE_TIMEOUT) for a token, an in-flight slot or the end of
        a pause. Raises ArchiveDeferred (with retry_after) when that does not work
        out in time, including when a pause outlasts the budget (no point waiting).
        Fails closed with ArchiveDeferred when Redis is unavailable.
        """
        budget = float(settings.WAYBACK_ACQUIRE_TIMEOUT if timeout is None else timeout)
        deadline = time.monotonic() + budget
        lease_id = uuid.uuid4().hex
        cost = request_cost(purpose)

        while True:
            try:
                status, wait_ms = await self._try_acquire(lease_id, cost)
            except Exception as exc:
                # Without shared state we cannot keep archive.org's per-IP limit.
                logger.error(f"archive_rate_limiter: Redis unavailable, deferring {purpose} request: {exc}")
                raise ArchiveDeferred(f"rate limiter unavailable: {exc}", retry_after=30.0) from exc
            if status == 1:
                return Lease(purpose, lease_id, time.monotonic(), self)

            wait_s = wait_ms / 1000.0
            what = "Wayback paused" if status == -1 else "no Wayback capacity"
            if time.monotonic() + wait_s > deadline:
                logger.info(
                    f"archive_rate_limiter: {what} for {purpose} request, deferring "
                    f"(retry in {wait_s:.0f}s, wait budget {budget:.0f}s)"
                )
                raise ArchiveDeferred(f"{what} for {purpose} (retry in {wait_s:.0f}s)", retry_after=wait_s)
            await asyncio.sleep(wait_s + random.uniform(0.0, 0.1))

    async def release(self, lease: Lease) -> None:
        try:
            await egress.get_redis().zrem(self._key("inflight"), lease.lease_id)
        except Exception as exc:
            logger.warning(f"archive_rate_limiter: could not release lease {lease.lease_id}: {exc}")

    @asynccontextmanager
    async def slot(self, purpose: str = "wayback", *, timeout: Optional[float] = None) -> AsyncIterator[Lease]:
        lease = await self.acquire(purpose, timeout=timeout)
        try:
            yield lease
        finally:
            await self.release(lease)

    # --------------------------------------------------------------- pausing
    async def pause(self, seconds: float, reason: str) -> float:
        """Pause ALL Wayback traffic for ``seconds`` (never shortens an existing pause)."""
        ms = max(1, int(seconds * 1000))
        r = egress.get_redis()
        key = self._key("pause")
        current = await r.pttl(key)
        if current is not None and current >= ms:
            return current / 1000.0
        await r.set(key, reason, px=ms)
        logger.warning(f"archive_rate_limiter: ALL Wayback traffic paused for {ms / 1000.0:.0f}s ({reason})")
        return ms / 1000.0

    async def pause_remaining(self) -> float:
        """Seconds left on the global pause (0 when not paused)."""
        pttl = await egress.get_redis().pttl(self._key("pause"))
        return pttl / 1000.0 if pttl is not None and pttl > 0 else 0.0

    # --------------------------------------------------------------- outcomes
    async def _report(self, kind: str) -> float:
        r = egress.get_redis()
        script = r.register_script(_REPORT_LUA)
        rate = await script(
            keys=[self._key("bucket")],
            args=[
                kind,
                int(settings.WAYBACK_AIMD_SUCCESS_STEP),
                float(settings.WAYBACK_GLOBAL_MAX_RATE_PER_MIN),
                float(settings.WAYBACK_MIN_RATE_PER_MIN),
                float(settings.WAYBACK_GLOBAL_RATE_PER_MIN),
                self._now_ms(),
            ],
        )
        return float(rate)

    async def record_success(self) -> None:
        before = await self.current_rate()
        after = await self._report("ok")
        await egress.get_redis().delete(self._key("streak"))
        if after > before:
            logger.info(f"archive_rate_limiter: rate {before:.0f} -> {after:.0f}/min (additive increase)")

    async def record_rate_limited(self, retry_after: Optional[float] = None, purpose: str = "wayback") -> float:
        """
        429/503 from archive.org: halve the rate and pause everything for
        max(Retry-After, 60s doubled per consecutive 429/503, capped at 1h).
        An explicit Retry-After is honoured, up to WAYBACK_FIREWALL_PAUSE_MAX_SECONDS.
        """
        r = egress.get_redis()
        already_paused = await self.pause_remaining() > 0
        new_rate = await self._report("limited")
        window = int(settings.WAYBACK_RECENT_429_SECONDS)
        await r.set(self._key("throttled"), "1", ex=window)
        if already_paused:
            # A request that was already in flight when the pause began: same incident,
            # do not escalate the pause for it.
            streak = max(1, int(await r.get(self._key("streak")) or 1))
        else:
            streak = int(await r.incr(self._key("streak")))
        await r.expire(self._key("streak"), window)
        escalated = min(
            float(settings.WAYBACK_MIN_PAUSE_SECONDS) * (2 ** (streak - 1)),
            float(settings.WAYBACK_FIREWALL_PAUSE_SECONDS),
        )
        explicit = min(float(retry_after or 0.0), float(settings.WAYBACK_FIREWALL_PAUSE_MAX_SECONDS))
        pause_s = await self.pause(
            max(explicit, escalated), f"{purpose} 429/503 #{streak} (Retry-After={retry_after})"
        )
        logger.warning(
            f"archive_rate_limiter: rate-limited on {purpose} (#{streak} in a row): "
            f"rate -> {new_rate:.1f}/min, Wayback paused {pause_s:.0f}s (Retry-After={retry_after})"
        )
        return pause_s

    async def record_connection_failure(self, exc: BaseException, purpose: str = "wayback") -> str:
        """
        Classify a connect/read failure and apply the matching state:

        * proxy mode, cannot connect to the proxy itself -> 'proxy_down': short pause
        * refused/reset/unreachable after a recent 429/503 -> 'blocked': archive.org
          firewalled this egress IP; pause 1h, doubling on repeat (cap 8h), ERROR log
        * read/write/pool timeout                         -> 'transient': nothing changes
          (a slow capture is not a block)
        * anything else without a recent 429/503          -> 'transient': short pause
        """
        r = egress.get_redis()
        short = float(settings.WAYBACK_MIN_PAUSE_SECONDS)
        if egress.wayback_proxy_url() and isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            logger.error(
                f"archive_rate_limiter: cannot reach the Wayback proxy ({type(exc).__name__}); "
                f"check WAYBACK_PROXY_URL"
            )
            await self.pause(short, f"proxy unreachable ({type(exc).__name__})")
            return "proxy_down"
        if await r.exists(self._key("throttled")):
            incident = max(1, int(float(settings.WAYBACK_FIREWALL_INCIDENT_SECONDS)))
            if not await r.set(self._key("fwlatch"), "1", nx=True, ex=incident):
                # Another request in flight at the same moment already escalated this
                # incident; one block is one escalation, not one per request.
                logger.warning(
                    f"archive_rate_limiter: {type(exc).__name__} on {purpose} request during a firewall "
                    f"block already being handled; not escalating (pause {await self.pause_remaining():.0f}s left)"
                )
                return "blocked"
            count = int(await r.incr(self._key("fwcount")))
            await r.expire(self._key("fwcount"), _FIREWALL_COUNT_TTL)
            seconds = min(
                float(settings.WAYBACK_FIREWALL_PAUSE_SECONDS) * (2 ** (count - 1)),
                float(settings.WAYBACK_FIREWALL_PAUSE_MAX_SECONDS),
            )
            paused = await self.pause(seconds, f"firewall block #{count} (refused/reset after 429)")
            logger.error(
                f"archive_rate_limiter: Internet Archive has FIREWALLED this egress IP "
                f"({type(exc).__name__} on {purpose} request after a recent 429/503, block #{count}); "
                f"ALL Wayback traffic paused {paused:.0f}s"
            )
            return "blocked"
        if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
            return "transient"
        await self.pause(short, f"transient {type(exc).__name__}")
        return "transient"

    # ------------------------------------------------------------ inspection
    async def current_rate(self) -> float:
        raw = await egress.get_redis().hget(self._key("bucket"), "rate")
        return float(raw) if raw is not None else float(settings.WAYBACK_GLOBAL_RATE_PER_MIN)

    async def snapshot(self) -> Dict[str, object]:
        """Limiter state for logs and smoke tests."""
        r = egress.get_redis()
        bucket = await r.hgetall(self._key("bucket"))
        return {
            "rate_per_min": float(bucket["rate"]) if "rate" in bucket else float(settings.WAYBACK_GLOBAL_RATE_PER_MIN),
            "tokens": round(float(bucket["tokens"]), 2) if "tokens" in bucket else None,
            "successes_since_step": int(bucket.get("succ", 0)),
            "inflight": int(await r.zcard(self._key("inflight"))),
            "paused_for_s": round(await self.pause_remaining(), 1),
            "pause_reason": await r.get(self._key("pause")),
            "throttle_streak": int(await r.get(self._key("streak")) or 0),
            "firewall_blocks": int(await r.get(self._key("fwcount")) or 0),
        }


_limiter: Optional[ArchiveRateLimiter] = None


def get_archive_rate_limiter() -> ArchiveRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = ArchiveRateLimiter()
    return _limiter
