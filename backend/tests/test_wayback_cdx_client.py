"""
Tests for the Wayback CDX client: resume-key paging, collapse parameter, page
cache, 429/503 handling through the limiter, and date-window splitting.

httpx is mocked with MockTransport; Redis is fakeredis (Lua enabled).
"""
import json
from urllib.parse import parse_qs, urlparse

import fakeredis
import httpx
import pytest
import pytest_asyncio
from tenacity import wait_none

from app.core.config import settings
from app.services import archive_rate_limiter as arl
from app.services import egress_rotation as egress
from app.services.archive_fetch_errors import ArchiveRateLimited
from app.services.egress_rotation import Exit
from app.services.wayback_machine import (
    CDXAPIClient,
    CDXAPIException,
    CDXHTTPError,
    CDXRateLimited,
    CDXRecord,
    normalize_collapse,
)

EXIT_A = Exit("10.1.0.1", "http://10.1.0.1:8888")
EXIT_B = Exit("10.1.0.2", "http://10.1.0.2:8888")

HEADER = ["timestamp", "original", "mimetype", "statuscode", "digest", "length"]


def row(ts: str, path: str, digest: str = "AAA") -> list:
    return [ts, f"https://example.com/{path}", "text/html", "200", digest, "2048"]


def page(rows: list, resume_key: str = None) -> str:
    data = [HEADER] + rows
    if resume_key:
        data += [[], [resume_key]]
    return json.dumps(data)


def query_of(request: httpx.Request) -> dict:
    return {k: v for k, v in parse_qs(urlparse(str(request.url)).query, keep_blank_values=True).items()}


@pytest_asyncio.fixture
async def env(monkeypatch):
    """fakeredis (text + bytes clients on one server), two exits, fast limiter, mocked httpx."""
    server = fakeredis.FakeServer()
    clients = {
        True: fakeredis.FakeAsyncRedis(server=server, decode_responses=True),
        False: fakeredis.FakeAsyncRedis(server=server, decode_responses=False),
    }
    monkeypatch.setattr(egress, "get_redis", lambda decode_responses=True: clients[decode_responses])
    egress.invalidate_selection()

    async def fake_select(max_exits=None):
        return [EXIT_A, EXIT_B]

    monkeypatch.setattr(egress, "select_exits", fake_select)

    async def alive_probe(exit_):
        return True

    monkeypatch.setattr(egress, "probe_exit", alive_probe)
    for key, value in {
        "WAYBACK_CDX_RATE_PER_MIN": 6000.0,
        "WAYBACK_MAX_RATE_PER_MIN": 6000.0,
        "WAYBACK_MAX_INFLIGHT_PER_EXIT": 4,
        "WAYBACK_ACQUIRE_TIMEOUT": 5.0,
        "WAYBACK_CDX_CACHE_TTL": 3600,
        "WAYBACK_CDX_COLLAPSE": "digest",
        "WAYBACK_CDX_PAGE_LIMIT": 5000,
        "WAYBACK_CDX_SPLIT_MAX_DEPTH": 3,
    }.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(arl, "_limiter", arl.ArchiveRateLimiter(prefix="test_cdx"))
    # Don't sleep through real backoff in transient-retry tests.
    monkeypatch.setattr(CDXAPIClient._request_with_retry.retry, "wait", wait_none())

    class Env:
        requests: list = []
        handler = None

    state = Env()
    state.requests = []

    real_client = httpx.AsyncClient

    class PatchedClient(real_client):
        def __init__(self, *args, **kwargs):
            proxy = kwargs.pop("proxy", None)
            kwargs["transport"] = httpx.MockTransport(lambda req: self._dispatch(proxy, req))
            super().__init__(*args, **kwargs)

        @staticmethod
        def _dispatch(proxy, request):
            state.requests.append((proxy, request))
            result = state.handler(proxy, request)
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(httpx, "AsyncClient", PatchedClient)
    yield state
    for c in clients.values():
        await c.flushall()
        await c.aclose()


# ---------------------------------------------------------------- URL building


