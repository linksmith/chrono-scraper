"""
Simplified scraping tasks for Celery
This module provides retry/reprocessing tasks for individual pages
that use the real content extraction pipeline.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlmodel import select

from app.tasks.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.project import (
    Domain,
    ScrapeSession,
    ScrapeSessionStatus,
    DomainStatus,
)
from app.core.config import settings
from app.services.websocket_service import (
    broadcast_page_progress_sync,
    broadcast_cdx_discovery_sync,
    broadcast_processing_stage_sync,
    broadcast_session_stats_sync
)
from app.models.scraping import ScrapePage, ScrapePageStatus

logger = logging.getLogger(__name__)


def _ensure_event_loop():
    """
    Ensure we have a proper event loop for async operations in Celery workers
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")
    except RuntimeError:
        # No event loop exists or it's closed, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


@celery_app.task(bind=True, name="app.tasks.scraping_simple.start_domain_scrape")
def start_domain_scrape(self, domain_id: int, scrape_session_id: int) -> Dict[str, Any]:
    """
    Start scraping a domain - simplified version
    This task updates the session status and creates sample pages for testing
    """
    loop = _ensure_event_loop()

    try:
        return loop.run_until_complete(_start_domain_scrape_async(domain_id, scrape_session_id))
    except Exception as e:
        logger.error(f"Error in domain scrape task: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "domain_id": domain_id,
            "session_id": scrape_session_id
        }


async def _start_domain_scrape_async(domain_id: int, scrape_session_id: int) -> Dict[str, Any]:
    """
    Async implementation of domain scraping (legacy placeholder — real scraping
    uses scrape_domain_with_intelligent_extraction in firecrawl_scraping.py)
    """
    async with AsyncSessionLocal() as db:
        try:
            domain_result = await db.execute(
                select(Domain).where(Domain.id == domain_id)
            )
            domain = domain_result.scalar_one_or_none()

            session_result = await db.execute(
                select(ScrapeSession).where(ScrapeSession.id == scrape_session_id)
            )
            scrape_session = session_result.scalar_one_or_none()

            if not domain:
                logger.error(f"Domain {domain_id} not found")
                return {"status": "error", "message": f"Domain {domain_id} not found"}

            if not scrape_session:
                logger.error(f"Scrape session {scrape_session_id} not found")
                return {"status": "error", "message": f"Scrape session {scrape_session_id} not found"}

            logger.info(f"Starting scrape for domain {domain.domain_name} (ID: {domain_id})")

            scrape_session.status = ScrapeSessionStatus.RUNNING
            scrape_session.started_at = datetime.utcnow()
            await db.commit()

            broadcast_cdx_discovery_sync({
                "scrape_session_id": scrape_session_id,
                "domain_id": domain_id,
                "domain_name": domain.domain_name,
                "current_page": 0,
                "total_pages": 1,
                "results_found": 0,
                "results_processed": 0,
                "duplicates_filtered": 0,
                "list_pages_filtered": 0,
                "high_value_pages": 0
            })

            # Mark session as completed (placeholder — real scraping is in firecrawl_scraping.py)
            scrape_session.status = ScrapeSessionStatus.COMPLETED
            scrape_session.completed_at = datetime.utcnow()
            domain.status = DomainStatus.COMPLETED
            domain.last_scraped = datetime.utcnow()
            await db.commit()

            logger.info(f"Completed placeholder scrape for domain {domain.domain_name}")

            return {
                "status": "success",
                "domain_id": domain_id,
                "session_id": scrape_session_id,
                "pages_created": 0,
                "domain_name": domain.domain_name
            }

        except Exception as e:
            logger.error(f"Error in domain scrape task: {str(e)}")
            try:
                if 'scrape_session' in locals() and scrape_session:
                    scrape_session.status = ScrapeSessionStatus.FAILED
                    scrape_session.error_message = str(e)
                    await db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to update session status: {commit_error}")
            raise


@celery_app.task(bind=True, name="app.tasks.scraping_simple.process_page_content")
def process_page_content(self, page_id: int) -> Dict[str, Any]:
    """
    Process/retry a single page's content using the real extraction pipeline.
    Uses extract_content_with_escalation() for progressive retry strategy.
    """
    loop = _ensure_event_loop()

    try:
        return loop.run_until_complete(_process_page_async(page_id))
    except Exception as e:
        logger.error(f"Error processing page {page_id}: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "page_id": page_id
        }


