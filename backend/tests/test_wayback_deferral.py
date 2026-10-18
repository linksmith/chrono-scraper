"""
A page the Wayback limiter would not let out is DEFERRED, not failed: it goes back to
pending with next_retry_at, retry_count untouched, and the processing loop stops
dispatching Wayback pages while all Wayback traffic is paused.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import fakeredis
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.config import settings
from app.models.scraping import PageErrorLog, ScrapePage, ScrapePageStatus
from app.models.shared_pages import Page, ProjectPage
from app.services import archive_rate_limiter as arl
from app.services import egress_rotation as egress
from app.services.archive_fetch_errors import ArchiveConnectionError, ArchiveDeferred
from app.services.page_persistence import defer_scrape_page, requeue_due_failures
from app.tasks import firecrawl_scraping as fs

PROJECT = 1


@pytest.fixture(autouse=True)
def _empty_tables(session):
    for model in (PageErrorLog, ProjectPage, ScrapePage, Page):
        session.execute(delete(model))
    session.commit()


@pytest_asyncio.fixture
async def limiter(monkeypatch):
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(egress, "get_redis", lambda decode_responses=True: client)
    lim = arl.ArchiveRateLimiter(prefix="test_defer")
    monkeypatch.setattr(arl, "_limiter", lim)
    monkeypatch.setattr(settings, "WAYBACK_ACQUIRE_TIMEOUT", 5.0)
    yield lim
    await client.flushall()
    await client.aclose()


def make_page(session, n, wayback=True, **kw):
    url = f"https://example.com/p{n}"
    ts = f"2020010100{n:04d}"
    content_url = f"https://web.archive.org/web/{ts}id_/{url}" if wayback else f"https://data.commoncrawl.org/{ts}"
    extra = {} if wayback else {"warc_filename": "crawl-data/x.warc.gz", "warc_offset": 1, "warc_length": 2}
    sp = ScrapePage(
        domain_id=10, scrape_session_id=5, original_url=url, content_url=content_url,
        unix_timestamp=ts, mime_type="text/html", status_code=200, digest_hash=f"DIGEST{n}", **extra, **kw,
    )
    session.add(sp)
    session.flush()
    return sp


def good_result(url):
    text = "alpha beta " * 40 + url
    return SimpleNamespace(
        text=text, markdown=text, title="T", word_count=len(text.split()), meta_description=None,
        author=None, language="en", source_url=None, status_code=200, error=None,
        extraction_method="test", extraction_time=0.1,
    )


async def run_loop(session, ids, monkeypatch, extractor):
    async def no_reindex(db, page_ids):
        return {"indexed": 0}

    monkeypatch.setattr(fs, "get_content_extraction_service", lambda: extractor)
    monkeypatch.setattr(fs, "reindex_pages_and_mark", no_reindex)
    domain = SimpleNamespace(id=10, project_id=PROJECT, domain_name="example.com")
    task_self = SimpleNamespace(update_state=lambda **kw: None)
    result = await fs._process_individual_firecrawl(session, None, domain, task_self, 5, scrape_page_ids=ids)
    session.commit()
    return result


# ------------------------------------------------------------------ deferral


@pytest.mark.asyncio
async def test_deferral_does_not_increment_retry_count_or_fail_the_page(session, limiter, monkeypatch):
    sp = make_page(session, 1, retry_count=2)
    session.commit()

    class Extractor:
        async def extract_content(self, rec):
            raise ArchiveDeferred("Wayback paused for content (retry in 120s)", url=rec.original_url, retry_after=120.0)

    before = datetime.now(timezone.utc)
    created, failed = await run_loop(session, [sp.id], monkeypatch, Extractor())

    session.refresh(sp)
    assert (created, failed) == (0, 0)
    assert sp.status == ScrapePageStatus.PENDING
    assert sp.retry_count == 2  # unchanged: no request was sent, so no attempt
    resume = sp.next_retry_at if sp.next_retry_at.tzinfo else sp.next_retry_at.replace(tzinfo=timezone.utc)
    assert before + timedelta(seconds=115) <= resume <= before + timedelta(seconds=130)
    assert session.execute(select(PageErrorLog)).scalars().all() == []  # not logged as an error


@pytest.mark.asyncio
async def test_real_connection_error_still_counts_as_an_attempt(session, limiter, monkeypatch):
    sp = make_page(session, 1, retry_count=2)
    session.commit()

    class Extractor:
        async def extract_content(self, rec):
            raise ArchiveConnectionError("reset", url=rec.original_url)

    await run_loop(session, [sp.id], monkeypatch, Extractor())
    session.refresh(sp)
    assert sp.status == ScrapePageStatus.FAILED and sp.retry_count == 3


def test_deferred_rows_are_released_by_the_beat_requeue_when_due(session):
    due = make_page(session, 1, retry_count=1)
    later = make_page(session, 2, retry_count=1)
    now = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)
    defer_scrape_page(due, 60, now=now)
    defer_scrape_page(later, 3600, now=now)
    session.commit()

    assert requeue_due_failures(session, now=now + timedelta(seconds=30)) == []
    released = requeue_due_failures(session, now=now + timedelta(seconds=61))
    assert [r.id for r in released] == [due.id]
    assert due.status == ScrapePageStatus.PENDING and due.next_retry_at is None and due.retry_count == 1
    assert later.next_retry_at is not None


# ------------------------------------------------------------------ pause: stop dispatching


@pytest.mark.asyncio
async def test_loop_does_not_dispatch_wayback_pages_while_paused_and_defers_them(session, limiter, monkeypatch):
    """A long pause: nothing is sent to archive.org, nothing fails, the rows wait for the pause end."""
    wb = [make_page(session, n) for n in range(1, 6)]
    cc = make_page(session, 6, wayback=False)
    session.commit()
    await limiter.pause(3600, "test: IA asked for a pause")
    fetched = []

    class Extractor:
        async def extract_content(self, rec):
            fetched.append(rec.original_url)
            return good_result(rec.original_url)

    created, failed = await run_loop(session, [sp.id for sp in wb] + [cc.id], monkeypatch, Extractor())

    assert fetched == [cc.original_url]  # Common Crawl is not affected by the Wayback pause
    assert (created, failed) == (1, 0)  # in particular: NOT drained into failures
    for sp in wb:
        session.refresh(sp)
        assert sp.status == ScrapePageStatus.PENDING and sp.retry_count == 0
        resume = sp.next_retry_at if sp.next_retry_at.tzinfo else sp.next_retry_at.replace(tzinfo=timezone.utc)
        assert resume >= datetime.now(timezone.utc) + timedelta(seconds=3500)  # ~ the pause end


@pytest.mark.asyncio
async def test_loop_waits_out_a_short_pause_then_fetches_everything(session, limiter, monkeypatch):
    wb = [make_page(session, n) for n in range(1, 4)]
    session.commit()
    await limiter.pause(0.6, "test: short pause")
    fetched_at = []
    loop = asyncio.get_event_loop()
    started = loop.time()

    class Extractor:
        async def extract_content(self, rec):
            fetched_at.append(loop.time() - started)
            return good_result(rec.original_url)

    created, failed = await run_loop(session, [sp.id for sp in wb], monkeypatch, Extractor())

    assert (created, failed) == (3, 0)
    assert min(fetched_at) >= 0.5  # nothing went out before the pause ended


# ------------------------------------------------------------------ thin pages


@pytest.mark.asyncio
@pytest.mark.parametrize("text,words", [("", 0), ("tiny page", 2)])
async def test_thin_page_after_a_successful_fetch_is_skipped_and_not_retryable(session, limiter, monkeypatch, text, words):
    """'Extraction failed or returned minimal content' is not a fetch_error: skipped, final."""
    from app.services.content_extraction_service import MINIMAL_CONTENT_ERROR

    sp = make_page(session, 1)
    session.commit()

    class Extractor:
        async def extract_content(self, rec):
            return SimpleNamespace(
                text=text, markdown="", title="", word_count=words, meta_description=None, author=None,
                language=None, source_url=None, status_code=200, extraction_method="intelligent_x",
                extraction_time=0.1, fetch_time=0.4,
                error=f"{MINIMAL_CONTENT_ERROR}: insufficient word count ({words} <= 50)",
            )

    await run_loop(session, [sp.id], monkeypatch, Extractor())

    session.refresh(sp)
    assert sp.status == ScrapePageStatus.SKIPPED
    assert sp.error_type == "insufficient_content"
    assert sp.next_retry_at is None
    assert requeue_due_failures(session, now=datetime.now(timezone.utc) + timedelta(days=365)) == []
    assert session.execute(select(PageErrorLog)).scalars().all() == []


@pytest.mark.asyncio
async def test_empty_result_with_another_error_is_still_a_retryable_fetch_error():
    class Extractor:
        async def extract_content(self, rec):
            return SimpleNamespace(text="", word_count=0, error="Connection reset by peer", fetch_time=0.1)

    out = await fs._extract_one_record(Extractor(), SimpleNamespace(original_url="https://example.com/x"))
    assert out["_fetch_error"] and out["error_type"] == "fetch_error" and out["retryable"] is True
