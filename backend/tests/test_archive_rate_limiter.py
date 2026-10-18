"""
Tests for the ONE global Wayback limiter: token bucket shared by CDX + content,
AIMD, global pause on 429/503 (Retry-After, escalation), firewall pause after a
refused connection, deferral (ArchiveDeferred) and in-flight leases.

Redis is fakeredis (with Lua, which the limiter's atomic scripts need).
"""
import asyncio
from datetime import datetime, timedelta, timezone

import fakeredis
import httpx
import pytest
import pytest_asyncio

from app.core.config import settings
from app.services import egress_rotation as egress
from app.services.archive_fetch_errors import ArchiveDeferred
from app.services.archive_rate_limiter import ArchiveRateLimiter, parse_retry_after


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
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def tuned(monkeypatch):
    values = {
        "WAYBACK_EGRESS": "direct",
        "WAYBACK_GLOBAL_RATE_PER_MIN": 30.0,
        "WAYBACK_GLOBAL_MAX_RATE_PER_MIN": 40.0,
        "WAYBACK_MIN_RATE_PER_MIN": 2.0,
        "WAYBACK_AIMD_SUCCESS_STEP": 3,
        "WAYBACK_MAX_INFLIGHT": 10,
        "WAYBACK_INFLIGHT_LEASE_SECONDS": 120.0,
        "WAYBACK_MIN_PAUSE_SECONDS": 60.0,
        "WAYBACK_FIREWALL_PAUSE_SECONDS": 3600.0,
        "WAYBACK_FIREWALL_PAUSE_MAX_SECONDS": 28800.0,
        "WAYBACK_RECENT_429_SECONDS": 1800.0,
        "WAYBACK_ACQUIRE_TIMEOUT": 0.2,
        "WAYBACK_CDX_REQUEST_COST": 1.0,
        "WAYBACK_FIREWALL_INCIDENT_SECONDS": 300.0,
    }
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def limiter(redis_client, tuned, clock):
    return ArchiveRateLimiter(prefix="test", clock=clock)


async def end_pause(redis_client):
    """Simulate the pause running out (the shorter firewall incident window with it)."""
    await redis_client.delete("test:pause", "test:fwlatch")


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
    for _ in range(2):  # burst capacity 2
        lease = await limiter.acquire("content")
        await limiter.release(lease)
    with pytest.raises(ArchiveDeferred) as exc:
        await limiter.acquire("content")
    assert 1.5 <= exc.value.retry_after <= 2.5  # 30/min => one token per 2s
    clock.advance(2.1)
    await limiter.release(await limiter.acquire("content"))


@pytest.mark.asyncio
async def test_one_bucket_is_shared_by_cdx_and_content(limiter):
    """CDX and content draw from the SAME budget: two cdx requests leave nothing for content."""
    await limiter.release(await limiter.acquire("cdx"))
    await limiter.release(await limiter.acquire("cdx"))
    with pytest.raises(ArchiveDeferred):
        await limiter.acquire("content")
    snap = await limiter.snapshot()
    assert snap["tokens"] < 1.0


@pytest.mark.asyncio
async def test_cdx_request_is_weighted_and_its_debt_is_waited_off(limiter, clock, monkeypatch):
    """A CDX query costs WAYBACK_CDX_REQUEST_COST tokens; the bucket goes into debt for it."""
    monkeypatch.setattr(settings, "WAYBACK_CDX_REQUEST_COST", 5.0)
    await limiter.release(await limiter.acquire("cdx"))  # 2 -> -3 tokens
    with pytest.raises(ArchiveDeferred) as exc:
        await limiter.acquire("content")
    assert 7.5 <= exc.value.retry_after <= 8.5  # 4 tokens to earn back at 30/min
    clock.advance(8.1)
    await limiter.release(await limiter.acquire("content"))