async def _process_page_async(page_id: int) -> Dict[str, Any]:
    """
    Async implementation of page retry processing.

    Builds a CDX-like record from ScrapePage fields, runs it through
    extract_content_with_escalation(), and creates Page + ProjectPage
    records on success.
    """
    async with AsyncSessionLocal() as db:
        try:
            scrape_page_result = await db.execute(
                select(ScrapePage).where(ScrapePage.id == page_id)
            )
            scrape_page = scrape_page_result.scalar_one_or_none()

            if not scrape_page:
                return {"status": "error", "message": f"ScrapePage {page_id} not found"}

            # Get the domain to find project_id
            domain_result = await db.execute(
                select(Domain).where(Domain.id == scrape_page.domain_id)
            )
            domain = domain_result.scalar_one_or_none()

            if not domain:
                return {"status": "error", "message": f"Domain for scrape page {page_id} not found"}

            # Broadcast processing start
            broadcast_page_progress_sync({
                "scrape_session_id": scrape_page.scrape_session_id or 0,
                "scrape_page_id": scrape_page.id,
                "domain_id": scrape_page.domain_id or 0,
                "domain_name": domain.domain_name,
                "page_url": scrape_page.original_url,
                "content_url": scrape_page.content_url or "",
                "status": ScrapePageStatus.IN_PROGRESS,
                "processing_stage": "retry_processing",
                "stage_progress": 0.0,
                "retry_count": scrape_page.retry_count
            })

            # Update status to in progress
            scrape_page.status = ScrapePageStatus.IN_PROGRESS
            scrape_page.last_attempt_at = datetime.utcnow()
            await db.commit()

            # Broadcast content extraction stage
            broadcast_processing_stage_sync({
                "scrape_session_id": scrape_page.scrape_session_id or 0,
                "scrape_page_id": scrape_page.id,
                "domain_id": scrape_page.domain_id or 0,
                "page_url": scrape_page.original_url,
                "stage": "content_extract",
                "stage_status": "started"
            })

            try:
                # Build a CDXRecord from ScrapePage fields
                # CDXRecord is a dataclass: timestamp, original_url, mime_type,
                # status_code (str), digest, length (str). content_url is a @property.
                from app.services.wayback_machine import CDXRecord
                cdx_record = CDXRecord(
                    original_url=scrape_page.original_url,
                    timestamp=scrape_page.unix_timestamp or "",
                    mime_type=scrape_page.mime_type or "text/html",
                    status_code=str(scrape_page.status_code or 200),
                    digest=scrape_page.digest_hash or "",
                    length=str(scrape_page.content_length or 0),
                )

                # Use real extraction with escalation strategy
                from app.services.content_extraction_service import get_content_extraction_service
                extractor = get_content_extraction_service()
                extracted = await extractor.extract_content_with_escalation(
                    cdx_record, retry_count=scrape_page.retry_count
                )

                # Progressive threshold: 50 -> 40 -> 30 -> 20
                threshold = max(20, 50 - (scrape_page.retry_count * 10))

                if extracted.text and extracted.word_count > threshold:
                    # Success — update ScrapePage and create Page + ProjectPage
                    scrape_page.title = extracted.title or "No Title"
                    scrape_page.extracted_text = extracted.text
                    scrape_page.extracted_content = extracted.text
                    scrape_page.markdown_content = extracted.markdown or extracted.text
                    scrape_page.extraction_method = extracted.extraction_method
                    scrape_page.extraction_time = extracted.extraction_time

                    # Create Page record
                    from app.models.shared_pages import Page, ProjectPage
                    page = Page(
                        url=scrape_page.original_url,
                        content_url=scrape_page.content_url,
                        title=extracted.title or "No Title",
                        content=extracted.text,
                        extracted_text=extracted.text,
                        markdown_content=extracted.markdown or extracted.text,
                        unix_timestamp=int(scrape_page.unix_timestamp) if scrape_page.unix_timestamp else 0,
                        mime_type=scrape_page.mime_type,
                        status_code=scrape_page.status_code,
                        meta_description=extracted.meta_description,
                        author=extracted.author,
                        language=extracted.language,
                        word_count=extracted.word_count,
                        character_count=len(extracted.text),
                        content_length=scrape_page.content_length,
                        capture_date=scrape_page.first_seen_at,
                        processed=True,
                        indexed=False,
                    )
                    db.add(page)
                    await db.flush()

                    # Create ProjectPage junction record (CRITICAL for search visibility)
                    project_page = ProjectPage(
                        project_id=domain.project_id,
                        page_id=page.id,
                        domain_id=domain.id,
                        review_status="pending",
                        priority_level="medium",
                        is_starred=False,
                        tags=[],
                        is_duplicate=False,
                        added_at=datetime.utcnow()
                    )
                    db.add(project_page)

                    # Link ScrapePage to Page
                    scrape_page.page_id = None  # Legacy field, not used for UUID PKs
                    scrape_page.status = ScrapePageStatus.COMPLETED
                    scrape_page.completed_at = datetime.utcnow()
                    scrape_page.error_message = None
                    scrape_page.error_type = None

                    await db.commit()

                    # Index in Meilisearch
                    try:
                        from app.services.shared_pages_meilisearch import SharedPagesMeilisearchService
                        ms_service = SharedPagesMeilisearchService(db)
                        await ms_service.bulk_index_pages([str(page.id)])
                        logger.info(f"Indexed retry page {page.id} in Meilisearch")
                    except Exception as idx_err:
                        logger.warning(f"Meilisearch indexing failed for retry page: {idx_err}")

                    # Broadcast content extraction completed
                    broadcast_processing_stage_sync({
                        "scrape_session_id": scrape_page.scrape_session_id or 0,
                        "scrape_page_id": scrape_page.id,
                        "domain_id": scrape_page.domain_id or 0,
                        "page_url": scrape_page.original_url,
                        "stage": "content_extract",
                        "stage_status": "completed",
                        "stage_details": {
                            "title": scrape_page.title,
                            "word_count": extracted.word_count,
                            "extraction_method": extracted.extraction_method,
                            "threshold": threshold,
                        }
                    })

                    # Broadcast final status
                    broadcast_page_progress_sync({
                        "scrape_session_id": scrape_page.scrape_session_id or 0,
                        "scrape_page_id": scrape_page.id,
                        "domain_id": scrape_page.domain_id or 0,
                        "domain_name": domain.domain_name,
                        "page_url": scrape_page.original_url,
                        "content_url": scrape_page.content_url or "",
                        "status": ScrapePageStatus.COMPLETED,
                        "processing_stage": "completed",
                        "stage_progress": 1.0,
                        "retry_count": scrape_page.retry_count,
                    })

                    return {
                        "status": "success",
                        "page_id": page_id,
                        "url": scrape_page.original_url,
                        "word_count": extracted.word_count,
                        "extraction_method": extracted.extraction_method,
                        "threshold": threshold,
                        "retry_count": scrape_page.retry_count,
                    }

                else:
                    # Insufficient content even after extraction
                    wc = extracted.word_count
                    method = extracted.extraction_method
                    text_preview = (extracted.text[:150] + "...") if extracted.text and len(extracted.text) > 150 else (extracted.text or "")
                    error_msg = (
                        f"Retry extraction insufficient: {wc} words "
                        f"(threshold {threshold}) via {method}"
                    )

                    scrape_page.status = ScrapePageStatus.SKIPPED
                    scrape_page.error_message = error_msg
                    scrape_page.error_type = "insufficient_content"
                    scrape_page.filter_details = {
                        "word_count": wc,
                        "min_threshold": threshold,
                        "extraction_method": method,
                        "title": (extracted.title or "")[:200],
                        "text_preview": text_preview[:300],
                        "reason": "low_content",
                        "retry_count": scrape_page.retry_count,
                    }
                    scrape_page.completed_at = datetime.utcnow()
                    await db.commit()

                    # Broadcast failure
                    broadcast_page_progress_sync({
                        "scrape_session_id": scrape_page.scrape_session_id or 0,
                        "scrape_page_id": scrape_page.id,
                        "domain_id": scrape_page.domain_id or 0,
                        "domain_name": domain.domain_name,
                        "page_url": scrape_page.original_url,
                        "content_url": scrape_page.content_url or "",
                        "status": ScrapePageStatus.SKIPPED,
                        "processing_stage": "completed",
                        "stage_progress": 0.0,
                        "retry_count": scrape_page.retry_count,
                        "error_message": error_msg,
                        "error_type": "insufficient_content",
                    })

                    return {
                        "status": "skipped",
                        "page_id": page_id,
                        "url": scrape_page.original_url,
                        "word_count": wc,
                        "threshold": threshold,
                        "error": error_msg,
                        "retry_count": scrape_page.retry_count,
                    }

            except Exception as processing_error:
                # Handle processing failure
                scrape_page.status = ScrapePageStatus.FAILED
                scrape_page.error_message = str(processing_error)
                scrape_page.error_type = type(processing_error).__name__
                scrape_page.completed_at = datetime.utcnow()
                await db.commit()

                # Broadcast failure
                broadcast_page_progress_sync({
                    "scrape_session_id": scrape_page.scrape_session_id or 0,
                    "scrape_page_id": scrape_page.id,
                    "domain_id": scrape_page.domain_id or 0,
                    "domain_name": domain.domain_name,
                    "page_url": scrape_page.original_url,
                    "content_url": scrape_page.content_url or "",
                    "status": ScrapePageStatus.FAILED,
                    "processing_stage": "failed",
                    "stage_progress": 0.0,
                    "retry_count": scrape_page.retry_count,
                    "error_message": scrape_page.error_message,
                    "error_type": scrape_page.error_type
                })

                return {
                    "status": "failed",
                    "page_id": page_id,
                    "url": scrape_page.original_url,
                    "error": str(processing_error),
                    "retry_count": scrape_page.retry_count
                }

        except Exception as e:
            logger.error(f"Error processing page {page_id}: {str(e)}")
            raise
