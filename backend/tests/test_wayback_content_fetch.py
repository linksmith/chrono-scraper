"""
Tests for the Wayback content path: block/error page detection on realistic
bodies, status mapping to typed errors, and the one-request-per-page fetch
through the limiter (mocked httpx, fakeredis).
"""
import fakeredis
import httpx
import pytest
import pytest_asyncio

from app.core.config import settings
from app.services import archive_rate_limiter as arl
from app.services import egress_rotation as egress
from app.services.archive_fetch_errors import (
    ArchiveBlockPage,
    ArchiveConnectionError,
    ArchiveFetchError,
    ArchiveHTTPError,
    ArchiveRateLimited,
)
from app.services.content_extraction_service import (
    ContentExtractionService,
    check_wayback_response,
    detect_block_page,
)
from app.services.egress_rotation import Exit
from app.services.wayback_machine import CDXRecord

EXIT_A = Exit("10.2.0.1", "http://10.2.0.1:8888")
EXIT_B = Exit("10.2.0.2", "http://10.2.0.2:8888")

IA_429_HTML = (
    "<html><head><title>429 Too Many Requests</title></head><body>"
    "<center><h1>429 Too Many Requests</h1></center><hr><center>nginx</center></body></html>"
)

IA_RATE_LIMIT_PLAIN = "<html><body><p>Too Many Requests. You have sent too many requests to the Wayback Machine.</p></body></html>"

IA_NOT_ARCHIVED = """<!DOCTYPE html>
<html lang="en"><head><title>Wayback Machine</title>
<link rel="stylesheet" href="/_static/css/styles.css"></head>
<body><div id="positionHome"><section>
<p class="code shift red">Hrm.</p>
<p>The Wayback Machine has not archived that URL.</p>
<p class="impatient"><a href="https://web.archive.org/save">Save this url in the Wayback Machine</a></p>
</section></div></body></html>"""

IA_HRM_ONLY = """<!DOCTYPE html><html><head><title>Hrm. | Wayback Machine</title></head>
<body><p class="code shift red">Hrm.</p><p>Something went wrong with that request.</p></body></html>"""

IA_EXCLUDED = """<html><head><title>Wayback Machine</title></head><body>
<p>This URL has been excluded from the Wayback Machine.</p></body></html>"""

BLANK_NEW_TAB = "<html><head><title>New Tab</title></head><body></body></html>"
ABOUT_BLANK = "about:blank"
BLANK_SKELETON = "<html><head></head><body>\n</body></html>"
TINY_IA_ERROR = "<html><body><h1>Internet Archive</h1><p>Service temporarily unavailable.</p></body></html>"

REAL_PAGE = (
    "<!DOCTYPE html><html><head><title>Council minutes 2021</title></head><body><article>"
    + "<p>The council met on Tuesday to discuss the municipal budget for the coming year. "
    "Several members raised concerns about infrastructure spending. </p>" * 12
    + "</article></body></html>"
)


class TestDetectBlockPage:
    def test_real_content_passes(self):
        assert detect_block_page(REAL_PAGE) is None

    def test_real_page_that_mentions_rate_limits_passes(self):
        page = REAL_PAGE.replace("budget", "budget and API rate limit policy")
        assert detect_block_page(page) is None

    def test_pdf_is_never_flagged(self):
        assert detect_block_page("%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj") is None

    def test_ia_429_html_is_rate_limited(self):
        err = detect_block_page(IA_429_HTML, "https://web.archive.org/web/1id_/x")
        assert isinstance(err, ArchiveRateLimited) and err.status_code == 429

    def test_plain_too_many_requests_text(self):
        assert isinstance(detect_block_page(IA_RATE_LIMIT_PLAIN), ArchiveRateLimited)

    def test_not_archived_page_is_permanent(self):
        err = detect_block_page(IA_NOT_ARCHIVED)
        assert isinstance(err, ArchiveBlockPage) and err.retryable is False

    def test_hrm_title_page_is_permanent_block_page(self):
        err = detect_block_page(IA_HRM_ONLY)
        assert isinstance(err, ArchiveBlockPage)

    def test_excluded_page_is_permanent(self):
        err = detect_block_page(IA_EXCLUDED)
        assert isinstance(err, ArchiveBlockPage) and err.retryable is False

    @pytest.mark.parametrize("body", [BLANK_NEW_TAB, ABOUT_BLANK, BLANK_SKELETON, "", "   \n ", None])
    def test_blank_bodies_are_block_pages_and_retryable(self, body):
        err = detect_block_page(body)
        assert isinstance(err, ArchiveBlockPage) and err.retryable is True

    def test_tiny_ia_error_page(self):
        assert isinstance(detect_block_page(TINY_IA_ERROR), ArchiveBlockPage)

    def test_frameset_page_is_not_blank(self):
        page = '<html><frameset cols="50%,50%"><frame src="a.html"><frame src="b.html"></frameset></html>'
        assert detect_block_page(page) is None