@pytest.mark.asyncio
async def test_weighted_cdx_needs_only_one_token_to_start_so_it_cannot_starve(limiter, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_CDX_REQUEST_COST", 5.0)
    await limiter.release(await limiter.acquire("content"))  # 2 -> 1 token, less than the cost
    await limiter.release(await limiter.acquire("cdx"))


@pytest.mark.asyncio
async def test_aimd_additive_increase_after_n_successes_capped(limiter):
    assert await limiter.current_rate() == 30.0
    for _ in range(3):
        await limiter.record_success()
    assert await limiter.current_rate() == 31.0
    for _ in range(60):
        await limiter.record_success()
    assert await limiter.current_rate() == 40.0  # capped at WAYBACK_GLOBAL_MAX_RATE_PER_MIN


@pytest.mark.asyncio
async def test_aimd_multiplicative_decrease_with_floor(limiter, redis_client):
    await limiter.record_rate_limited(None)
    assert await limiter.current_rate() == 15.0
    for _ in range(10):
        await end_pause(redis_client)
        await limiter.record_rate_limited(None)
    assert await limiter.current_rate() == 2.0  # floor


# ------------------------------------------------------------------ global pause


@pytest.mark.asyncio
async def test_429_pauses_all_traffic_for_at_least_the_minimum(limiter):
    pause = await limiter.record_rate_limited(None, "content")
    assert pause == 60.0
    for purpose in ("cdx", "content"):
        with pytest.raises(ArchiveDeferred) as exc:
            await limiter.acquire(purpose)
        assert 55 <= exc.value.retry_after <= 60


@pytest.mark.asyncio
async def test_429_pause_honours_retry_after_seconds_when_longer(limiter):
    assert await limiter.record_rate_limited(900.0) == 900.0
    state = await limiter.snapshot()
    assert 895 <= state["paused_for_s"] <= 900


@pytest.mark.asyncio
async def test_retry_after_http_date_is_honoured_via_parse(limiter):
    now = datetime.now(timezone.utc)
    header = (now + timedelta(seconds=300)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    pause = await limiter.record_rate_limited(parse_retry_after(header))
    assert 295 <= pause <= 301


@pytest.mark.asyncio
async def test_consecutive_429s_double_the_pause_until_a_success(limiter, redis_client):
    assert await limiter.record_rate_limited(None) == 60.0
    await end_pause(redis_client)
    assert await limiter.record_rate_limited(None) == 120.0
    await end_pause(redis_client)
    assert await limiter.record_rate_limited(None) == 240.0
    await limiter.record_success()
    await end_pause(redis_client)
    assert await limiter.record_rate_limited(None) == 60.0  # streak reset


@pytest.mark.asyncio
async def test_escalation_is_capped_at_an_hour_but_retry_after_is_not_capped_there(limiter, redis_client):
    for _ in range(10):
        pause = await limiter.record_rate_limited(None)
        await end_pause(redis_client)
    assert pause == 3600.0
    assert await limiter.record_rate_limited(7200.0) == 7200.0


@pytest.mark.asyncio
async def test_a_429_from_a_request_already_in_flight_does_not_escalate(limiter):
    assert await limiter.record_rate_limited(None) == 60.0
    assert await limiter.record_rate_limited(None) == 60.0  # same incident (still paused)
    assert (await limiter.snapshot())["throttle_streak"] == 1


@pytest.mark.asyncio
async def test_pause_never_shortens(limiter):
    await limiter.pause(600, "a")
    assert await limiter.pause(60, "b") >= 599


@pytest.mark.asyncio
async def test_short_pause_is_waited_out_instead_of_deferring(limiter, redis_client, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_ACQUIRE_TIMEOUT", 5.0)
    await redis_client.set("test:pause", "x", px=300)
    lease = await asyncio.wait_for(limiter.acquire("content"), timeout=3)
    assert lease.purpose == "content"


@pytest.mark.asyncio
async def test_long_pause_defers_immediately_with_the_remaining_time(limiter):
    await limiter.pause(1000, "test")
    loop = asyncio.get_event_loop()
    started = loop.time()
    with pytest.raises(ArchiveDeferred) as exc:
        await limiter.acquire("cdx")
    assert loop.time() - started < 0.5  # no pointless waiting
    assert 990 <= exc.value.retry_after <= 1000


# ------------------------------------------------------------ refused connections


@pytest.mark.asyncio
async def test_refused_after_recent_429_is_a_firewall_block_with_doubling_pause(limiter, redis_client, caplog):
    await limiter.record_rate_limited(None)
    await end_pause(redis_client)
    with caplog.at_level("ERROR"):
        verdict = await limiter.record_connection_failure(httpx.ConnectError("refused"))
    assert verdict == "blocked"
    assert "FIREWALLED" in caplog.text
    state = await limiter.snapshot()
    assert 3590 <= state["paused_for_s"] <= 3600
    assert state["firewall_blocks"] == 1

    await end_pause(redis_client)
    await limiter.record_connection_failure(httpx.ConnectError("refused"))
    assert 7190 <= (await limiter.snapshot())["paused_for_s"] <= 7200


@pytest.mark.asyncio
async def test_concurrent_refusals_in_one_firewall_incident_escalate_once(limiter, redis_client):
    """Two requests in flight when the firewall drops us are ONE block (1h), not two (2h)."""
    await limiter.record_rate_limited(None)
    await end_pause(redis_client)
    verdicts = await asyncio.gather(
        limiter.record_connection_failure(httpx.ConnectError("refused")),
        limiter.record_connection_failure(httpx.ConnectError("refused")),
    )
    assert verdicts == ["blocked", "blocked"]
    state = await limiter.snapshot()
    assert state["firewall_blocks"] == 1
    assert 3590 <= state["paused_for_s"] <= 3600


@pytest.mark.asyncio
async def test_firewall_pause_is_capped(limiter, redis_client):
    await limiter.record_rate_limited(None)
    for _ in range(8):
        await end_pause(redis_client)
        await limiter.record_connection_failure(httpx.RemoteProtocolError("reset"))
    assert (await limiter.snapshot())["paused_for_s"] <= 28800


@pytest.mark.asyncio
async def test_refused_without_recent_429_is_only_a_short_pause(limiter):
    verdict = await limiter.record_connection_failure(httpx.ConnectError("refused"))
    assert verdict == "transient"
    state = await limiter.snapshot()
    assert 55 <= state["paused_for_s"] <= 60
    assert state["firewall_blocks"] == 0


@pytest.mark.asyncio
async def test_read_timeout_changes_nothing(limiter):
    assert await limiter.record_connection_failure(httpx.ReadTimeout("slow")) == "transient"
    assert (await limiter.snapshot())["paused_for_s"] == 0.0


@pytest.mark.asyncio
async def test_proxy_mode_connect_error_is_proxy_down_not_a_firewall_block(limiter, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_EGRESS", "proxy")
    monkeypatch.setattr(settings, "WAYBACK_PROXY_URL", "http://127.0.0.1:8888")
    await limiter.record_rate_limited(None)
    verdict = await limiter.record_connection_failure(httpx.ConnectError("proxy refused"))
    assert verdict == "proxy_down"
    assert (await limiter.snapshot())["firewall_blocks"] == 0


# ------------------------------------------------------------------ in-flight cap


@pytest.mark.asyncio
async def test_global_inflight_cap_and_release(limiter, clock, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_MAX_INFLIGHT", 2)
    monkeypatch.setattr(settings, "WAYBACK_GLOBAL_RATE_PER_MIN", 600.0)
    a = await limiter.acquire("content")
    b = await limiter.acquire("cdx")
    clock.advance(1)
    with pytest.raises(ArchiveDeferred):
        await limiter.acquire("content")  # third concurrent request, whatever its kind
    await limiter.release(a)
    clock.advance(1)
    await limiter.release(await limiter.acquire("content"))
    await limiter.release(b)


@pytest.mark.asyncio
async def test_inflight_lease_expires_so_crashed_workers_do_not_leak_slots(limiter, clock, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_MAX_INFLIGHT", 1)
    monkeypatch.setattr(settings, "WAYBACK_INFLIGHT_LEASE_SECONDS", 30.0)
    monkeypatch.setattr(settings, "WAYBACK_GLOBAL_RATE_PER_MIN", 600.0)
    await limiter.acquire("content")  # never released (worker crashed)
    with pytest.raises(ArchiveDeferred):
        await limiter.acquire("content")
    clock.advance(31)
    await limiter.release(await limiter.acquire("content"))


@pytest.mark.asyncio
async def test_slot_context_manager_releases_on_error(limiter, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_MAX_INFLIGHT", 1)
    monkeypatch.setattr(settings, "WAYBACK_GLOBAL_RATE_PER_MIN", 600.0)
    with pytest.raises(RuntimeError):
        async with limiter.slot("content"):
            raise RuntimeError("boom")
    assert (await limiter.snapshot())["inflight"] == 0


@pytest.mark.asyncio
async def test_redis_failure_defers_instead_of_sending_unpaced(limiter, monkeypatch):
    def broken(decode_responses=True):
        raise ConnectionError("redis down")

    monkeypatch.setattr(egress, "get_redis", broken)
    with pytest.raises(ArchiveDeferred) as exc:
        await limiter.acquire("content")
    assert exc.value.retry_after == 30.0


# ------------------------------------------------------------------ egress / identity


def test_direct_egress_has_no_proxy_and_sends_only_the_identifying_user_agent(monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_EGRESS", "direct")
    monkeypatch.setattr(settings, "WAYBACK_USER_AGENT", "ChronoScraper/2.0.0 (+ops@example.org)")
    kwargs = egress.wayback_client_kwargs()
    assert "proxy" not in kwargs
    assert kwargs["headers"] == {"User-Agent": "ChronoScraper/2.0.0 (+ops@example.org)"}


def test_proxy_egress_uses_the_single_configured_proxy(monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_EGRESS", "proxy")
    monkeypatch.setattr(settings, "WAYBACK_PROXY_URL", "http://10.9.9.9:8888")
    assert egress.wayback_client_kwargs()["proxy"] == "http://10.9.9.9:8888"


def test_default_user_agent_is_built_from_project_settings():
    from app.core.config import Settings

    built = Settings(ADMIN_EMAIL="ops@example.org", WAYBACK_USER_AGENT="")
    assert built.WAYBACK_USER_AGENT == f"{built.PROJECT_NAME.replace(' ', '')}/{built.VERSION} (+ops@example.org)"
    no_contact = Settings(ADMIN_EMAIL=None, WAYBACK_USER_AGENT="")
    assert no_contact.WAYBACK_USER_AGENT == f"{no_contact.PROJECT_NAME.replace(' ', '')}/{no_contact.VERSION}"


def test_proxy_egress_without_a_proxy_url_is_rejected():
    from app.core.config import Settings

    with pytest.raises(ValueError):
        Settings(WAYBACK_EGRESS="proxy", WAYBACK_PROXY_URL=None)