class TestCollapse:
    def test_default_comes_from_settings(self, monkeypatch):
        monkeypatch.setattr(settings, "WAYBACK_CDX_COLLAPSE", "urlkey")
        assert normalize_collapse() == "urlkey"

    @pytest.mark.parametrize("value", ["digest", "urlkey", "timestamp:8", "timestamp:14", "TIMESTAMP:4"])
    def test_allowed(self, value):
        assert normalize_collapse(value) == value.lower()

    @pytest.mark.parametrize("value", ["timestamp", "timestamp:0", "timestamp:15", "timestamp:x", "original", "digest,urlkey"])
    def test_rejected(self, value):
        with pytest.raises(ValueError):
            normalize_collapse(value)

    def test_url_uses_default_and_override(self):
        client = CDXAPIClient()
        assert "collapse=digest" in client._build_cdx_url_simple("example.com", "20210101", "20211231")
        url = client._build_cdx_url_simple("example.com", "20210101", "20211231", collapse="timestamp:8")
        assert "collapse=timestamp:8" in url and "collapse=digest" not in url
        assert "collapse=urlkey" in client._build_cdx_url("example.com", "20210101", "20211231", collapse="urlkey")

    def test_url_uses_limit_and_resume_key_not_page_size(self):
        client = CDXAPIClient()
        url = client._build_cdx_url_simple("example.com", "20210101", "20211231", limit=250, resume_key="com%2Cexample+2021")
        assert "limit=250" in url and "showResumeKey=true" in url
        assert "resumeKey=com%2Cexample+2021" in url
        for banned in ("pageSize", "page=", "showNumPages"):
            assert banned not in url

    def test_page_count_url_is_plain_text_query(self):
        url = CDXAPIClient()._build_cdx_url("example.com", "20210101", "20211231", show_num_pages=True)
        assert "showNumPages=true" in url and "output=json" not in url and "showResumeKey" not in url

    def test_wayback_content_url_is_raw_id_flavour(self):
        record = CDXRecord.from_wayback_response(row("20210101120000", "a"))
        assert record.content_url == "https://web.archive.org/web/20210101120000id_/https://example.com/a"


class TestParsing:
    def test_resume_key_trailer_is_stripped(self):
        client = CDXAPIClient()
        records, static, key = client._parse_cdx_page(page([row("20210101000000", "a")], "com%2Cexample%29%2F+2021"))
        assert [r.original_url for r in records] == ["https://example.com/a"]
        assert key == "com%2Cexample%29%2F+2021"

    def test_last_page_has_no_key(self):
        _records, _static, key = CDXAPIClient()._parse_cdx_page(page([row("20210101000000", "a")]))
        assert key is None

    def test_empty_body_and_header_only(self):
        client = CDXAPIClient()
        assert client._parse_cdx_page("") == ([], 0, None)
        assert client._parse_cdx_page(json.dumps([HEADER])) == ([], 0, None)

    def test_single_element_row_is_not_mistaken_for_a_key(self):
        data = [HEADER, row("20210101000000", "a"), ["x"]]
        assert CDXAPIClient._split_resume_key(data)[1] is None


class TestWindowSplitting:
    def test_halves_cover_the_range(self):
        (a_from, a_to), (b_from, b_to) = CDXAPIClient._split_window("20210101", "20211231")
        assert a_from == "20210101" and b_to == "20211231"
        assert a_to == "20210702" and b_from == "20210703"

    def test_year_only_bounds(self):
        halves = CDXAPIClient._split_window("2021", "2021")
        assert halves is not None and halves[0][0] == "2021" and halves[1][1] == "2021"

    def test_single_day_cannot_split(self):
        assert CDXAPIClient._split_window("20210101", "20210101") is None

    def test_garbage_cannot_split(self):
        assert CDXAPIClient._split_window("x", "y") is None


# ---------------------------------------------------------------------- paging


