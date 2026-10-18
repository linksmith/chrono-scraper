"""
Tests for discovery (Common Crawl crawl selection/paging, hybrid merge), digest/content
dedup on storage, and honest failure/retry/reaper state.
"""
import json
from datetime import datetime, timedelta, timezone

import aiohttp
import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.models.scraping import PageErrorLog, ScrapePage, ScrapePageStatus
from app.models.shared_pages import Page, ProjectPage
from app.services.archive_merge import merge_hybrid_records, normalize_url, period_key
from app.services.common_crawl_direct_service import CommonCrawlDirectService, DirectCommonCrawlException
from app.services.page_persistence import (
    ERROR_DIGEST_REUSE,
    ERROR_DUPLICATE_CONTENT,
    ERROR_STALE_IN_PROGRESS,
    compute_content_hash,
    compute_retry_delay,
    find_pages_by_digests,
    link_by_digest,
    persist_extracted_page,
    reap_stale_in_progress,
    record_failure,
    requeue_due_failures,
)
from app.services.wayback_machine import CDXRecord


# ---------------------------------------------------------------------------
# Common Crawl discovery
# ---------------------------------------------------------------------------

def _collinfo():
    """One crawl per ~2 months from 2013 to 2026, newest first (like collinfo.json)."""
    info = []
    for year in range(2026, 2012, -1):
        for month in (11, 9, 7, 5, 3, 1):
            info.append({
                "id": f"CC-MAIN-{year}-{month:02d}",
                "cdx-api": f"https://index.commoncrawl.org/CC-MAIN-{year}-{month:02d}-index",
                "from": f"{year}-{month:02d}-01T00:00:00",
                "to": f"{year}-{month:02d}-20T00:00:00",
            })
    info.append({"id": "CC-MAIN-2008-2009", "cdx-api": "https://index.commoncrawl.org/CC-MAIN-2008-2009-index",
                 "from": "2008-05-09T05:37:12", "to": "2009-01-09T20:58:29"})
    return info


@pytest.fixture
def cc_service(tmp_path):
    CommonCrawlDirectService._collinfo_cache = _collinfo()
    yield CommonCrawlDirectService(cache_dir=str(tmp_path))
    CommonCrawlDirectService._collinfo_cache = None


@pytest.mark.asyncio
async def test_old_date_range_selects_every_overlapping_crawl(cc_service):
    selected = await cc_service._collections_for_range("20190101", "20251231")
    ids = [c["id"] for c in selected]
    assert len(ids) == 7 * 6  # all 2019..2025 crawls, not just the newest six
    assert all("2019" <= i.split("-")[2] <= "2025" for i in ids)
    assert ids[0].startswith("CC-MAIN-2025")  # newest first


@pytest.mark.asyncio
async def test_range_selects_only_crawls_inside_window(cc_service):
    selected = await cc_service._collections_for_range("20200301", "20200521")
    assert [c["id"] for c in selected] == ["CC-MAIN-2020-05", "CC-MAIN-2020-03"]


@pytest.mark.asyncio
async def test_legacy_arc_crawl_selected_by_window(cc_service):
    selected = await cc_service._collections_for_range("20080101", "20081231")
    assert [c["id"] for c in selected] == ["CC-MAIN-2008-2009"]


@pytest.mark.asyncio
async def test_range_without_crawls_selects_nothing(cc_service):
    assert await cc_service._collections_for_range("20100101", "20101231") == []


def _index_line(url, ts, digest, offset=100):
    return json.dumps({
        "urlkey": "x", "timestamp": ts, "url": url, "mime": "text/html", "status": "200",
        "digest": digest, "length": "5000", "offset": str(offset), "filename": f"crawl-data/f{ts}.warc.gz",
    })


@pytest.mark.asyncio
async def test_query_index_api_follows_pages_and_keeps_warc_fields(cc_service, monkeypatch):
    calls = []

    async def fake_get(cdx_api, params):
        calls.append(dict(params[-1:]))
        if ("showNumPages", "true") in params:
            return json.dumps({"pages": 2, "pageSize": 5, "blocks": 9})
        page = dict(params)["page"]
        if page == "0":
            return _index_line("https://a.nl/1", "20200101000000", "D1") + "\n" + _index_line("https://a.nl/2", "20200102000000", "D2")
        return _index_line("https://a.nl/3", "20200103000000", "D3", offset=777)

    monkeypatch.setattr(cc_service, "_get_index_text", fake_get)
    recs = await cc_service._query_index_api("https://x/index", "a.nl", "domain", "20200101", "20201231", 100)

    assert [r.original_url for r in recs] == ["https://a.nl/1", "https://a.nl/2", "https://a.nl/3"]
    assert recs[2].warc_filename == "crawl-data/f20200103000000.warc.gz"
    assert recs[2].warc_offset == 777 and recs[2].warc_length == 5000
    assert recs[0].is_common_crawl


