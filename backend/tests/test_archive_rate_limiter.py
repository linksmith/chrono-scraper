"""
Tests for the Redis-backed archive limiter (token bucket, AIMD, parking,
dead-vs-blocked classification, in-flight leases) and exit selection.

Redis is fakeredis (with Lua, which the limiter's atomic scripts need).
"""
from datetime import datetime, timedelta, timezone

import fakeredis
import httpx
import pytest
import pytest_asyncio

from app.core.config import settings
from app.services import egress_rotation as egress
from app.services.archive_fetch_errors import ArchiveConnectionError, ArchiveRateLimited
from app.services.archive_rate_limiter import ArchiveRateLimiter, HostClass, parse_retry_after
from app.services.egress_rotation import Exit

EXIT_A = Exit("10.0.0.1", "http://10.0.0.1:8888")
EXIT_B = Exit("10.0.0.2", "http://10.0.0.2:8888")


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest_asyncio.fixture
async def redis_client(monkeypatch):
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(egress, "get_redis", lambda decode_responses=True: client)
    egress.invalidate_selection()
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def tuned(monkeypatch):
    values = {
        "WAYBACK_CONTENT_RATE_PER_MIN": 30.0,
        "WAYBACK_CDX_RATE_PER_MIN": 10.0,
        "WAYBACK_MAX_RATE_PER_MIN": 40.0,
        "WAYBACK_MIN_RATE_PER_MIN": 2.0,
        "WAYBACK_AIMD_SUCCESS_STEP": 3,
        "WAYBACK_MAX_INFLIGHT_PER_EXIT": 10,
        "WAYBACK_INFLIGHT_LEASE_SECONDS": 120.0,
        "WAYBACK_MIN_PARK_SECONDS": 60.0,
        "WAYBACK_FIREWALL_PARK_SECONDS": 3600.0,
        "WAYBACK_FIREWALL_PARK_MAX_SECONDS": 28800.0,
        "WAYBACK_RECENT_429_SECONDS": 1800.0,
        "WAYBACK_ACQUIRE_TIMEOUT": 0.2,
    }
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def limiter(redis_client, tuned, clock):
    return ArchiveRateLimiter(prefix="test", clock=clock)


@pytest.fixture
def probe(monkeypatch):
    """Control the health probe result: probe.result = True/False."""

    class Probe:
        result = True
        calls = 0

    state = Probe()

    async def fake_probe(exit_):
        state.calls += 1
        return state.result

    monkeypatch.setattr(egress, "probe_exit", fake_probe)
    return state


# ------------------------------------------------------------------ Retry-After


class TestParseRetryAfter:
    def test_seconds(self):
        assert parse_retry_after("120") == 120.0

    def test_fractional_seconds(self):
        assert parse_retry_after("1.5") == 1.5

    def test_http_date(self):
        now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)
        later = now + timedelta(seconds=90)
        header = later.strftime("%a, %d %b %Y %H:%M:%S GMT")
        assert parse_retry_after(header, now=now) == pytest.approx(90.0)

    def test_http_date_in_the_past_is_zero(self):
        now = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)
        assert parse_retry_after("Sun, 05 Jul 2026 11:00:00 GMT", now=now) == 0.0

    def test_negative_seconds_clamped(self):
        assert parse_retry_after("-5") == 0.0

    @pytest.mark.parametrize("value", [None, "", "   ", "soon", "Someday, 99 Foo 2026"])
    def test_unparseable_is_none(self, value):
        assert parse_retry_after(value) is None


# ------------------------------------------------------------------ token bucket


@pytest.mark.asyncio
async def test_token_bucket_burst_then_wait_then_refill(limiter, clock):
    # 30/min = one token per 2s, burst capacity 2.
    assert (await limiter._try_acquire(HostClass.WAYBACK_CONTENT, EXIT_A, "l1"))[0] == 1
    assert (await limiter._try_acquire(HostClass.WAYBACK_CONTENT, EXIT_A, "l2"))[0] == 1
    status, wait_ms = await limiter._try_acquire(HostClass.WAYBACK_CONTENT, EXIT_A, "l3")
    assert status == 0
    assert 1900 <= wait_ms <= 2100

    clock.advance(2.1)
    assert (await limiter._try_acquire(HostClass.WAYBACK_CONTENT, EXIT_A, "l3"))[0] == 1