class TestCheckWaybackResponse:
    def test_429_uses_retry_after_seconds(self):
        with pytest.raises(ArchiveRateLimited) as exc:
            check_wayback_response("u", 429, {"Retry-After": "120"}, IA_429_HTML)
        assert exc.value.retry_after == 120.0 and exc.value.status_code == 429

    def test_503_uses_retry_after_http_date(self):
        with pytest.raises(ArchiveRateLimited) as exc:
            check_wayback_response("u", 503, {"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}, "")
        assert exc.value.retry_after > 3600

    def test_429_without_header(self):
        with pytest.raises(ArchiveRateLimited) as exc:
            check_wayback_response("u", 429, {}, "")
        assert exc.value.retry_after is None

    @pytest.mark.parametrize("status", [404, 410, 400, 403])
    def test_client_errors_are_final(self, status):
        with pytest.raises(ArchiveHTTPError) as exc:
            check_wayback_response("u", status, {}, IA_NOT_ARCHIVED)
        assert exc.value.retryable is False and exc.value.status_code == status

    @pytest.mark.parametrize("status", [500, 502, 504, 522])
    def test_server_errors_are_retryable(self, status):
        with pytest.raises(ArchiveHTTPError) as exc:
            check_wayback_response("u", status, {}, "")
        assert exc.value.retryable is True

    def test_200_block_body_raises_and_records_status(self):
        with pytest.raises(ArchiveBlockPage) as exc:
            check_wayback_response("u", 200, {}, BLANK_NEW_TAB)
        assert exc.value.status_code == 200

    def test_200_real_page_passes(self):
        check_wayback_response("u", 200, {}, REAL_PAGE)


# ------------------------------------------------------------------ fetch path


def make_record(ts="20210315120000", url="https://example.com/news/1") -> CDXRecord:
    return CDXRecord.from_wayback_response([ts, url, "text/html", "200", "ABC", "4096"])


@pytest_asyncio.fixture
async def env(monkeypatch):
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(egress, "get_redis", lambda decode_responses=True: client)
    egress.invalidate_selection()

    async def fake_select(max_exits=None):
        return [EXIT_A, EXIT_B]

    monkeypatch.setattr(egress, "select_exits", fake_select)

    async def alive_probe(exit_):
        return True

    monkeypatch.setattr(egress, "probe_exit", alive_probe)
    for key, value in {
        "WAYBACK_CONTENT_RATE_PER_MIN": 6000.0,
        "WAYBACK_MAX_RATE_PER_MIN": 6000.0,
        "WAYBACK_MAX_INFLIGHT_PER_EXIT": 4,
        "WAYBACK_ACQUIRE_TIMEOUT": 2.0,
        "WAYBACK_MIN_PARK_SECONDS": 60.0,
    }.items():
        monkeypatch.setattr(settings, key, value)
    limiter = arl.ArchiveRateLimiter(prefix="test_content")
    monkeypatch.setattr(arl, "_limiter", limiter)

    # Deterministic pick order: A before B.
    async def a_first(exits):
        return sorted(exits, key=lambda e: e.id)

    monkeypatch.setattr(limiter, "_order_by_load", a_first)

    class State:
        requests: list = []
        handler = None

    state = State()
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
    state.limiter = limiter
    state.client = client
    yield state
    await client.flushall()
    await client.aclose()


@pytest.fixture
def service():
    return ContentExtractionService()


@pytest.mark.asyncio
async def test_success_is_exactly_one_request_with_fetch_time(env, service):
    env.handler = lambda proxy, req: httpx.Response(200, text=REAL_PAGE)
    record = make_record()
    assert "id_/" in record.content_url

    html, fetch_time = await service._fetch_html(record, record.content_url)

    assert html == REAL_PAGE
    assert fetch_time >= 0.0
    assert len(env.requests) == 1
    proxy, request = env.requests[0]
    assert proxy == EXIT_A.proxy_url
    assert request.headers["referer"] == "https://web.archive.org/"
    state = (await egress.exit_states([EXIT_A.id]))[EXIT_A.id]
    assert state["parked_for_s"] == 0.0


@pytest.mark.asyncio
async def test_429_parks_exit_raises_and_is_not_retried(env, service):
    env.handler = lambda proxy, req: httpx.Response(429, headers={"Retry-After": "200"}, text=IA_429_HTML)
    record = make_record()
    with pytest.raises(ArchiveRateLimited) as excinfo:
        await service._fetch_html(record, record.content_url)
    assert len(env.requests) == 1
    assert excinfo.value.retry_after >= 199
    assert hasattr(excinfo.value, "fetch_time")
    parked = await egress.park_remaining([EXIT_A.id, EXIT_B.id])
    assert parked[EXIT_A.id] >= 199 and parked[EXIT_B.id] == 0


@pytest.mark.asyncio
async def test_429_html_with_200_status_is_treated_as_rate_limit(env, service):
    env.handler = lambda proxy, req: httpx.Response(200, text=IA_429_HTML)
    record = make_record()
    with pytest.raises(ArchiveRateLimited):
        await service._fetch_html(record, record.content_url)
    assert (await egress.park_remaining([EXIT_A.id]))[EXIT_A.id] >= 59
    assert len(env.requests) == 1


@pytest.mark.asyncio
async def test_connection_error_retries_once_on_a_different_exit(env, service):
    def handler(proxy, req):
        if proxy == EXIT_A.proxy_url:
            return httpx.ConnectTimeout("proxy down")
        return httpx.Response(200, text=REAL_PAGE)

    env.handler = handler
    record = make_record()
    html, _ = await service._fetch_html(record, record.content_url)
    assert html == REAL_PAGE
    assert [p for p, _r in env.requests] == [EXIT_A.proxy_url, EXIT_B.proxy_url]
    states = await egress.exit_states([EXIT_A.id, EXIT_B.id])
    assert states[EXIT_A.id]["dead"] is True


@pytest.mark.asyncio
async def test_connection_error_twice_raises_after_exactly_two_requests(env, service):
    env.handler = lambda proxy, req: httpx.ConnectError("refused")
    record = make_record()
    with pytest.raises(ArchiveConnectionError):
        await service._fetch_html(record, record.content_url)
    assert len(env.requests) == 2
    assert env.requests[0][0] != env.requests[1][0]


@pytest.mark.asyncio
async def test_refused_after_recent_429_parks_for_firewall_and_is_connection_error(env, service):
    await egress.note_throttled(EXIT_A.id)
    await egress.note_throttled(EXIT_B.id)
    env.handler = lambda proxy, req: httpx.ProxyError("502 Bad Gateway")
    record = make_record()
    with pytest.raises(ArchiveConnectionError):
        await service._fetch_html(record, record.content_url)
    states = await egress.exit_states([EXIT_A.id, EXIT_B.id])
    assert all(3500 < s["parked_for_s"] <= 3600 for s in states.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("status,exc_type", [(404, ArchiveHTTPError), (410, ArchiveHTTPError)])
async def test_gone_pages_raise_http_error_without_retry(env, service, status, exc_type):
    env.handler = lambda proxy, req: httpx.Response(status, text=IA_NOT_ARCHIVED)
    record = make_record()
    with pytest.raises(exc_type) as excinfo:
        await service._fetch_html(record, record.content_url)
    assert excinfo.value.status_code == status and excinfo.value.retryable is False
    assert len(env.requests) == 1


@pytest.mark.asyncio
async def test_5xx_is_not_retried_inline(env, service):
    env.handler = lambda proxy, req: httpx.Response(502, text="bad gateway")
    record = make_record()
    with pytest.raises(ArchiveHTTPError) as excinfo:
        await service._fetch_html(record, record.content_url)
    assert excinfo.value.retryable is True and len(env.requests) == 1


@pytest.mark.asyncio
async def test_blank_200_body_raises_block_page_before_extraction(env, service):
    env.handler = lambda proxy, req: httpx.Response(200, text=BLANK_NEW_TAB)
    record = make_record()
    with pytest.raises(ArchiveBlockPage):
        await service._fetch_html(record, record.content_url)


@pytest.mark.asyncio
async def test_redirect_to_another_capture_is_followed(env, service):
    def handler(proxy, req):
        if "20210315120000id_" in str(req.url):
            return httpx.Response(302, headers={"Location": "https://web.archive.org/web/20210316000000id_/https://example.com/news/1"})
        return httpx.Response(200, text=REAL_PAGE)

    env.handler = handler
    record = make_record()
    html, _ = await service._fetch_html(record, record.content_url)
    assert html == REAL_PAGE


@pytest.mark.asyncio
async def test_all_exits_parked_raises_rate_limited_without_any_request(env, service):
    await egress.park_exit(EXIT_A.id, 600, "test")
    await egress.park_exit(EXIT_B.id, 600, "test")
    env.handler = lambda proxy, req: httpx.Response(200, text=REAL_PAGE)
    record = make_record()
    with pytest.raises(ArchiveRateLimited) as excinfo:
        await service._fetch_html(record, record.content_url)
    assert excinfo.value.retry_after > 500
    assert env.requests == []


@pytest.mark.asyncio
async def test_extract_content_reraises_typed_fetch_errors_and_attaches_fetch_time(env, service):
    env.handler = lambda proxy, req: httpx.Response(200, text=REAL_PAGE)
    record = make_record()
    result = await service.extract_content(record)
    assert result.fetch_time >= 0.0

    env.handler = lambda proxy, req: httpx.Response(429, text=IA_429_HTML)
    with pytest.raises(ArchiveFetchError) as excinfo:
        await service.extract_content(record)
    assert isinstance(excinfo.value, ArchiveRateLimited)
    assert service.metrics["failed_extractions"] >= 1


@pytest.mark.asyncio
async def test_escalation_path_reraises_too(env, service):
    env.handler = lambda proxy, req: httpx.Response(404, text=IA_NOT_ARCHIVED)
    record = make_record()
    with pytest.raises(ArchiveHTTPError):
        await service.extract_content_with_escalation(record, retry_count=3)


@pytest.mark.asyncio
async def test_common_crawl_warc_path_never_touches_limiter_or_proxies(env, service, monkeypatch):
    from app.models.project import ArchiveSource

    class FakeCC:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def fetch_warc_html(self, filename, offset, length):
            return REAL_PAGE

    import app.services.common_crawl_direct_service as cc_module

    monkeypatch.setattr(cc_module, "CommonCrawlDirectService", FakeCC)

    record = CDXRecord(
        timestamp="20210315120000", original_url="https://example.com/a", mime_type="text/html",
        status_code="200", digest="D", length="1", source=ArchiveSource.COMMON_CRAWL,
        warc_filename="crawl-data/x.warc.gz", warc_offset=10, warc_length=20,
    )
    env.handler = lambda proxy, req: pytest.fail("no HTTP request expected on the CC path")
    html, fetch_time = await service._fetch_html(record, record.content_url)
    assert html == REAL_PAGE and env.requests == []
    snap = await env.limiter.snapshot([EXIT_A, EXIT_B])
    assert snap[EXIT_A.id]["inflight"] == 0 and snap[EXIT_A.id]["wayback_content"]["tokens"] is None