@pytest.mark.asyncio
async def test_query_index_api_sends_mime_and_status_filters(cc_service):
    params = cc_service._index_params("a.nl", "domain", "20200101", "20201231", include_attachments=False)
    assert ("filter", "mime:text/html") in params and ("filter", "=status:200") in params
    with_pdf = cc_service._index_params("a.nl", "domain", "20200101", "20201231", include_attachments=True)
    assert ("filter", "~mime:(text/html|application/pdf)") in with_pdf


class _FakeResponse:
    def __init__(self, status, body="", headers=None):
        self.status, self._body, self.headers = status, body, headers or {}

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.mark.asyncio
async def test_index_request_retries_503_then_succeeds(cc_service, monkeypatch):
    monkeypatch.setattr(settings, "CC_INDEX_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(settings, "CC_INDEX_BACKOFF_BASE_SECONDS", 0.01)
    cc_service.session = _FakeSession([_FakeResponse(503), aiohttp.ClientConnectionError("reset"), _FakeResponse(200, "ok")])
    assert await cc_service._get_index_text("https://x/index", []) == "ok"
    assert cc_service.session.calls == 3


@pytest.mark.asyncio
async def test_index_request_404_means_no_captures_and_gives_up_after_retries(cc_service, monkeypatch):
    monkeypatch.setattr(settings, "CC_INDEX_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(settings, "CC_INDEX_BACKOFF_BASE_SECONDS", 0.01)
    cc_service.session = _FakeSession([_FakeResponse(404, "{}")])
    assert await cc_service._get_index_text("https://x/index", []) is None

    cc_service.session = _FakeSession([_FakeResponse(503)] * settings.CC_INDEX_MAX_RETRIES)
    with pytest.raises(DirectCommonCrawlException):
        await cc_service._get_index_text("https://x/index", [])
    assert cc_service.session.calls == settings.CC_INDEX_MAX_RETRIES


@pytest.mark.asyncio
async def test_failure_pauses_all_index_requests_and_requests_are_paced(cc_service, monkeypatch):
    monkeypatch.setattr(settings, "CC_INDEX_MIN_INTERVAL_SECONDS", 0.2)
    monkeypatch.setattr(settings, "CC_INDEX_BACKOFF_BASE_SECONDS", 0.3)
    cc_service.session = _FakeSession([_FakeResponse(503), _FakeResponse(200, "a"), _FakeResponse(200, "b")])
    import time
    started = time.monotonic()
    assert await cc_service._get_index_text("https://x/index", []) == "a"
    assert time.monotonic() - started >= 0.3  # the 503 started a cooldown the retry had to sit out
    started = time.monotonic()
    assert await cc_service._get_index_text("https://x/index", []) == "b"
    assert time.monotonic() - started >= 0.15  # minimum spacing between consecutive requests


# ---------------------------------------------------------------------------
# Hybrid merge
# ---------------------------------------------------------------------------

def _cc(url, ts, digest="CC"):
    return CDXRecord.from_common_crawl_response({
        "timestamp": ts, "url": url, "mimetype": "text/html", "statuscode": "200", "digest": digest,
        "length": "100", "filename": "crawl-data/x.warc.gz", "offset": 1, "warc_length": 100,
    })


def _wb(url, ts, digest="WB"):
    return CDXRecord(timestamp=ts, original_url=url, mime_type="text/html", status_code="200",
                     digest=digest, length="100")


@pytest.mark.parametrize("a,b", [
    ("http://www.Example.com/page/", "https://example.com/page"),
    ("https://example.com:443/page#frag", "http://example.com:80/page"),
    ("example.com/page", "https://www.example.com/page/"),
])
def test_normalize_url_collapses_equivalent_spellings(a, b):
    assert normalize_url(a) == normalize_url(b)


def test_normalize_url_keeps_what_changes_content():
    assert normalize_url("https://example.com/a?id=1") != normalize_url("https://example.com/a?id=2")
    assert normalize_url("https://example.com:8080/a") != normalize_url("https://example.com/a")
    assert normalize_url("https://example.com/a") != normalize_url("https://example.com/b")


def test_period_key_prefixes():
    assert period_key("20200315123000", "day") == "20200315"
    assert period_key("20200315123000", "month") == "202003"
    assert period_key("20200315123000", "year") == "2020"
    with pytest.raises(ValueError):
        period_key("20200315123000", "week")


def test_hybrid_url_period_drops_wayback_captures_cc_covers():
    cc = [_cc("https://www.example.com/a/", "20200310000000")]
    wb = [
        _wb("http://example.com/a", "20200328000000"),   # same URL, same month: covered
        _wb("http://example.com/a", "20200402000000"),   # same URL, other month: kept
        _wb("http://example.com/b", "20200310000000"),   # other URL: kept
    ]
    merged, stats = merge_hybrid_records(cc, wb, mode="url_period", period="month")
    assert stats == {"cc": 1, "wayback": 3, "wayback_dropped": 1, "final": 3}
    assert merged[0] is cc[0]  # CC record (with its WARC fields) is returned untouched
    assert merged[0].warc_filename == "crawl-data/x.warc.gz"
    assert [r.timestamp for r in merged[1:]] == ["20200402000000", "20200310000000"]


def test_hybrid_url_period_respects_period_setting():
    cc = [_cc("https://example.com/a", "20200310000000")]
    wb = [_wb("https://example.com/a", "20200328000000")]
    assert merge_hybrid_records(cc, wb, "url_period", "day")[1]["wayback_dropped"] == 0
    assert merge_hybrid_records(cc, wb, "url_period", "year")[1]["wayback_dropped"] == 1


def test_hybrid_digest_mode_drops_identical_payloads_only():
    cc = [_cc("https://example.com/a", "20200310000000", digest="SAME")]
    wb = [
        _wb("https://other.example.org/zzz", "20150101000000", digest="SAME"),  # same bytes, any URL/date
        _wb("https://example.com/a", "20200310000000", digest="DIFFERENT"),     # same URL/date, other bytes
        _wb("https://example.com/c", "20200310000000", digest=""),               # no digest: never dropped
    ]
    merged, stats = merge_hybrid_records(cc, wb, mode="digest")
    assert stats["wayback_dropped"] == 1 and stats["final"] == 3
    assert {r.digest for r in merged[1:]} == {"DIFFERENT", ""}


def test_hybrid_merge_rejects_unknown_mode():
    with pytest.raises(ValueError):
        merge_hybrid_records([], [], mode="fuzzy")


# ---------------------------------------------------------------------------
# Storage: digest reuse, content-hash duplicates
# ---------------------------------------------------------------------------

PROJECT_A, PROJECT_B = 1, 2


@pytest.fixture(autouse=True)
def _empty_tables(session):
    """The shared test database persists between tests; start each one from empty tables."""
    for model in (PageErrorLog, ProjectPage, ScrapePage, Page):
        session.execute(delete(model))
    session.commit()


def _scrape_page(session, url="https://example.com/a", ts="20200101000000", digest="DIGEST1", **kw):
    sp = ScrapePage(
        domain_id=10, scrape_session_id=5, original_url=url, content_url=f"https://web.archive.org/web/{ts}if_/{url}",
        unix_timestamp=ts, mime_type="text/html", status_code=200, digest_hash=digest, **kw,
    )
    session.add(sp)
    session.flush()
    return sp


def _extracted(text="word " * 80, **kw):
    return {"title": "T", "text": text, "markdown": text, "description": None, "author": None,
            "language": "en", "word_count": len(text.split()), "extraction_method": "test",
            "extraction_time": 0.5, **kw}


def test_content_hash_ignores_whitespace_but_not_words():
    assert compute_content_hash("a  b\n c") == compute_content_hash("a b c")
    assert compute_content_hash("a b c") != compute_content_hash("a b d")


def test_extraction_writes_text_once_and_sets_digest_and_hash(session):
    sp = _scrape_page(session)
    outcome = persist_extracted_page(session, sp, PROJECT_A, _extracted())
    session.commit()

    page = session.get(Page, outcome.page_id)
    assert outcome.kind == "created"
    assert page.content and page.extracted_text is None and page.markdown_content is None
    assert page.text_content == page.content
    assert page.capture_digest == "DIGEST1"
    assert page.content_hash == compute_content_hash(page.content)
    assert sp.page_id == page.id and sp.status == ScrapePageStatus.COMPLETED
    assert sp.extracted_text is None and sp.extracted_content is None and sp.markdown_content is None
    links = session.execute(select(ProjectPage).where(ProjectPage.page_id == page.id)).scalars().all()
    assert [link.project_id for link in links] == [PROJECT_A]


def test_digest_reuse_links_other_project_without_new_page(session):
    first = _scrape_page(session)
    created = persist_extracted_page(session, first, PROJECT_A, _extracted())
    session.commit()

    # Another project discovers the same capture (different timestamp, identical payload digest).
    second = _scrape_page(session, ts="20200202000000", digest="DIGEST1")
    assert find_pages_by_digests(session, ["DIGEST1", "OTHER", ""]) == {"DIGEST1": created.page_id}
    linked = link_by_digest(session, second, PROJECT_B)
    session.commit()

    assert linked == created.page_id
    assert second.status == ScrapePageStatus.COMPLETED and second.page_id == created.page_id
    assert second.error_type == ERROR_DIGEST_REUSE and "identical archive payload digest" in second.error_message
    assert session.execute(select(Page)).scalars().all().__len__() == 1
    projects = {link.project_id for link in session.execute(
        select(ProjectPage).where(ProjectPage.page_id == created.page_id)).scalars()}
    assert projects == {PROJECT_A, PROJECT_B}

    # Linking again must not duplicate the junction row.
    third = _scrape_page(session, ts="20200303000000", digest="DIGEST1")
    link_by_digest(session, third, PROJECT_B)
    session.commit()
    assert session.execute(select(ProjectPage).where(ProjectPage.project_id == PROJECT_B)).scalars().all().__len__() == 1


def test_digest_without_match_links_nothing(session):
    sp = _scrape_page(session, digest="NEVER-SEEN")
    assert link_by_digest(session, sp, PROJECT_A) is None
    assert sp.status == ScrapePageStatus.PENDING and sp.page_id is None


def test_same_url_identical_content_reuses_page_as_duplicate_content(session):
    first = _scrape_page(session, ts="20200101000000", digest="D1")
    created = persist_extracted_page(session, first, PROJECT_A, _extracted())
    session.commit()

    # Later capture of the same URL: different payload digest (markup changed), same text.
    again = _scrape_page(session, ts="20210101000000", digest="D2")
    outcome = persist_extracted_page(session, again, PROJECT_A, _extracted("word   " * 80))
    session.commit()

    assert outcome.kind == "duplicate_content" and outcome.page_id == created.page_id
    assert again.status == ScrapePageStatus.COMPLETED and again.page_id == created.page_id
    assert again.error_type == ERROR_DUPLICATE_CONTENT
    assert len(session.execute(select(Page)).scalars().all()) == 1


def test_same_text_on_different_url_is_a_new_page(session):
    first = _scrape_page(session, url="https://example.com/a", digest="D1")
    persist_extracted_page(session, first, PROJECT_A, _extracted())
    other = _scrape_page(session, url="https://example.com/b", ts="20200101000001", digest="D3")
    outcome = persist_extracted_page(session, other, PROJECT_A, _extracted())
    session.commit()
    assert outcome.kind == "created"
    assert len(session.execute(select(Page)).scalars().all()) == 2


def test_markdown_kept_only_when_different_from_text(session):
    sp = _scrape_page(session)
    out = persist_extracted_page(session, sp, PROJECT_A, _extracted(markdown="# Heading\n" + "word " * 80))
    session.commit()
    assert session.get(Page, out.page_id).markdown_content.startswith("# Heading")


# ---------------------------------------------------------------------------
# Failure honesty, backoff, re-queue, reaper
# ---------------------------------------------------------------------------

NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


def test_backoff_doubles_and_honours_retry_after_and_cap():
    base = settings.SCRAPE_RETRY_BASE_DELAY_SECONDS
    assert compute_retry_delay(1) == base
    assert compute_retry_delay(2) == base * 2
    assert compute_retry_delay(3) == base * 4
    assert compute_retry_delay(1, retry_after=base * 10) == base * 10
    assert compute_retry_delay(30) == settings.SCRAPE_RETRY_MAX_DELAY_SECONDS


def test_retryable_failure_records_type_count_and_next_retry(session):
    sp = _scrape_page(session)
    record_failure(session, sp, "rate_limited", "HTTP 429", retry_after=900, status_code=429,
                   fetch_time=1.25, now=NOW)
    session.commit()

    assert sp.status == ScrapePageStatus.FAILED
    assert (sp.error_type, sp.error_message, sp.retry_count, sp.fetch_time) == ("rate_limited", "HTTP 429", 1, 1.25)
    assert sp.next_retry_at.replace(tzinfo=timezone.utc) == NOW + timedelta(seconds=900)
    log = session.execute(select(PageErrorLog)).scalars().one()
    assert log.error_type == "rate_limited" and log.is_recoverable and log.error_details["status_code"] == 429


def test_non_retryable_failure_is_not_scheduled(session):
    sp = _scrape_page(session)
    record_failure(session, sp, "http_error", "HTTP 404", retryable=False, now=NOW)
    assert sp.status == ScrapePageStatus.FAILED and sp.next_retry_at is None
    assert requeue_due_failures(session, now=NOW + timedelta(days=30)) == []


def test_retries_stop_after_max_retries(session):
    sp = _scrape_page(session, retry_count=settings.SCRAPE_MAX_RETRIES - 1)
    record_failure(session, sp, "connection_error", "reset", now=NOW)
    assert sp.retry_count == settings.SCRAPE_MAX_RETRIES and sp.next_retry_at is None


def test_requeue_only_due_rows_in_batches_oldest_first(session):
    due_old = _scrape_page(session, url="https://e.com/1", ts="20200101000001")
    due_new = _scrape_page(session, url="https://e.com/2", ts="20200101000002")
    not_due = _scrape_page(session, url="https://e.com/3", ts="20200101000003")
    for sp, minutes in ((due_old, 30), (due_new, 10), (not_due, -60)):
        record_failure(session, sp, "connection_error", "reset", now=NOW - timedelta(minutes=minutes) - timedelta(seconds=300))
        sp.next_retry_at = NOW - timedelta(minutes=minutes)
    session.commit()

    batch = requeue_due_failures(session, limit=1, now=NOW)
    assert [r.id for r in batch] == [due_old.id]
    assert due_old.status == ScrapePageStatus.PENDING and due_old.next_retry_at is None

    rest = requeue_due_failures(session, limit=10, now=NOW)
    assert [r.id for r in rest] == [due_new.id]
    assert not_due.status == ScrapePageStatus.FAILED  # its retry time is still in the future


def test_reaper_resets_stale_in_progress_and_fails_exhausted(session):
    stale = _scrape_page(session, url="https://e.com/1", ts="20200101000001",
                         status=ScrapePageStatus.IN_PROGRESS, last_attempt_at=NOW - timedelta(minutes=45))
    exhausted = _scrape_page(session, url="https://e.com/2", ts="20200101000002",
                             status=ScrapePageStatus.IN_PROGRESS, last_attempt_at=NOW - timedelta(hours=3),
                             retry_count=settings.SCRAPE_MAX_RETRIES - 1)
    fresh = _scrape_page(session, url="https://e.com/3", ts="20200101000003",
                         status=ScrapePageStatus.IN_PROGRESS, last_attempt_at=NOW - timedelta(minutes=5))
    session.commit()

    result = reap_stale_in_progress(session, now=NOW)

    assert result["reaped"] == 2 and result["failed"] == 1 and result["reset_ids"] == [stale.id]
    assert stale.status == ScrapePageStatus.PENDING and stale.retry_count == 1
    assert exhausted.status == ScrapePageStatus.FAILED and exhausted.error_type == ERROR_STALE_IN_PROGRESS
    assert exhausted.next_retry_at is None
    assert fresh.status == ScrapePageStatus.IN_PROGRESS


def test_fetch_error_dict_from_extractor_is_typed():
    """_extract_one_record turns an ArchiveFetchError into a typed diagnostic, never an empty-content skip."""
    import asyncio
    from app.services.archive_fetch_errors import ArchiveRateLimited
    from app.tasks.firecrawl_scraping import _extract_one_record

    class Extractor:
        async def extract_content(self, rec):
            raise ArchiveRateLimited("HTTP 429", url=rec.original_url, status_code=429, retry_after=120)

    rec = _wb("https://example.com/a", "20200101000000")
    out = asyncio.run(_extract_one_record(Extractor(), rec))
    assert out["_fetch_error"] and out["error_type"] == "rate_limited"
    assert out["retryable"] is True and out["retry_after"] == 120 and out["status_code"] == 429
    assert out["fetch_time"] >= 0


# ---------------------------------------------------------------------------
# The processing loop: in-run digest dedup, typed failures
# ---------------------------------------------------------------------------

def test_processing_loop_fetches_identical_digest_once_and_records_typed_failures(session, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from app.models.shared_pages import Page as PageModel
    from app.services.archive_fetch_errors import ArchiveConnectionError
    from app.tasks import firecrawl_scraping as fs

    fetched = []

    class Extractor:
        async def extract_content(self, rec):
            fetched.append(rec.original_url)
            await asyncio.sleep(0.01)
            if rec.original_url.endswith("/blocked"):
                raise ArchiveConnectionError("connection reset", url=rec.original_url)
            text = "alpha beta " * 40 + rec.original_url
            return SimpleNamespace(text=text, markdown=text, title="T", word_count=len(text.split()),
                                   meta_description=None, author=None, language="en", source_url=None,
                                   status_code=200, error=None, extraction_method="test", extraction_time=0.1)

    async def no_reindex(db, page_ids):
        return {"indexed": 0}

    monkeypatch.setattr(fs, "get_content_extraction_service", lambda: Extractor())
    monkeypatch.setattr(fs, "reindex_pages_and_mark", no_reindex)

    # Same capture digest under three timestamps (one fetch expected), one other page, one that fails.
    same = [_scrape_page(session, url="https://example.com/same", ts=f"2020010100000{i}", digest="SAMEDIGEST")
            for i in range(3)]
    other = _scrape_page(session, url="https://example.com/other", ts="20200201000000", digest="OTHERDIGEST")
    blocked = _scrape_page(session, url="https://example.com/blocked", ts="20200301000000", digest="BLOCKEDDIGEST")
    session.commit()
    ids = [sp.id for sp in same] + [other.id, blocked.id]

    domain = SimpleNamespace(id=10, project_id=PROJECT_A, domain_name="example.com")
    task_self = SimpleNamespace(update_state=lambda **kw: None)
    created, failed = asyncio.run(fs._process_individual_firecrawl(
        session, None, domain, task_self, 5, scrape_page_ids=ids))
    session.commit()

    assert sorted(fetched) == ["https://example.com/blocked", "https://example.com/other", "https://example.com/same"]
    assert (created, failed) == (4, 1)
    pages = session.execute(select(PageModel)).scalars().all()
    assert len(pages) == 2
    page_ids = {sp.page_id for sp in same}
    assert len(page_ids) == 1 and None not in page_ids
    assert sorted(sp.error_type or "" for sp in same) == ["", ERROR_DIGEST_REUSE, ERROR_DIGEST_REUSE]

    session.refresh(blocked)
    assert blocked.status == ScrapePageStatus.FAILED and blocked.error_type == "connection_error"
    assert blocked.retry_count == 1 and blocked.next_retry_at is not None and blocked.fetch_time is not None
    assert blocked.page_id is None


# ---------------------------------------------------------------------------
# Legacy skip reclassification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message,details,expected", [
    ("Low content: 8 words", {"extraction_method": "extraction_failed_connection_error", "title": "Extraction Failed",
                              "text_preview": "Content extraction failed (connection_error): All connection attempts failed"},
     ("connection_error", True)),
    ("Low content", {"extraction_method": "extraction_failed_http_error",
                     "text_preview": "Content extraction failed (http_error): All rotating FlareSolverr exits blocked/failed"},
     ("rate_limited", True)),
    ("Low content", {"extraction_method": "extraction_failed_http_error",
                     "text_preview": "Content extraction failed (http_error): HTTP 404"}, ("http_error", False)),
    ("Low content", {"extraction_method": "intelligent_trafilatura", "title": "429 Too Many Requests",
                     "text_preview": "429 Too Many Requests\nnginx"}, ("rate_limited", True)),
    ("Low content", {"extraction_method": "intelligent_trafilatura", "title": "New Tab", "text_preview": ""},
     ("block_page", True)),
    ("Low content", {"extraction_method": "intelligent_trafilatura", "title": "Category:Brazil - Wikipedia",
                     "text_preview": "Subcategories\nThis category has the following 16 subcategories"}, None),
    (None, None, None),
])
def test_classify_legacy_skip(message, details, expected):
    from app.scripts.reclassify_legacy_skips import classify_legacy_skip
    assert classify_legacy_skip(message, details) == expected