@pytest.mark.asyncio
async def test_buckets_are_independent_per_host_class_and_exit(limiter):
    for i in range(2):
        await limiter._try_acquire(HostClass.WAYBACK_CONTENT, EXIT_A, f"a{i}")
    assert (await limiter._try_acquire(HostClass.WAYBACK_CONTENT, EXIT_A, "a2"))[0] == 0
    assert (await limiter._try_acquire(HostClass.WAYBACK_CDX, EXIT_A, "c0"))[0] == 1
    assert (await limiter._try_acquire(HostClass.WAYBACK_CONTENT, EXIT_B, "b0"))[0] == 1


@pytest.mark.asyncio
async def test_cdx_class_starts_at_its_own_rate(limiter):
    assert await limiter.current_rate(EXIT_A, HostClass.WAYBACK_CDX) == 10.0
    assert await limiter.current_rate(EXIT_A, HostClass.WAYBACK_CONTENT) == 30.0


# -------------------------------------------------------------------------- AIMD


@pytest.mark.asyncio
async def test_aimd_additive_increase_after_n_successes_capped(limiter):
    hc = HostClass.WAYBACK_CONTENT
    for _ in range(2):
        await limiter.record_success(EXIT_A, hc)
    assert await limiter.current_rate(EXIT_A, hc) == 30.0  # step is 3
    await limiter.record_success(EXIT_A, hc)
    assert await limiter.current_rate(EXIT_A, hc) == 31.0
    for _ in range(3 * 20):
        await limiter.record_success(EXIT_A, hc)
    assert await limiter.current_rate(EXIT_A, hc) == 40.0  # capped at WAYBACK_MAX_RATE_PER_MIN


@pytest.mark.asyncio
async def test_aimd_multiplicative_decrease_with_floor_and_streak_reset(limiter):
    hc = HostClass.WAYBACK_CONTENT
    await limiter.record_success(EXIT_A, hc)
    await limiter.record_success(EXIT_A, hc)
    await limiter.record_rate_limited(EXIT_A, hc, None)
    assert await limiter.current_rate(EXIT_A, hc) == 15.0
    # the success streak restarted: two more successes must not step up yet
    await limiter.record_success(EXIT_A, hc)
    await limiter.record_success(EXIT_A, hc)
    assert await limiter.current_rate(EXIT_A, hc) == 15.0
    for _ in range(6):
        await limiter.record_rate_limited(EXIT_A, hc, None)
    assert await limiter.current_rate(EXIT_A, hc) == 2.0  # floor


@pytest.mark.asyncio
async def test_decrease_empties_the_bucket(limiter):
    hc = HostClass.WAYBACK_CONTENT
    await limiter.record_rate_limited(EXIT_A, hc, None)
    await egress.get_redis().delete(egress.PARK_KEY.format(EXIT_A.id))  # isolate the bucket
    status, _ = await limiter._try_acquire(hc, EXIT_A, "x")
    assert status == 0


# ---------------------------------------------------------------- park / unpark


@pytest.mark.asyncio
async def test_rate_limited_parks_for_at_least_minimum(limiter):
    park = await limiter.record_rate_limited(EXIT_A, HostClass.WAYBACK_CONTENT, 5.0)
    assert park == 60.0


@pytest.mark.asyncio
async def test_rate_limited_parks_for_retry_after_when_longer(limiter):
    park = await limiter.record_rate_limited(EXIT_A, HostClass.WAYBACK_CONTENT, 300.0)
    assert park == 300.0
    remaining = (await egress.park_remaining([EXIT_A.id]))[EXIT_A.id]
    assert 298 <= remaining <= 300


@pytest.mark.asyncio
async def test_park_never_shortens(redis_client):
    await egress.park_exit("x", 100, "first")
    assert await egress.park_exit("x", 10, "shorter") >= 99