@pytest.mark.asyncio
async def test_resume_key_paging_follows_keys_until_exhausted(env):
    pages = {
        None: page([row("20210101000000", "a"), row("20210102000000", "b")], "KEY1"),
        "KEY1": page([row("20210103000000", "c")], "KEY2"),
        "KEY2": page([row("20210104000000", "d")]),
    }
    env.handler = lambda proxy, req: httpx.Response(200, text=pages[query_of(req).get("resumeKey", [None])[0]])

    records, stats = await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231", page_size=2)

    assert [r.original_url.rsplit("/", 1)[1] for r in records] == ["a", "b", "c", "d"]
    assert stats["fetched_pages"] == 3 and stats["final_count"] == 4
    queries = [query_of(req) for _p, req in env.requests]
    assert [q.get("resumeKey", [None])[0] for q in queries] == [None, "KEY1", "KEY2"]
    assert all(q["limit"] == ["2"] and q["showResumeKey"] == ["true"] and q["collapse"] == ["digest"] for q in queries)
    assert all("pageSize" not in q and "page" not in q and "showNumPages" not in q for q in queries)


@pytest.mark.asyncio
async def test_max_pages_bounds_requests(env):
    env.handler = lambda proxy, req: httpx.Response(200, text=page([row("20210101000000", "a")], "MORE"))
    _records, stats = await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231", max_pages=2)
    assert stats["fetched_pages"] == 2 and len(env.requests) == 2


@pytest.mark.asyncio
async def test_per_call_collapse_override_reaches_the_request(env):
    env.handler = lambda proxy, req: httpx.Response(200, text=page([row("20210101000000", "a")]))
    await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231", collapse="timestamp:8")
    assert query_of(env.requests[0][1])["collapse"] == ["timestamp:8"]


@pytest.mark.asyncio
async def test_pages_are_cached_by_full_query(env):
    env.handler = lambda proxy, req: httpx.Response(200, text=page([row("20210101000000", "a")]))
    client = CDXAPIClient()
    first, _ = await client.fetch_cdx_records_simple("example.com", "20210101", "20211231")
    second, _ = await client.fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert len(env.requests) == 1 and len(first) == len(second) == 1
    await client.fetch_cdx_records_simple("example.com", "20210101", "20211231", collapse="urlkey")
    assert len(env.requests) == 2  # different params, different cache entry


@pytest.mark.asyncio
async def test_cache_can_be_disabled(env, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_CDX_CACHE_TTL", 0)
    env.handler = lambda proxy, req: httpx.Response(200, text=page([row("20210101000000", "a")]))
    client = CDXAPIClient()
    await client.fetch_cdx_records_simple("example.com", "20210101", "20211231")
    await client.fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert len(env.requests) == 2


@pytest.mark.asyncio
async def test_get_page_count_reads_plain_integer(env):
    env.handler = lambda proxy, req: httpx.Response(200, text="7\n")
    assert await CDXAPIClient().get_page_count("example.com", "20210101", "20211231") == 7


# --------------------------------------------------------------- errors / pacing


@pytest.mark.asyncio
async def test_429_parks_exit_raises_typed_error_and_does_not_storm(env):
    env.handler = lambda proxy, req: httpx.Response(429, headers={"Retry-After": "300"}, text="slow down")
    with pytest.raises(CDXRateLimited) as excinfo:
        await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    exc = excinfo.value
    assert isinstance(exc, CDXAPIException) and isinstance(exc, ArchiveRateLimited)
    assert exc.status_code == 429 and exc.retry_after >= 299
    assert len(env.requests) == 1  # no inline retry on another exit
    parked = await egress.park_remaining([EXIT_A.id, EXIT_B.id])
    assert sorted(v > 0 for v in parked.values()) == [False, True]


@pytest.mark.asyncio
async def test_429_with_http_date_retry_after_and_no_header_default(env):
    env.handler = lambda proxy, req: httpx.Response(
        429, headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}
    )
    with pytest.raises(CDXRateLimited) as excinfo:
        await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert excinfo.value.retry_after > 3600  # a date far in the future is honoured, not crashed on

    env.handler = lambda proxy, req: httpx.Response(429)
    env.requests.clear()
    await egress.get_redis().flushall()
    with pytest.raises(CDXRateLimited) as excinfo:
        await CDXAPIClient().fetch_cdx_records_simple("example.org", "20210101", "20211231")
    assert 59 <= excinfo.value.retry_after <= 60


