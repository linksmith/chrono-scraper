"""
Persistence helpers for scrape results (sync SQLAlchemy sessions, as used by the Celery tasks).

- Extracted text is written once, on the shared Page; ScrapePage only points at it (page_id).
- A capture whose archive payload digest already exists as a Page (any project) is linked,
  not fetched again.
- Fetch failures are recorded honestly with exponential-backoff retry state, re-queued at a
  low rate by ``requeue_due_failures`` and unstuck by ``reap_stale_in_progress``.
"""
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import select, update

from app.core.config import settings
from app.models.scraping import PageErrorLog, ScrapePage, ScrapePageStatus
from app.models.shared_pages import Page, ProjectPage

logger = logging.getLogger(__name__)

ERROR_DIGEST_REUSE = "digest_reuse"
ERROR_DUPLICATE_CONTENT = "duplicate_content"
ERROR_EXISTING_PAGE = "existing_page"
ERROR_STALE_IN_PROGRESS = "stale_in_progress"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_content_hash(text: str) -> str:
    """sha256 of the whitespace-normalized text (same words in the same order => same hash)."""
    normalized = " ".join((text or "").split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Page lookup / linking
# ---------------------------------------------------------------------------

def find_page_by_digest(db, digest: Optional[str]) -> Optional[uuid.UUID]:
    """Id of any stored Page extracted from a capture with this payload digest."""
    if not digest:
        return None
    return db.execute(
        select(Page.id).where(Page.capture_digest == digest).order_by(Page.created_at).limit(1)
    ).scalars().first()


def find_pages_by_digests(db, digests: Iterable[str]) -> Dict[str, uuid.UUID]:
    """Map each digest that already exists as a Page (any project, any age) to that Page's id."""
    wanted = sorted({d for d in digests if d})
    found: Dict[str, uuid.UUID] = {}
    for start in range(0, len(wanted), 1000):
        rows = db.execute(
            select(Page.capture_digest, Page.id)
            .where(Page.capture_digest.in_(wanted[start:start + 1000]))
            .order_by(Page.created_at.desc())
        ).all()
        for digest, page_id in rows:
            found[digest] = page_id  # oldest page wins (rows arrive newest first)
    if wanted:
        logger.info("Digest lookup: %d/%d capture digests already stored as pages", len(found), len(wanted))
    return found


def find_page_by_url_timestamp(db, url: str, unix_timestamp: Optional[str]) -> Optional[uuid.UUID]:
    ts = int(unix_timestamp) if unix_timestamp and str(unix_timestamp).isdigit() else 0
    return db.execute(
        select(Page.id).where(Page.url == url, Page.unix_timestamp == ts).limit(1)
    ).scalars().first()


def find_page_by_content_hash(db, url: str, content_hash: str) -> Optional[uuid.UUID]:
    return db.execute(
        select(Page.id).where(Page.url == url, Page.content_hash == content_hash)
        .order_by(Page.created_at).limit(1)
    ).scalars().first()


def ensure_project_page(db, project_id: int, page_id: uuid.UUID, domain_id: Optional[int]) -> bool:
    """Create the ProjectPage junction row if missing. Returns True when one was created.

    Without it the page is invisible to search (Meilisearch indexing joins on project_pages).
    """
    exists = db.execute(
        select(ProjectPage.id).where(ProjectPage.project_id == project_id, ProjectPage.page_id == page_id).limit(1)
    ).scalars().first()
    if exists:
        return False
    db.add(ProjectPage(
        project_id=project_id,
        page_id=page_id,
        domain_id=domain_id,
        review_status="pending",
        priority_level="medium",
        is_starred=False,
        tags=[],
        is_duplicate=False,
        added_at=datetime.utcnow(),
    ))
    db.flush()
    return True


def mark_linked(scrape_page: ScrapePage, page_id: uuid.UUID, error_type: Optional[str], note: Optional[str]) -> None:
    """Resolve a ScrapePage to an existing Page without touching the database.

    ``error_type``/``note`` record why no fetch/extraction was needed (digest_reuse,
    duplicate_content, existing_page).
    """
    scrape_page.page_id = page_id
    scrape_page.status = ScrapePageStatus.COMPLETED
    scrape_page.completed_at = datetime.utcnow()
    scrape_page.error_type = error_type
    scrape_page.error_message = note
    scrape_page.next_retry_at = None


def link_scrape_page(db, scrape_page: ScrapePage, page_id: uuid.UUID, project_id: int,
                     error_type: Optional[str], note: Optional[str]) -> bool:
    """mark_linked() plus the ProjectPage junction. Returns True if a ProjectPage was created."""
    mark_linked(scrape_page, page_id, error_type, note)
    created = ensure_project_page(db, project_id, page_id, scrape_page.domain_id)
    logger.info(
        "Linked scrape_page=%s url=%s to page=%s (%s) project=%s project_page_created=%s",
        scrape_page.id, scrape_page.original_url, page_id, error_type, project_id, created,
    )
    return created


def link_by_digest(db, scrape_page: ScrapePage, project_id: int) -> Optional[uuid.UUID]:
    """If a Page with this capture's digest exists, link to it and return its id."""
    page_id = find_page_by_digest(db, scrape_page.digest_hash)
    if page_id is None:
        return None
    link_scrape_page(db, scrape_page, page_id, project_id, ERROR_DIGEST_REUSE,
                     f"Reused page {page_id}: identical archive payload digest {scrape_page.digest_hash}")
    return page_id


@dataclass
class PersistOutcome:
    page_id: uuid.UUID
    kind: str  # "created" | "duplicate_content" | "existing_page"
    project_page_created: bool

    @property
    def created_page(self) -> bool:
        return self.kind == "created"


def _parse_capture_date(unix_timestamp: Optional[str], fallback: Optional[datetime]) -> Optional[datetime]:
    ts = str(unix_timestamp or "")
    if len(ts) >= 14:
        try:
            return datetime.strptime(ts[:14], "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return fallback


def persist_extracted_page(db, scrape_page: ScrapePage, project_id: int,
                           extracted: Dict[str, Any]) -> PersistOutcome:
    """
    Store one successful extraction.

    ``extracted`` keys: title, text, markdown, description, author, language, word_count,
    extraction_method, extraction_time (+ optional quality_score, status_code).
    The text goes on Page.content only; ScrapePage keeps metadata and page_id.
    """
    text = extracted["text"]
    content_hash = compute_content_hash(text)

    scrape_page.title = extracted.get("title")
    scrape_page.extraction_method = extracted.get("extraction_method")
    scrape_page.extraction_time = extracted.get("extraction_time")

    duplicate = find_page_by_content_hash(db, scrape_page.original_url, content_hash)
    if duplicate is not None:
        created = link_scrape_page(
            db, scrape_page, duplicate, project_id, ERROR_DUPLICATE_CONTENT,
            f"Same URL already stored with identical content (page {duplicate})",
        )
        return PersistOutcome(duplicate, "duplicate_content", created)

    existing = find_page_by_url_timestamp(db, scrape_page.original_url, scrape_page.unix_timestamp)
    if existing is not None:
        created = link_scrape_page(db, scrape_page, existing, project_id, ERROR_EXISTING_PAGE,
                                   f"Page {existing} already exists for this URL and timestamp")
        return PersistOutcome(existing, "existing_page", created)

    markdown = extracted.get("markdown")
    page = Page(
        url=scrape_page.original_url,
        content_url=scrape_page.content_url,
        title=extracted.get("title"),
        content=text,
        # Only keep markdown when it adds something over the plain text.
        markdown_content=markdown if markdown and markdown != text else None,
        unix_timestamp=int(scrape_page.unix_timestamp) if scrape_page.unix_timestamp else 0,
        mime_type=scrape_page.mime_type,
        status_code=extracted.get("status_code") or scrape_page.status_code,
        meta_description=extracted.get("description"),
        author=extracted.get("author"),
        language=extracted.get("language"),
        quality_score=extracted.get("quality_score"),
        word_count=extracted.get("word_count"),
        character_count=len(text),
        content_length=scrape_page.content_length,
        capture_date=_parse_capture_date(scrape_page.unix_timestamp, scrape_page.first_seen_at),
        content_hash=content_hash,
        capture_digest=scrape_page.digest_hash,
        processed=True,
        indexed=False,
    )
    db.add(page)
    db.flush()  # assigns the id used by the junction row

    scrape_page.page_id = page.id
    scrape_page.status = ScrapePageStatus.COMPLETED
    scrape_page.completed_at = datetime.utcnow()
    scrape_page.error_type = None
    scrape_page.error_message = None
    scrape_page.next_retry_at = None
    created = ensure_project_page(db, project_id, page.id, scrape_page.domain_id)
    return PersistOutcome(page.id, "created", created)


async def reindex_pages_and_mark(db, page_ids: Iterable[uuid.UUID]) -> Dict[str, Any]:
    """Re-sync pages with Meilisearch (await directly; never nest run_async_in_sync) and flag indexed."""
    ids = list(dict.fromkeys(page_ids))
    if not ids:
        return {"indexed": 0, "deleted": 0, "failed": 0, "total_requested": 0}
    from app.core.database import AsyncSessionLocal
    from app.services.shared_pages_meilisearch import SharedPagesMeilisearchService

    async with AsyncSessionLocal() as async_db:
        result = await SharedPagesMeilisearchService(async_db).reindex_pages(ids)
    if result.get("indexed", 0) > 0:
        db.execute(update(Page).where(Page.id.in_(ids)).values(indexed=True))
        db.commit()
    logger.info("Meilisearch reindex after scrape: %s", result)
    return result


# ---------------------------------------------------------------------------
# Failures, retries, reaper
# ---------------------------------------------------------------------------

def compute_retry_delay(retry_count: int, retry_after: Optional[float] = None) -> float:
    """Seconds until the next attempt: base * 2^(attempt-1), at least Retry-After, capped."""
    backoff = settings.SCRAPE_RETRY_BASE_DELAY_SECONDS * (2 ** max(0, retry_count - 1))
    return min(settings.SCRAPE_RETRY_MAX_DELAY_SECONDS, max(backoff, float(retry_after or 0)))


def record_failure(db, scrape_page: ScrapePage, error_type: str, message: str, *, retryable: bool = True,
                   retry_after: Optional[float] = None, status_code: Optional[int] = None,
                   fetch_time: Optional[float] = None, now: Optional[datetime] = None) -> None:
    """Mark a ScrapePage failed and, if retryable and attempts remain, schedule the backoff retry."""
    now = now or utcnow()
    scrape_page.status = ScrapePageStatus.FAILED
    scrape_page.error_type = error_type
    scrape_page.error_message = message[:2000]
    scrape_page.retry_count = (scrape_page.retry_count or 0) + 1
    if fetch_time is not None:
        scrape_page.fetch_time = fetch_time

    retry_at = None
    delay: Optional[float] = None
    if retryable and scrape_page.retry_count < settings.SCRAPE_MAX_RETRIES:
        delay = compute_retry_delay(scrape_page.retry_count, retry_after)
        retry_at = now + timedelta(seconds=delay)
    scrape_page.next_retry_at = retry_at

    if scrape_page.id is not None:
        db.add(PageErrorLog(
            scrape_page_id=scrape_page.id,
            scrape_session_id=scrape_page.scrape_session_id,
            error_type=error_type,
            error_message=message[:2000],
            error_details={"status_code": status_code, "retry_count": scrape_page.retry_count,
                           "retry_after": retry_after},
            wayback_url=scrape_page.content_url or "",
            original_url=scrape_page.original_url,
            is_recoverable=retry_at is not None,
            suggested_retry_delay=int(delay) if delay is not None else None,
            retry_scheduled_at=retry_at,
        ))
    logger.warning(
        "Fetch failed scrape_page=%s url=%s type=%s retry_count=%d next_retry_at=%s: %s",
        scrape_page.id, scrape_page.original_url, error_type, scrape_page.retry_count,
        retry_at.isoformat() if retry_at else None, message[:200],
    )


def requeue_due_failures(db, limit: Optional[int] = None, now: Optional[datetime] = None) -> List[ScrapePage]:
    """
    Flip due retryable failed rows back to pending (oldest due first) and return them.

    Rows are locked with SKIP LOCKED so overlapping beat runs never pick the same row.
    """
    now = now or utcnow()
    limit = limit or settings.SCRAPE_RETRY_BATCH
    rows = db.execute(
        select(ScrapePage)
        .where(
            ScrapePage.status == ScrapePageStatus.FAILED,
            ScrapePage.next_retry_at.is_not(None),
            ScrapePage.next_retry_at <= now,
            ScrapePage.retry_count < settings.SCRAPE_MAX_RETRIES,
        )
        .order_by(ScrapePage.next_retry_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).scalars().all()
    for row in rows:
        row.status = ScrapePageStatus.PENDING
        row.next_retry_at = None
    db.commit()
    if rows:
        logger.info("Re-queued %d failed scrape pages for retry", len(rows))
    return list(rows)


def reap_stale_in_progress(db, now: Optional[datetime] = None,
                           stale_minutes: Optional[int] = None) -> Dict[str, Any]:
    """
    Rows stuck in_progress longer than the stale window (worker died mid-fetch) go back to
    pending, or to failed once they have used up SCRAPE_MAX_RETRIES attempts.
    """
    now = now or utcnow()
    cutoff = now - timedelta(minutes=stale_minutes or settings.SCRAPE_STALE_IN_PROGRESS_MINUTES)
    rows = db.execute(
        select(ScrapePage)
        .where(
            ScrapePage.status == ScrapePageStatus.IN_PROGRESS,
            (ScrapePage.last_attempt_at.is_(None)) | (ScrapePage.last_attempt_at < cutoff),
        )
        .with_for_update(skip_locked=True)
    ).scalars().all()
    reset_ids: List[int] = []
    failed = 0
    for row in rows:
        row.retry_count = (row.retry_count or 0) + 1
        if row.retry_count >= settings.SCRAPE_MAX_RETRIES:
            row.status = ScrapePageStatus.FAILED
            row.error_type = ERROR_STALE_IN_PROGRESS
            row.error_message = "Worker stopped while processing this page; retries exhausted"
            row.next_retry_at = None
            failed += 1
        else:
            row.status = ScrapePageStatus.PENDING
            reset_ids.append(row.id)
    db.commit()
    if rows:
        logger.warning("Reaped %d stale in_progress scrape pages (reset=%d, failed=%d)",
                       len(rows), len(reset_ids), failed)
    return {"reaped": len(rows), "reset_to_pending": len(reset_ids), "failed": failed, "reset_ids": reset_ids}


def group_ids_by_session(rows: Sequence[ScrapePage]) -> Dict[Any, List[int]]:
    """{(domain_id, scrape_session_id): [scrape_page ids]} for dispatching retries."""
    grouped: Dict[Any, List[int]] = {}
    for row in rows:
        grouped.setdefault((row.domain_id, row.scrape_session_id), []).append(row.id)
    return grouped