@pytest.mark.asyncio
async def test_parked_exit_is_skipped_and_all_parked_raises_with_retry_after(limiter):
    await limiter.record_rate_limited(EXIT_A, HostClass.WAYBACK_CONTENT, 120.0)

    # B still serves requests while A is parked
    lease = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A, EXIT_B])
    assert lease.exit.id == EXIT_B.id
    await limiter.release(lease)

    await limiter.record_rate_limited(EXIT_B, HostClass.WAYBACK_CONTENT, 90.0)
    with pytest.raises(ArchiveRateLimited) as excinfo:
        await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A, EXIT_B])
    assert 59 <= excinfo.value.retry_after <= 91  # shortest park: B's max(90, 60)


@pytest.mark.asyncio
async def test_park_applies_to_every_host_class(limiter):
    await limiter.record_rate_limited(EXIT_A, HostClass.WAYBACK_CONTENT, 120.0)
    with pytest.raises(ArchiveRateLimited):
        await limiter.acquire(HostClass.WAYBACK_CDX, [EXIT_A])


@pytest.mark.asyncio
async def test_park_expires_and_exit_is_usable_again(limiter, redis_client):
    await egress.park_exit(EXIT_A.id, 0.05, "short")
    with pytest.raises(ArchiveRateLimited):
        await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A])
    import asyncio

    await asyncio.sleep(0.12)
    lease = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A])
    assert lease.exit.id == EXIT_A.id


@pytest.mark.asyncio
async def test_acquire_raises_when_tokens_do_not_free_up_in_time(limiter):
    for i in range(2):
        lease = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A])
        await limiter.release(lease)
    with pytest.raises(ArchiveRateLimited) as excinfo:
        await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A], timeout=0.1)
    assert excinfo.value.retry_after > 1.0


@pytest.mark.asyncio
async def test_no_exits_raises_connection_error(limiter):
    with pytest.raises(ArchiveConnectionError):
        await limiter.acquire(HostClass.WAYBACK_CONTENT, [])
    with pytest.raises(ArchiveConnectionError):
        await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A], exclude=[EXIT_A.id])


# ------------------------------------------------------------ dead vs blocked


@pytest.mark.asyncio
async def test_proxy_connect_error_marks_exit_dead_and_excludes_it(limiter, probe):
    verdict = await limiter.record_connection_failure(EXIT_A, httpx.ConnectTimeout("proxy down"))
    assert verdict == "dead"
    assert probe.calls == 0  # no probe needed: the proxy itself is unreachable
    lease = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A, EXIT_B])
    assert lease.exit.id == EXIT_B.id
    await limiter.release(lease)
    with pytest.raises(ArchiveConnectionError):
        await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A])


@pytest.mark.asyncio
async def test_failed_probe_marks_dead(limiter, probe):
    probe.result = False
    verdict = await limiter.record_connection_failure(EXIT_A, httpx.ReadTimeout("stalled"))
    assert verdict == "dead"
    state = (await egress.exit_states([EXIT_A.id]))[EXIT_A.id]
    assert state["dead"] is True and state["parked_for_s"] == 0.0


@pytest.mark.asyncio
async def test_refused_after_recent_429_is_blocked_with_doubling_park(limiter, probe):
    probe.result = True
    await limiter.record_rate_limited(EXIT_A, HostClass.WAYBACK_CONTENT, None)
    first = await limiter.record_connection_failure(EXIT_A, httpx.ProxyError("502 Bad Gateway"))
    assert first == "blocked"
    state = (await egress.exit_states([EXIT_A.id]))[EXIT_A.id]
    assert state["dead"] is False
    assert 3590 <= state["parked_for_s"] <= 3600

    # a second firewall hit doubles the park (the lock from the first probe expired in prod;
    # clear it here so the second failure is probed too)
    await egress.get_redis().delete(egress.PROBELOCK_KEY.format(EXIT_A.id))
    await limiter.record_connection_failure(EXIT_A, httpx.RemoteProtocolError("reset"))
    state = (await egress.exit_states([EXIT_A.id]))[EXIT_A.id]
    assert 7190 <= state["parked_for_s"] <= 7200
    assert state["firewall_parks"] == 2