@pytest.mark.asyncio
async def test_503_on_first_page_splits_the_window(env):
    def handler(proxy, req):
        q = query_of(req)
        if q["from"] == ["20210101"] and q["to"] == ["20211231"]:
            return httpx.Response(503)
        return httpx.Response(200, text=page([row(q["from"][0] + "000000", f"w{q['from'][0]}")]))

    env.handler = handler
    records, stats = await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert stats["windows_split"] == 1
    assert len(env.requests) == 3
    windows = sorted((query_of(r)["from"][0], query_of(r)["to"][0]) for _p, r in env.requests[1:])
    assert windows == [("20210101", "20210702"), ("20210703", "20211231")]
    assert len(records) == 2


@pytest.mark.asyncio
async def test_503_on_later_page_propagates_without_splitting(env):
    def handler(proxy, req):
        if "resumeKey" in query_of(req):
            return httpx.Response(503)
        return httpx.Response(200, text=page([row("20210101000000", "a")], "KEY"))

    env.handler = handler
    with pytest.raises(CDXRateLimited):
        await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert len(env.requests) == 2


@pytest.mark.asyncio
async def test_504_retries_three_attempts_then_splits(env):
    def handler(proxy, req):
        q = query_of(req)
        if q["from"] == ["20210101"] and q["to"] == ["20211231"]:
            return httpx.Response(504)
        return httpx.Response(200, text=page([row(q["from"][0] + "000000", "x")]))

    env.handler = handler
    records, stats = await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert stats["windows_split"] == 1 and len(records) == 2
    assert len(env.requests) == 3 + 2  # 3 attempts on the full window, then two halves


@pytest.mark.asyncio
async def test_split_depth_is_bounded(env, monkeypatch):
    monkeypatch.setattr(settings, "WAYBACK_CDX_SPLIT_MAX_DEPTH", 1)
    env.handler = lambda proxy, req: httpx.Response(504)
    with pytest.raises(CDXHTTPError):
        await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert len(env.requests) == 3 + 3  # full window x3, then the first half x3, then give up


@pytest.mark.asyncio
async def test_400_is_final(env):
    env.handler = lambda proxy, req: httpx.Response(400, text="bad query")
    with pytest.raises(CDXHTTPError) as excinfo:
        await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert excinfo.value.retryable is False and len(env.requests) == 1


@pytest.mark.asyncio
async def test_dead_exit_is_excluded_and_request_retried_on_another(env):
    def handler(proxy, req):
        if proxy == EXIT_A.proxy_url:
            return httpx.ConnectTimeout("proxy down")
        return httpx.Response(200, text=page([row("20210101000000", "a")]))

    env.handler = handler
    # make the dead exit the first pick deterministically
    limiter = arl.get_archive_rate_limiter()
    order = {"n": 0}
    original = limiter._order_by_load

    async def a_first(exits):
        order["n"] += 1
        return sorted(exits, key=lambda e: e.id)

    limiter._order_by_load = a_first
    try:
        records, _ = await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    finally:
        limiter._order_by_load = original
    assert len(records) == 1
    assert [p for p, _r in env.requests] == [EXIT_A.proxy_url, EXIT_B.proxy_url]
    states = await egress.exit_states([EXIT_A.id, EXIT_B.id])
    assert states[EXIT_A.id]["dead"] is True and states[EXIT_B.id]["dead"] is False


@pytest.mark.asyncio
async def test_all_exits_parked_raises_rate_limited_without_requests(env):
    await egress.park_exit(EXIT_A.id, 600, "test")
    await egress.park_exit(EXIT_B.id, 600, "test")
    with pytest.raises(CDXRateLimited) as excinfo:
        await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert excinfo.value.retry_after > 500
    assert env.requests == []


@pytest.mark.asyncio
async def test_html_error_body_is_not_treated_as_cdx_data(env):
    env.handler = lambda proxy, req: httpx.Response(200, text="<html>Service busy</html>")
    with pytest.raises(CDXHTTPError):
        await CDXAPIClient().fetch_cdx_records_simple("example.com", "20210101", "20211231")
    assert len(env.requests) == 3  # transient: 3 attempts, nothing cached