@pytest.mark.asyncio
async def test_firewall_park_is_capped(limiter, probe, redis_client):
    await redis_client.set(egress.PARKCOUNT_KEY.format(EXIT_A.id), 10)
    seconds = await egress.firewall_park(EXIT_A.id)
    assert seconds == 28800.0


@pytest.mark.asyncio
async def test_refused_without_recent_429_is_only_transient(limiter, probe):
    verdict = await limiter.record_connection_failure(EXIT_A, httpx.ProxyError("502"))
    assert verdict == "transient"
    state = (await egress.exit_states([EXIT_A.id]))[EXIT_A.id]
    assert state["dead"] is False
    assert 55 <= state["parked_for_s"] <= 60  # WAYBACK_MIN_PARK_SECONDS, not an hour


@pytest.mark.asyncio
async def test_dead_exit_returns_when_probe_passes(limiter, probe, monkeypatch, redis_client):
    monkeypatch.setattr(settings, "EGRESS_DEAD_RECHECK_SECONDS", 60)
    await egress.mark_exit_dead(EXIT_A.id, "test")
    # the recheck is rate limited across processes: no probe until the lock expires
    probe.result = True
    assert await egress._check_candidate(redis_client, EXIT_A, dead=True, health=False) is False
    assert probe.calls == 0
    await redis_client.delete(egress.PROBELOCK_KEY.format(EXIT_A.id))
    probe.result = False
    assert await egress._check_candidate(redis_client, EXIT_A, dead=True, health=False) is False
    assert await redis_client.exists(egress.DEAD_KEY.format(EXIT_A.id))
    await redis_client.delete(egress.PROBELOCK_KEY.format(EXIT_A.id))
    probe.result = True
    assert await egress._check_candidate(redis_client, EXIT_A, dead=True, health=False) is True
    assert not await redis_client.exists(egress.DEAD_KEY.format(EXIT_A.id))


# ------------------------------------------------------------------- semaphore


@pytest.mark.asyncio
async def test_inflight_cap_and_release(limiter, clock, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_MAX_INFLIGHT_PER_EXIT", 2)
    monkeypatch.setattr(settings, "WAYBACK_CONTENT_RATE_PER_MIN", 600.0)
    first = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A])
    second = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A])
    with pytest.raises(ArchiveRateLimited):
        await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A], timeout=0.05)
    await limiter.release(first)
    clock.advance(1)  # refill tokens: the frozen test clock never does it on its own
    third = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A], timeout=1)
    assert third.exit.id == EXIT_A.id
    await limiter.release(second)
    await limiter.release(third)


@pytest.mark.asyncio
async def test_inflight_lease_expires_so_crashed_workers_do_not_leak_slots(limiter, clock, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_MAX_INFLIGHT_PER_EXIT", 1)
    monkeypatch.setattr(settings, "WAYBACK_INFLIGHT_LEASE_SECONDS", 30.0)
    monkeypatch.setattr(settings, "WAYBACK_CONTENT_RATE_PER_MIN", 600.0)
    await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A])  # never released: "crashed worker"
    with pytest.raises(ArchiveRateLimited):
        await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A], timeout=0.05)
    clock.advance(31)
    lease = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A], timeout=0.05)
    assert lease.exit.id == EXIT_A.id


@pytest.mark.asyncio
async def test_slot_context_manager_releases_on_error(limiter, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_MAX_INFLIGHT_PER_EXIT", 1)
    monkeypatch.setattr(settings, "WAYBACK_CONTENT_RATE_PER_MIN", 600.0)
    with pytest.raises(RuntimeError):
        async with limiter.slot(HostClass.WAYBACK_CONTENT, [EXIT_A]):
            raise RuntimeError("boom")
    async with limiter.slot(HostClass.WAYBACK_CONTENT, [EXIT_A], timeout=0.05) as lease:
        assert lease.exit.id == EXIT_A.id


@pytest.mark.asyncio
async def test_least_loaded_exit_is_chosen(limiter, clock, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_CONTENT_RATE_PER_MIN", 600.0)
    held = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A])
    for _ in range(5):
        clock.advance(1)
        lease = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A, EXIT_B])
        assert lease.exit.id == EXIT_B.id  # A carries one in-flight request, B none
        await limiter.release(lease)
    await limiter.release(held)


@pytest.mark.asyncio
async def test_snapshot_reports_state(limiter):
    lease = await limiter.acquire(HostClass.WAYBACK_CONTENT, [EXIT_A])
    snap = await limiter.snapshot([EXIT_A])
    assert snap[EXIT_A.id]["inflight"] == 1
    assert snap[EXIT_A.id]["wayback_content"]["rate_per_min"] == 30.0
    await limiter.release(lease)


# --------------------------------------------------------------- exit selection


@pytest.mark.asyncio
async def test_select_exits_is_stable_capped_and_replaces_dead(redis_client, probe, monkeypatch):
    pool = [Exit(f"10.0.0.{i}", f"http://10.0.0.{i}:8888") for i in range(1, 11)]

    async def fake_pool():
        return sorted(pool, key=lambda e: egress._stable_order_key(e.id))

    monkeypatch.setattr(egress, "exit_pool", fake_pool)
    monkeypatch.setattr(settings, "EGRESS_PROVIDER", "mullvad")
    monkeypatch.setattr(settings, "EGRESS_INCLUDE_DIRECT", False)
    monkeypatch.setattr(settings, "EGRESS_MAX_EXITS", 4)

    first = await egress.select_exits()
    assert len(first) == 4
    egress.invalidate_selection()
    assert [e.id for e in await egress.select_exits()] == [e.id for e in first]

    await egress.mark_exit_dead(first[1].id, "test")  # holds the probe lock: no recheck yet
    replaced = await egress.select_exits()
    assert len(replaced) == 4
    assert first[1].id not in [e.id for e in replaced]
    assert [e.id for e in replaced if e.id != first[1].id][:3] == [e.id for e in first if e.id != first[1].id]


@pytest.mark.asyncio
async def test_select_exits_swaps_long_parked_exit_for_a_spare(redis_client, probe, monkeypatch):
    pool = [Exit(f"10.0.0.{i}", f"http://10.0.0.{i}:8888") for i in range(1, 7)]

    async def fake_pool():
        return sorted(pool, key=lambda e: egress._stable_order_key(e.id))

    monkeypatch.setattr(egress, "exit_pool", fake_pool)
    monkeypatch.setattr(settings, "EGRESS_PROVIDER", "mullvad")
    monkeypatch.setattr(settings, "EGRESS_INCLUDE_DIRECT", False)
    monkeypatch.setattr(settings, "EGRESS_MAX_EXITS", 3)
    monkeypatch.setattr(settings, "EGRESS_REPLACE_PARK_SECONDS", 900.0)

    first = await egress.select_exits()
    await egress.park_exit(first[0].id, 3600, "firewall")
    short = await egress.park_exit(first[1].id, 120, "429")  # short parks keep their seat
    assert short == 120
    egress.invalidate_selection()
    again = await egress.select_exits()
    assert first[0].id not in [e.id for e in again]
    assert first[1].id in [e.id for e in again]


@pytest.mark.asyncio
async def test_select_exits_can_add_direct(redis_client, monkeypatch):
    monkeypatch.setattr(settings, "EGRESS_PROVIDER", "none")
    monkeypatch.setattr(settings, "EGRESS_INCLUDE_DIRECT", True)
    exits = await egress.select_exits()
    assert [e.id for e in exits] == ["direct"]

    async def fake_pool():
        return [Exit("10.0.0.1", "http://10.0.0.1:8888")]

    monkeypatch.setattr(egress, "exit_pool", fake_pool)
    monkeypatch.setattr(settings, "EGRESS_PROVIDER", "mullvad")
    egress.invalidate_selection()

    async def ok_probe(exit_):
        return True

    monkeypatch.setattr(egress, "probe_exit", ok_probe)
    exits = await egress.select_exits()
    assert [e.id for e in exits] == ["10.0.0.1", "direct"]
