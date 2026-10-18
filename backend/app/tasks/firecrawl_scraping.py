"""
Intelligent extraction scraping tasks for Celery

This module provides a streamlined scraping system that:
1. Uses CDX API for discovery with intelligent filtering
2. Uses intelligent extraction for high-speed content processing
3. Provides simple, reliable task execution with 99.9% faster extraction
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlmodel import select, Session
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.models.project import Domain, Project, ScrapeSession, ScrapeSessionStatus, DomainStatus
from app.models.scraping import ScrapePage, ScrapePageStatus, IncrementalRunType, IncrementalRunStatus
from app.services.content_extraction_service import MINIMAL_CONTENT_ERROR, get_content_extraction_service
from app.services.firecrawl_v2_client import FirecrawlV2Client, FirecrawlV2Error
from app.services.enhanced_intelligent_filter import get_enhanced_intelligent_filter, FilterReason
from app.services.archive_fetch_errors import ArchiveDeferred, ArchiveDiscoveryFailed, ArchiveFetchError
from app.services.archive_rate_limiter import get_archive_rate_limiter
from app.services.archive_merge import merge_hybrid_records
from app.services.page_persistence import (
    ERROR_DIGEST_REUSE, ERROR_EXISTING_PAGE, ensure_project_page, find_pages_by_digests,
    find_page_by_digest, find_page_by_url_timestamp, link_scrape_page, mark_linked, persist_extracted_page,
    defer_scrape_page, utcnow, record_failure, reindex_pages_and_mark, requeue_due_failures, reap_stale_in_progress, group_ids_by_session,
)
from app.services.meilisearch_service import meilisearch_service
from app.models.extraction_data import ExtractedContent
from app.services.incremental_scraping import IncrementalScrapingService
from app.services.archive_service_router import AllSourcesFailedException
from app.services.enhanced_archive_router import EnhancedArchiveServiceRouter, create_enhanced_routing_config_from_project

logger = logging.getLogger(__name__)


# Module-level singleton engine for Celery tasks
_sync_engine = None
_sync_session_factory = None


def get_sync_session():
    """Create a synchronous database session for Celery tasks using singleton engine"""
    global _sync_engine, _sync_session_factory
    if _sync_engine is None:
        _sync_engine = create_engine(
            settings.DATABASE_URL,
            poolclass=NullPool,  # Disable connection pooling for Celery
            echo=False,
        )
        _sync_session_factory = sessionmaker(
            _sync_engine,
            class_=Session,
            expire_on_commit=False,
        )
    return _sync_session_factory()


def run_async_in_sync(async_callable_or_coro):
    """
    Run an async function or coroutine object from sync Celery tasks.
    Accepts either a coroutine function (no args) or an already-created coroutine object.

    Each call runs on a fresh event loop that is closed afterwards. The shared async engine
    (app.core.database.engine) pools asyncpg connections, and those are bound to the loop
    that opened them: a later loop reusing one fails with "Event loop is closed" / "attached
    to a different loop". So the pool is emptied on this loop before it closes.
    """
    # Normalize to coroutine object
    if callable(async_callable_or_coro) and asyncio.iscoroutinefunction(async_callable_or_coro):
        coro = async_callable_or_coro()
    else:
        coro = async_callable_or_coro
    if not asyncio.iscoroutine(coro):
        raise TypeError("An asyncio.Future, a coroutine or an awaitable is required")

    async def _run_and_release_connections():
        try:
            return await coro
        finally:
            from app.core.database import engine as async_engine
            try:
                await async_engine.dispose()
            except Exception as exc:
                logger.warning(f"Could not release async DB connections before closing the loop: {exc}")

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_run_and_release_connections())
    finally:
        loop.close()


def _discovery_session_stats(scrape_session_id: int, created_pages: List[ScrapePage],
                             discovered: int, already_known: int) -> Dict[str, Any]:
    """
    Payload for ``broadcast_session_stats_sync`` after discovery, in SessionStatsEvent's field
    names: pending = pages to fetch, completed = linked to an existing page, skipped = filtered out.
    ``already_known`` (rows that existed before) has no field of its own and goes to performance_metrics.
    """
    pending = sum(1 for p in created_pages if p.status == ScrapePageStatus.PENDING)
    completed = sum(1 for p in created_pages if p.status == ScrapePageStatus.COMPLETED)
    skipped = len(created_pages) - pending - completed
    return {
        "scrape_session_id": scrape_session_id,
        "total_urls": discovered,
        "pending_urls": pending,
        "in_progress_urls": 0,
        "completed_urls": completed,
        "failed_urls": 0,
        "skipped_urls": skipped,
        "progress_percentage": ((completed + skipped) / discovered * 100) if discovered else 0.0,
        "active_domains": 1,
        "completed_domains": 0,
        "failed_domains": 0,
        "performance_metrics": {"already_known_urls": already_known},
    }


def _domain_failure_prefix(domain_name: str) -> str:
    return f"[{domain_name}] "


def record_domain_failure(scrape_session: ScrapeSession, domain_name: str, message: str) -> None:
    """
    Mark the session failed for one of its domains. A session spans several domains, each
    finished by its own task, so error_message keeps one "[domain] message" line per failed
    domain (replacing that domain's earlier line) instead of the last writer's message.
    """
    prefix = _domain_failure_prefix(domain_name)
    lines = [ln for ln in (scrape_session.error_message or "").splitlines()
             if ln.strip() and not ln.startswith(prefix)]
    lines.append(prefix + " ".join(message.split()))
    scrape_session.error_message = "\n".join(lines)
    scrape_session.status = ScrapeSessionStatus.FAILED


def clear_domain_failure(scrape_session: ScrapeSession, domain_name: str) -> None:
    """Forget this domain's failure line (a re-run starts clean); other domains' lines stay."""
    prefix = _domain_failure_prefix(domain_name)
    lines = [ln for ln in (scrape_session.error_message or "").splitlines()
             if ln.strip() and not ln.startswith(prefix)]
    scrape_session.error_message = "\n".join(lines) or None


def finish_domain_status(scrape_session: ScrapeSession) -> ScrapeSessionStatus:
    """
    Session status once one domain finished successfully: FAILED while another domain's
    failure is still recorded, COMPLETED otherwise. A later domain completing must not
    hide an earlier domain's failure behind "completed".
    """
    return ScrapeSessionStatus.FAILED if scrape_session.error_message else ScrapeSessionStatus.COMPLETED


def describe_discovery_failure(exc: BaseException, domain_name: str) -> Optional[ArchiveDiscoveryFailed]:
    """
    Turn an archive discovery exception into an ArchiveDiscoveryFailed with a clear message,
    or None when it is not an archive failure (the caller re-raises it unchanged).
    """
    root = exc.__cause__ if isinstance(exc, AllSourcesFailedException) and exc.__cause__ else exc
    if isinstance(root, ArchiveFetchError):
        detail = f"{root.error_type}: {root}"
        retryable, retry_after = root.retryable, root.retry_after
    elif isinstance(root, (asyncio.TimeoutError, TimeoutError)):
        detail = f"timed out after {settings.WAYBACK_CDX_DISCOVERY_TIMEOUT:.0f}s"
        retryable, retry_after = True, None
    elif isinstance(exc, AllSourcesFailedException):
        detail = str(root)
        retryable, retry_after = True, None
    else:
        return None
    message = (
        f"Archive discovery failed for {domain_name} ({detail}); no CDX records were stored. "
        + (f"Retryable{f' after ~{retry_after:.0f}s' if retry_after else ''}: re-run the scrape."
           if retryable else "Not retryable.")
    )
    return ArchiveDiscoveryFailed(message, retryable=retryable, retry_after=retry_after)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, retry_backoff=True)
def scrape_domain_with_intelligent_extraction(self, domain_id: int, scrape_session_id: int, history_id: Optional[int] = None, incremental_mode: bool = False) -> Dict[str, Any]:
    """
    Scrape a domain using intelligent content extraction with CDX filtering
    
    This is the main entry point for domain scraping that:
    1. Discovers pages via CDX API with intelligent filtering
    2. Extracts content using intelligent extraction (trafilatura, newspaper3k, beautifulsoup)
    3. Stores results in the database
    4. Updates incremental scraping history if in incremental mode
    
    Args:
        domain_id: ID of the domain to scrape
        scrape_session_id: ID of the scrape session
        history_id: ID of incremental scraping history record (for incremental runs)
        incremental_mode: Whether this is an incremental scraping run
        
    Returns:
        Dictionary with scraping results
    """
    db = None
    try:
        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 1,
                "total": 4,
                "status": "Starting intelligent extraction scraping...",
                "domain_id": domain_id
            }
        )
        
        # Create database session
        db = get_sync_session()
        
        # Get domain and validate
        domain = db.get(Domain, domain_id)
        scrape_session = db.get(ScrapeSession, scrape_session_id)
        
        if not domain:
            error_msg = f"Domain {domain_id} not found - may have been deleted during scraping"
            logger.error(error_msg)
            
            # Update scrape session with error if it exists
            if scrape_session:
                scrape_session.error_message = error_msg
                scrape_session.status = ScrapeSessionStatus.FAILED
                db.add(scrape_session)
                db.commit()
                
                # Log error to PageErrorLog if we can determine the original URL
                from app.models.scraping import PageErrorLog
                error_log = PageErrorLog(
                    error_type="domain_not_found",
                    error_message=error_msg,
                    error_details={
                        "domain_id": domain_id,
                        "scrape_session_id": scrape_session_id,
                        "task_id": None,
                        "recovery_action": "verify_domain_exists_before_retry"
                    },
                    wayback_url="unknown",
                    original_url="unknown",
                    is_recoverable=False,
                    suggested_retry_delay=None
                )
                db.add(error_log)
                db.commit()
            
            # Return error response instead of raising exception
            return {
                "status": "failed",
                "error": "domain_not_found",
                "message": error_msg,
                "domain_id": domain_id,
                "scrape_session_id": scrape_session_id,
                "pages_created": 0,
                "pages_failed": 0,
                "filter_stats": {},
                "runtime_seconds": 0
            }
            
        if not scrape_session:
            error_msg = f"Scrape session {scrape_session_id} not found - may have been cancelled"
            logger.error(error_msg)
            
            # Log error to PageErrorLog
            from app.models.scraping import PageErrorLog
            error_log = PageErrorLog(
                error_type="scrape_session_not_found",
                error_message=error_msg,
                error_details={
                    "domain_id": domain_id,
                    "scrape_session_id": scrape_session_id,
                    "domain_name": domain.domain_name if domain else "unknown",
                    "task_id": None,
                    "recovery_action": "verify_session_exists_before_retry"
                },
                wayback_url="unknown",
                original_url="unknown",
                is_recoverable=False,
                suggested_retry_delay=None
            )
            db.add(error_log)
            db.commit()
            
            # Return error response instead of raising exception
            return {
                "status": "failed",
                "error": "scrape_session_not_found",
                "message": error_msg,
                "domain_id": domain_id,
                "scrape_session_id": scrape_session_id,
                "pages_created": 0,
                "pages_failed": 0,
                "filter_stats": {},
                "runtime_seconds": 0
            }
            
        # Get project to check attachment download setting
        from app.models.project import Project
        project = db.get(Project, domain.project_id)
        if not project:
            error_msg = f"Project {domain.project_id} not found for domain {domain.domain_name}"
            logger.error(error_msg)
            
            # Update scrape session with error
            scrape_session.error_message = error_msg
            scrape_session.status = ScrapeSessionStatus.FAILED
            db.add(scrape_session)
            
            # Log error to PageErrorLog
            from app.models.scraping import PageErrorLog
            error_log = PageErrorLog(
                error_type="project_not_found",
                error_message=error_msg,
                error_details={
                    "domain_id": domain_id,
                    "project_id": domain.project_id,
                    "domain_name": domain.domain_name,
                    "scrape_session_id": scrape_session_id,
                    "task_id": None,
                    "recovery_action": "verify_project_exists_before_retry"
                },
                wayback_url="unknown",
                original_url="unknown",
                is_recoverable=False,
                suggested_retry_delay=None
            )
            db.add(error_log)
            db.commit()
            
            # Return error response instead of raising exception
            return {
                "status": "failed",
                "error": "project_not_found",
                "message": error_msg,
                "domain_id": domain_id,
                "scrape_session_id": scrape_session_id,
                "domain_name": domain.domain_name,
                "pages_created": 0,
                "pages_failed": 0,
                "filter_stats": {},
                "runtime_seconds": 0
            }
            
        logger.info(f"Project attachment setting: enable_attachment_download={project.enable_attachment_download}")
        
        logger.info(f"Starting intelligent extraction scraping for domain: {domain.domain_name} (incremental_mode: {incremental_mode})")
        
        # Initialize incremental tracking
        start_time = datetime.utcnow()
        if incremental_mode and history_id:
            # Convert async session to sync for updating history
            try:
                from app.core.database import get_async_session
                
                async def update_incremental_status():
                    async_db = anext(get_async_session())
                    async_db_session = await async_db
                    try:
                        # Update incremental history status to running
                        await IncrementalScrapingService.update_incremental_statistics(
                            async_db_session, domain_id, history_id, 
                            {"status": IncrementalRunStatus.RUNNING, "started_at": start_time}
                        )
                    finally:
                        await async_db_session.close()
                
                # Use the helper function to run async code
                run_async_in_sync(update_incremental_status)
            except Exception as e:
                logger.warning(f"Failed to update incremental history status: {e}")
        
        # Update domain status
        domain.status = DomainStatus.ACTIVE
        scrape_session.status = ScrapeSessionStatus.RUNNING
        # A re-run after a retryable discovery failure starts clean for THIS domain only
        clear_domain_failure(scrape_session, domain.domain_name)
        scrape_session.started_at = start_time
        db.commit()
        
        # Try to broadcast initial session stats for UI
        try:
            from app.services.websocket_service import broadcast_session_stats_sync
            broadcast_session_stats_sync({
                "scrape_session_id": scrape_session_id,
                "total_urls": 0,
                "pending_urls": 0,
                "in_progress_urls": 0,
                "completed_urls": 0,
                "failed_urls": 0,
                "skipped_urls": 0,
                "progress_percentage": 0.0,
                "active_domains": 1,
                "completed_domains": 0,
                "failed_domains": 0,
            })
        except Exception:
            pass
        
        # Step 1: CDX Discovery with intelligent filtering
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 2,
                "total": 4,
                "status": f"Discovering pages for {domain.domain_name}...",
                "domain_id": domain_id
            }
        )
        
        # Run async CDX discovery in sync context using helper to avoid loop mismatches
        try:
            cdx_records, all_filtering_decisions, filter_stats = run_async_in_sync(
                _discover_and_filter_pages(domain, project.enable_attachment_download)
            )
        except Exception as discovery_exc:
            # A discovery failure is a failure: never let it look like a domain without captures.
            failure = describe_discovery_failure(discovery_exc, domain.domain_name)
            if failure is None:
                raise
            raise failure from discovery_exc
        
        logger.info(f"CDX discovery completed: {len(cdx_records)} records after filtering")

        # Broadcast CDX discovery summary for the UI
        try:
            from app.services.websocket_service import broadcast_cdx_discovery_sync
            broadcast_cdx_discovery_sync({
                "scrape_session_id": scrape_session_id,
                "domain_id": domain_id,
                "domain_name": domain.domain_name,
                "current_page": filter_stats.get("fetched_pages", 0),
                "total_pages": filter_stats.get("total_pages"),
                "results_found": filter_stats.get("total_records", len(cdx_records)),
                "results_processed": len(cdx_records),
                "duplicates_filtered": filter_stats.get("duplicate_filtered", 0),
                "list_pages_filtered": filter_stats.get("list_filtered", 0),
                "high_value_pages": filter_stats.get("final_count", len(cdx_records)),
            })
        except Exception:
            pass
        
        # Update session stats with total discovered URLs (not just filtered ones)
        scrape_session.total_urls = len(all_filtering_decisions)
        db.commit()
        
        # Create ScrapePage records for ALL discovered URLs with individual filtering reasons using batch operations
        logger.info(f"Creating ScrapePage records for ALL {len(all_filtering_decisions)} discovered URLs with individual filtering reasons")
        
        # BATCH PROCESSING FOR PERFORMANCE: Instead of individual queries, use bulk operations
        # Step 1: Find existing ScrapePage records to avoid duplicates
        existing_combinations = set()
        if all_filtering_decisions:
            # Get all existing records for this domain in a single query (much simpler and faster)
            existing_pages_query = db.execute(
                select(ScrapePage.original_url, ScrapePage.unix_timestamp)
                .where(ScrapePage.domain_id == domain.id)
            ).fetchall()
            
            existing_combinations = {(row[0], row[1]) for row in existing_pages_query}
            logger.info(f"Found {len(existing_combinations)} existing ScrapePage records, will skip duplicates")
        
        # Step 2: Prepare ScrapePage objects for bulk insert
        scrape_pages_to_create = []
        batch_progress_data = []
        current_time = datetime.utcnow()
        
        for decision in all_filtering_decisions:
            try:
                cdx_record = decision.cdx_record
                url_timestamp_key = (cdx_record.original_url, str(cdx_record.timestamp))
                
                # Skip if this combination already exists
                if url_timestamp_key not in existing_combinations:
                    # Create ScrapePage with filtering decision data
                    scrape_page = ScrapePage(
                        domain_id=domain.id,
                        scrape_session_id=scrape_session_id,
                        original_url=cdx_record.original_url,
                        content_url=cdx_record.content_url,
                        unix_timestamp=str(cdx_record.timestamp),
                        mime_type=cdx_record.mime_type or "text/html",
                        status_code=int(cdx_record.status_code) if cdx_record.status_code else 200,
                        content_length=cdx_record.content_length_bytes,
                        digest_hash=getattr(cdx_record, 'digest', None),
                        warc_filename=getattr(cdx_record, 'warc_filename', None),
                        warc_offset=getattr(cdx_record, 'warc_offset', None),
                        warc_length=getattr(cdx_record, 'warc_length', None),
                        status=decision.status,
                        filter_reason=decision.reason.value if hasattr(decision.reason, 'value') else str(decision.reason),
                        filter_category=decision.reason.value if hasattr(decision.reason, 'value') else str(decision.reason),
                        filter_details=decision.filter_details,
                        matched_pattern=decision.matched_pattern,
                        filter_confidence=decision.confidence,
                        related_page_id=getattr(decision, 'related_page_id', None),
                        is_pdf=cdx_record.mime_type == "application/pdf" if cdx_record.mime_type else False,
                        priority_score=getattr(decision, 'priority_score', None),
                        can_be_manually_processed=decision.can_be_manually_processed,
                        first_seen_at=current_time,
                        created_at=current_time
                    )
                    # Identical archive payload already stored as a Page: link instead of fetching.
                    reuse_page_id = (decision.filter_details or {}).get("existing_page_id")
                    if decision.reason == FilterReason.ALREADY_PROCESSED_DIGEST and reuse_page_id:
                        mark_linked(
                            scrape_page, uuid.UUID(str(reuse_page_id)), ERROR_DIGEST_REUSE,
                            f"Reused page {reuse_page_id}: identical archive payload digest {cdx_record.digest}",
                        )
                    scrape_pages_to_create.append(scrape_page)
                    
                    # Collect data for batch WebSocket broadcast (without individual broadcasts)
                    batch_progress_data.append({
                        "page_url": cdx_record.original_url,
                        "content_url": cdx_record.content_url,
                        "status": decision.status,
                        "filter_reason": getattr(decision, 'specific_reason', str(decision.reason))
                    })
                        
            except Exception as e:
                logger.error(f"Failed to prepare ScrapePage for {decision.cdx_record.original_url}: {str(e)}")
        
        # Step 3: Bulk insert ScrapePage records (much faster than individual inserts)
        scrape_pages_created = len(scrape_pages_to_create)
        if scrape_pages_to_create:
            # Process in batches to avoid memory issues with very large domains
            batch_size = 5000
            for i in range(0, len(scrape_pages_to_create), batch_size):
                batch = scrape_pages_to_create[i:i + batch_size]
                db.add_all(batch)
                db.commit()  # Commit each batch to avoid long transactions
                logger.info(f"Batch inserted {len(batch)} ScrapePage records ({i + len(batch)}/{scrape_pages_created} total)")
        
        logger.info(f"Created {scrape_pages_created} ScrapePage records with individual filtering reasons (skipped {len(existing_combinations)} duplicates)")

        # Link digest-reused captures to this project (ProjectPage) so they show up in search.
        reused_page_ids = []
        for sp in scrape_pages_to_create:
            if sp.status == ScrapePageStatus.COMPLETED and sp.page_id is not None:
                if ensure_project_page(db, domain.project_id, sp.page_id, domain.id):
                    reused_page_ids.append(sp.page_id)
        if reused_page_ids:
            db.commit()
            logger.info(f"Digest reuse: linked {len(reused_page_ids)} existing pages to project {domain.project_id} "
                        f"for domain {domain.domain_name} (no fetch needed)")
            run_async_in_sync(reindex_pages_and_mark(db, reused_page_ids))
        
        # Step 4: Broadcast session-level statistics instead of page-level progress
        if batch_progress_data:
            try:
                from app.services.websocket_service import broadcast_session_stats_sync
                broadcast_session_stats_sync(_discovery_session_stats(
                    scrape_session_id, scrape_pages_to_create, len(all_filtering_decisions), len(existing_combinations)
                ))
            except Exception as e:
                logger.warning(f"Failed to broadcast batch progress: {e}")
        
        # Log filtering statistics for transparency
        status_counts = {}
        for decision in all_filtering_decisions:
            status_key = decision.status.value if hasattr(decision.status, 'value') else str(decision.status)
            status_counts[status_key] = status_counts.get(status_key, 0) + 1
        
        logger.info(f"Filtering status breakdown: {status_counts}")
        
        # Check if intelligent extraction should be used instead of Firecrawl V2 batch processing
        use_intelligent_only = getattr(settings, "USE_INTELLIGENT_EXTRACTION_ONLY", False)
        
        if use_intelligent_only:
            logger.info("USE_INTELLIGENT_EXTRACTION_ONLY is enabled - bypassing all Firecrawl V2 batch processing")
        else:
            # Create Firecrawl v2 batch - mandatory when V2_BATCH_ONLY is enabled
            v2_batch_only = getattr(settings, "FIRECRAWL_V2_BATCH_ONLY", False)
            v2_batch_enabled = getattr(settings, "FIRECRAWL_V2_BATCH_ENABLED", True)
            
            if (v2_batch_enabled or v2_batch_only) and not getattr(scrape_session, "external_batch_id", None):
                batch_urls = [r.content_url for r in cdx_records]
                if batch_urls:
                    # Chunk URLs to avoid timeout issues with large batches
                    max_batch_size = getattr(settings, "FIRECRAWL_MAX_BATCH_SIZE", 1000)  # Conservative limit
                    url_chunks = [batch_urls[i:i + max_batch_size] for i in range(0, len(batch_urls), max_batch_size)]
                    
                    logger.info(f"Splitting {len(batch_urls)} URLs into {len(url_chunks)} batches of up to {max_batch_size} URLs each")
                    
                    # Extended timeout for Wayback Machine (2 minutes as requested)
                    timeout_ms = (getattr(settings, "WAYBACK_MACHINE_TIMEOUT", 120) or 120) * 1000
                    fc = FirecrawlV2Client()
                    
                    # Store batch IDs for tracking multiple batches
                    batch_ids = []
                
                    for chunk_idx, url_chunk in enumerate(url_chunks):
                        try:
                            logger.info(f"Creating batch {chunk_idx + 1}/{len(url_chunks)} with {len(url_chunk)} URLs")
                            
                            # Use enhanced v2 features: 24-hour caching for historical content
                            batch_id = fc.start_batch(
                                url_chunk, 
                                formats=["markdown", "html"], 
                                timeout_ms=timeout_ms,
                                max_age_hours=24  # Cache Wayback Machine content for 24 hours
                            )
                            
                            if batch_id:
                                batch_ids.append(batch_id)
                                logger.info(f"Successfully created batch {chunk_idx + 1}/{len(url_chunks)}: {batch_id}")
                            else:
                                logger.error(f"Failed to create batch {chunk_idx + 1}/{len(url_chunks)}: No batch ID returned")
                                if v2_batch_only:
                                    raise RuntimeError(f"Failed to create Firecrawl V2 batch chunk {chunk_idx + 1} and V2_BATCH_ONLY is enabled")
                                    
                        except Exception as e:
                            error_msg = f"Failed to start Firecrawl V2 batch chunk {chunk_idx + 1}/{len(url_chunks)} for session {scrape_session_id}: {e}"
                            logger.error(error_msg)
                            
                            if v2_batch_only:
                                raise RuntimeError(f"V2 batch creation failed for chunk {chunk_idx + 1} and V2_BATCH_ONLY is enabled: {e}")
                            else:
                                logger.warning(f"Continuing with remaining batches after failure: {error_msg}")
                                continue
                
                    # Store the batch IDs (comma-separated for multiple batches)
                    if batch_ids:
                        scrape_session.external_batch_id = ",".join(batch_ids)
                        scrape_session.external_batch_provider = "firecrawl_v2_multi"
                        db.commit()
                        logger.info(f"Created {len(batch_ids)} Firecrawl V2 batches for session {scrape_session_id}: {', '.join(batch_ids)}")
                    elif v2_batch_only:
                        raise RuntimeError("No Firecrawl V2 batches created and V2_BATCH_ONLY is enabled")
                        
                elif v2_batch_only:
                    # Gracefully handle empty CDX in V2 batch-only mode
                    logger.info("V2 batch-only mode: No URLs available for batch; skipping batch creation and proceeding with 0 pages")
                    scrape_session.completed_urls = 0
                    scrape_session.failed_urls = 0
                    db.commit()

        # Early stop if cancelled before processing
        def _should_stop(local_db: Session, session_id: int) -> bool:
            sess = local_db.get(ScrapeSession, session_id)
            if not sess:
                return True
            try:
                return sess.status in {ScrapeSessionStatus.CANCELLED, ScrapeSessionStatus.FAILED}
            except Exception:
                return False

        # Avoid autoflush while checking cancellation to prevent unintended flush/commit
        with db.no_autoflush:
            should_stop = _should_stop(db, scrape_session_id)
        if should_stop:
            logger.info(f"Session {scrape_session_id} cancelled; stopping before processing pages")
            try:
                domain.status = DomainStatus.PAUSED
                scrape_session.status = ScrapeSessionStatus.CANCELLED
                scrape_session.completed_at = datetime.utcnow()
                db.commit()
            except Exception as commit_error:
                # Handle stale/rollback scenarios gracefully
                logger.warning(f"Cancellation commit failed, attempting recovery: {commit_error}")
                try:
                    db.rollback()
                    # Re-fetch entities to ensure they are in sync
                    refreshed_domain = db.get(Domain, domain_id)
                    refreshed_session = db.get(ScrapeSession, scrape_session_id)
                    if refreshed_domain:
                        refreshed_domain.status = DomainStatus.PAUSED
                    if refreshed_session:
                        refreshed_session.status = ScrapeSessionStatus.CANCELLED
                        refreshed_session.completed_at = datetime.utcnow()
                    db.commit()
                except Exception as recovery_error:
                    logger.error(f"Failed to recover from cancellation commit error: {recovery_error}")
                    db.rollback()
            return {
                "status": "cancelled",
                "domain_name": domain.domain_name,
                "domain_id": domain_id,
                "session_id": scrape_session_id,
                "pages_found": len(cdx_records),
                "pages_created": 0,
                "pages_failed": 0,
                "message": "Cancelled before processing batches"
            }

        # Step 2: Extract content using intelligent extraction
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 3,
                "total": 4,
                "status": f"Extracting content for {len(cdx_records)} pages...",
                "domain_id": domain_id,
                "total_pages": len(cdx_records)
            }
        )
        
        # Process pages with intelligent extraction - batch processing or individual fallback
        pages_created = 0
        pages_failed = 0
        
        # Check if we should use V2 batch-only mode (but respect intelligent extraction setting)
        if not use_intelligent_only and v2_batch_only and scrape_session.external_batch_id:
            # V2 Batch-only processing mode
            logger.info(f"Processing session {scrape_session_id} using V2 batch-only mode with batch ID: {scrape_session.external_batch_id}")
            
            # Run async V2 batch processing in sync context
            pages_created, pages_failed = run_async_in_sync(
                _process_v2_batch_results(db, scrape_session, domain, cdx_records, self)
            )
        elif use_intelligent_only:
            # Use intelligent extraction only (bypass Firecrawl entirely)
            logger.info(f"Processing session {scrape_session_id} using intelligent extraction (robust content extractor)")
            
            # Process with individual intelligent extraction calls
            pages_created, pages_failed = run_async_in_sync(
                _process_individual_firecrawl(db, scrape_session, domain, self, scrape_session_id)
            )
        else:
            # Fallback to individual processing (when V2_BATCH_ONLY is False)
            if v2_batch_only:
                # In V2 batch-only mode with no batch ID (e.g., 0 URLs), just finalize with 0 pages
                logger.info("V2 batch-only mode with no batch ID: finalizing session with 0 pages")
                pages_created = 0
                pages_failed = 0
            else:
                logger.info(f"Processing session {scrape_session_id} using individual extraction mode")
                
                # Process with individual Firecrawl calls
                pages_created, pages_failed = run_async_in_sync(
                    _process_individual_firecrawl(db, scrape_session, domain, self, scrape_session_id)
                )
        
        
        # Step 3: Update statistics and finalize session
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 4,
                "total": 4,
                "status": "Finalizing results...",
                "domain_id": domain_id,
                "pages_created": pages_created
            }
        )
        
        # Update domain and session statistics
        domain.total_pages = len(cdx_records)
        domain.scraped_pages = pages_created
        domain.last_scraped = datetime.utcnow()
        
        # Check if session was cancelled during processing
        current_status = db.get(ScrapeSession, scrape_session_id).status
        if current_status == ScrapeSessionStatus.CANCELLED:
            scrape_session.status = ScrapeSessionStatus.CANCELLED
            scrape_session.completed_at = datetime.utcnow()
            logger.info(f"Session {scrape_session_id} was cancelled during processing")
        else:
            scrape_session.completed_urls = pages_created
            scrape_session.failed_urls = pages_failed
            scrape_session.status = finish_domain_status(scrape_session)
            scrape_session.completed_at = datetime.utcnow()
            if scrape_session.status == ScrapeSessionStatus.FAILED:
                logger.warning(
                    f"Session {scrape_session_id}: {domain.domain_name} completed, but the session stays "
                    f"failed for another domain: {scrape_session.error_message}"
                )
        
        db.commit()
        
        logger.info(f"Intelligent extraction scraping completed: {pages_created} pages created, {pages_failed} failed")
        
        # Update incremental history on completion
        if incremental_mode and history_id:
            try:
                from app.core.database import get_async_session
                
                async def update_completion_stats():
                    async_db = anext(get_async_session())
                    async_db_session = await async_db
                    try:
                        # Calculate runtime and statistics
                        end_time = datetime.utcnow()
                        runtime_seconds = (end_time - start_time).total_seconds()
                        
                        completion_stats = {
                            "status": "completed",
                            "completed_at": end_time,
                            "runtime_seconds": runtime_seconds,
                            "pages_processed": pages_created + pages_failed,
                            "pages_created": pages_created,
                            "pages_failed": pages_failed,
                            "new_content_found": pages_created,
                            "success_rate": (pages_created / (pages_created + pages_failed) * 100) if (pages_created + pages_failed) > 0 else 0
                        }
                        
                        # Update incremental statistics
                        await IncrementalScrapingService.update_incremental_statistics(
                            async_db_session, domain_id, history_id, completion_stats
                        )
                        
                        # Update domain coverage
                        await IncrementalScrapingService.update_domain_coverage(
                            async_db_session, domain_id, 
                            {"new_content": pages_created, "gaps_filled": 0}
                        )
                    finally:
                        await async_db_session.close()
                
                # Use the helper function to run async code
                run_async_in_sync(update_completion_stats)
                logger.info(f"Updated incremental history {history_id} with completion stats")
            except Exception as e:
                logger.warning(f"Failed to update incremental completion stats: {e}")
        
        # Broadcast final session stats
        try:
            from app.services.websocket_service import broadcast_session_stats_sync
            total = scrape_session.total_urls or 0
            completed = scrape_session.completed_urls or 0
            failed = scrape_session.failed_urls or 0
            progress_pct = (completed / total * 100) if total else 0.0
            broadcast_session_stats_sync({
                "scrape_session_id": scrape_session_id,
                "total_urls": total,
                "pending_urls": 0,
                "in_progress_urls": 0,
                "completed_urls": completed,
                "failed_urls": failed,
                "skipped_urls": 0,
                "progress_percentage": progress_pct,
                "active_domains": 0,
                "completed_domains": 1,
                "failed_domains": 0,
            })
        except Exception:
            pass
        
        return {
            "status": "completed",
            "domain_name": domain.domain_name,
            "domain_id": domain_id,
            "session_id": scrape_session_id,
            "history_id": history_id,
            "pages_found": len(cdx_records),
            "pages_created": pages_created,
            "pages_failed": pages_failed,
            "filter_stats": filter_stats,
            "incremental_mode": incremental_mode,
            "message": f"Successfully extracted {pages_created} pages using intelligent extraction for {domain.domain_name}"
        }
        
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Intelligent extraction scraping failed for domain {domain_id}: {error_msg}")
        
        # Update incremental history on failure
        if incremental_mode and history_id:
            try:
                async def update_failure_stats():
                    from app.core.database import get_async_session
                    async_db = anext(get_async_session())
                    async_db_session = await async_db
                    try:
                        # Calculate runtime
                        end_time = datetime.utcnow()
                        runtime_seconds = (end_time - start_time).total_seconds()
                        
                        failure_stats = {
                            "status": "failed",
                            "completed_at": end_time,
                            "runtime_seconds": runtime_seconds,
                            "error_message": error_msg,
                            "error_details": {"exception_type": type(exc).__name__}
                        }
                        
                        await IncrementalScrapingService.update_incremental_statistics(
                            async_db_session, domain_id, history_id, failure_stats
                        )
                    finally:
                        await async_db_session.close()
                
                run_async_in_sync(update_failure_stats)
                logger.info(f"Updated incremental history {history_id} with failure stats")
            except Exception as e:
                logger.warning(f"Failed to update incremental failure stats: {e}")
        
        # Update database status on failure
        if db:
            try:
                domain = db.get(Domain, domain_id)
                scrape_session = db.get(ScrapeSession, scrape_session_id)
                
                if domain:
                    domain.status = DomainStatus.ERROR
                if scrape_session:
                    record_domain_failure(
                        scrape_session, domain.domain_name if domain else f"domain {domain_id}", error_msg
                    )

                db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update database after error: {db_error}")

        if isinstance(exc, ArchiveDiscoveryFailed) and exc.retryable:
            # Re-run discovery later (the Redis CDX page cache keeps finished pages), at the earliest
            # when the Wayback pause ends; bounded by the task's max_retries. Past that the
            # session simply stays failed with its error message.
            countdown = min(max((exc.retry_after or 0.0) + 30.0, 300.0), 3600.0)
            logger.warning(
                f"Discovery for domain {domain_id} (session {scrape_session_id}) failed and is "
                f"retryable: retry {self.request.retries + 1}/{self.max_retries} in {countdown:.0f}s"
            )
            raise self.retry(exc=exc, countdown=countdown)

        # Raise the exception and let Celery record proper failure metadata
        raise
        
    finally:
        if db:
            db.close()


async def _extract_one_record(extractor, cdx_record) -> Optional[Dict[str, Any]]:
    """
    Run intelligent extraction for a single CDX record and classify the outcome.

    Never raises — failures come back as diagnostic dicts so callers can set
    ScrapePage statuses without try/except around every await:
    - ``_fetch_error``: the fetch layer raised an ArchiveFetchError (typed, honest, retryable or not);
      ``_deferred`` is also set when it was an ArchiveDeferred (the limiter refused, nothing was
      sent: not an attempt)
    - ``_extraction_error``: any other exception
    - ``_low_content``: fetched fine but too little text
    ``fetch_time`` is the extractor's own fetch duration when it reports one, else the
    wall time of the whole call.
    """
    started = time.monotonic()
    try:
        extracted_content = await extractor.extract_content(cdx_record)
        elapsed = time.monotonic() - started
        fetch_time = getattr(extracted_content, 'fetch_time', None)
        if fetch_time is None:
            fetch_time = elapsed

        if extracted_content.text and extracted_content.word_count > 50:
            return {
                'title': extracted_content.title or "No Title",
                'text': extracted_content.text,
                'markdown': extracted_content.markdown or extracted_content.text,
                'description': extracted_content.meta_description,
                'author': extracted_content.author,
                'language': extracted_content.language,
                'source_url': extracted_content.source_url,
                'status_code': extracted_content.status_code,
                'error': extracted_content.error,
                'word_count': extracted_content.word_count,
                'extraction_method': extracted_content.extraction_method,
                'extraction_time': extracted_content.extraction_time,
                'fetch_time': fetch_time,
            }

        if (not extracted_content.text and extracted_content.error
                and not extracted_content.error.startswith(MINIMAL_CONTENT_ERROR)):
            # Legacy fetch layer: failures came back as an empty result carrying an error string.
            # (A fetched page with too little text carries MINIMAL_CONTENT_ERROR and is NOT a fetch
            # failure: it falls through to _low_content, which is skipped and final.)
            logger.warning(f"Empty extraction with error for {cdx_record.original_url}: {extracted_content.error}")
            return {
                '_fetch_error': True,
                'error_type': 'fetch_error',
                'retryable': True,
                'error': extracted_content.error,
                'fetch_time': fetch_time,
            }

        # Return diagnostics instead of None — preserves info for error messages
        text_preview = (extracted_content.text[:150] + "...") if extracted_content.text and len(extracted_content.text) > 150 else (extracted_content.text or "")
        logger.warning(
            f"Low content for {cdx_record.original_url}: "
            f"{extracted_content.word_count} words via {extracted_content.extraction_method}"
        )
        return {
            '_low_content': True,
            'word_count': extracted_content.word_count,
            'extraction_method': extracted_content.extraction_method,
            'title': extracted_content.title or "",
            'text_preview': text_preview,
            'error': extracted_content.error,
            'fetch_time': fetch_time,
        }

    except ArchiveFetchError as e:
        logger.warning(f"Archive fetch failed for {cdx_record.original_url}: {e.error_type}: {e}")
        return {
            '_fetch_error': True,
            '_deferred': isinstance(e, ArchiveDeferred),
            'error_type': e.error_type,
            'retryable': e.retryable,
            'retry_after': e.retry_after,
            'status_code': e.status_code,
            'error': str(e),
            'fetch_time': time.monotonic() - started,
        }
    except Exception as e:
        logger.error(f"Intelligent extraction failed for {cdx_record.original_url}: {str(e)}")
        return {
            '_extraction_error': True,
            'error': str(e),
            'error_type': type(e).__name__,
            'fetch_time': time.monotonic() - started,
        }


async def _process_batch_with_firecrawl(batch_records) -> List[Optional[Dict[str, Any]]]:
    """
    Process a batch of CDX records with Firecrawl in parallel

    Args:
        batch_records: List of CDX records to process

    Returns:
        List of extracted content dictionaries (None for failures)
    """

    extractor = get_content_extraction_service()

    # Process all records in parallel with semaphore for rate limiting
    semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests

    async def extract_single(cdx_record):
        async with semaphore:
            return await _extract_one_record(extractor, cdx_record)

    # Execute all extractions in parallel
    results = await asyncio.gather(
        *[extract_single(record) for record in batch_records],
        return_exceptions=True
    )
    
    # Handle exceptions in results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Exception in parallel extraction for {batch_records[i].original_url}: {result}")
            processed_results.append(None)
        else:
            processed_results.append(result)
    
    return processed_results


async def _extract_content_with_firecrawl(cdx_record) -> Optional[Dict[str, Any]]:
    """
    Extract content from a CDX record using Firecrawl (kept for compatibility)
    
    Args:
        cdx_record: CDX record to extract
        
    Returns:
        Dictionary with extracted content or None if failed
    """
    results = await _process_batch_with_firecrawl([cdx_record])
    return results[0] if results else None


# Compatibility alias for legacy code
scrape_domain_with_firecrawl = scrape_domain_with_intelligent_extraction


# Simplified task for backward compatibility
@celery_app.task
def start_domain_scrape_simple(domain_id: int) -> str:
    """
    Simple task wrapper that creates a scrape session and starts scraping
    
    Args:
        domain_id: ID of the domain to scrape
        
    Returns:
        Task ID of the main scraping task
    """
    db = get_sync_session()
    
    try:
        # Get domain
        domain = db.get(Domain, domain_id)
        if not domain:
            error_msg = f"Domain {domain_id} not found - may have been deleted during task queuing"
            logger.error(error_msg)
            
            # Log error to PageErrorLog
            from app.models.scraping import PageErrorLog
            error_log = PageErrorLog(
                error_type="domain_not_found",
                error_message=error_msg,
                error_details={
                    "domain_id": domain_id,
                    "task_id": None,
                    "function": "start_scraping_task",
                    "recovery_action": "verify_domain_exists_before_retry"
                },
                wayback_url="unknown",
                original_url="unknown",
                is_recoverable=False,
                suggested_retry_delay=None
            )
            db.add(error_log)
            db.commit()
            
            # Return None to indicate failure
            return None
        
        # Create scrape session
        scrape_session = ScrapeSession(
            project_id=domain.project_id,
            session_name=f"Firecrawl scrape - {domain.domain_name}",
            status=ScrapeSessionStatus.PENDING,
            total_urls=0,
            completed_urls=0,
            failed_urls=0,
            cancelled_urls=0
        )
        
        db.add(scrape_session)
        db.commit()
        db.refresh(scrape_session)
        
        # Start the main scraping task
        task = scrape_domain_with_intelligent_extraction.delay(domain_id, scrape_session.id)
        
        logger.info(f"Started intelligent extraction scraping task {task.id} for domain {domain_id}")
        
        return task.id
        
    finally:
        db.close()


async def _process_v2_batch_results(db, scrape_session, domain, cdx_records, task_self):
    """
    Process results from a Firecrawl V2 batch operation
    
    Args:
        db: Database session
        scrape_session: ScrapeSession object
        domain: Domain object
        cdx_records: List of CDX records
        task_self: Celery task instance for state updates
        
    Returns:
        Tuple of (pages_created, pages_failed)
    """
    from app.services.firecrawl_v2_client import FirecrawlV2Client
    from app.models.scraping import ScrapePage, ScrapePageStatus

    pages_created = 0
    pages_failed = 0
    
    if not scrape_session.external_batch_id:
        logger.error(f"No external batch ID found for session {scrape_session.id}")
        return pages_created, pages_failed
    
    # Handle multiple batch IDs (comma-separated)
    batch_ids = [bid.strip() for bid in scrape_session.external_batch_id.split(",") if bid.strip()]
    logger.info(f"Processing V2 batch results for {len(batch_ids)} batch(es): {', '.join(batch_ids[:3])}{'...' if len(batch_ids) > 3 else ''}")

    # Retrieve real V2 batch results with pagination (per docs) for all batches
    fc_client = FirecrawlV2Client()
    all_documents = []
    
    for batch_idx, batch_id in enumerate(batch_ids):
        logger.info(f"Processing batch {batch_idx + 1}/{len(batch_ids)}: {batch_id}")
        
        next_token = None
        try:
            while True:
                status_resp = fc_client.get_batch_status(batch_id, next_token)
                documents = status_resp.get("data") or []
                if documents:
                    all_documents.extend(documents)
                    logger.info(f"Retrieved {len(documents)} documents from batch {batch_idx + 1}, total: {len(all_documents)}")
                next_token = status_resp.get("next")
                if not next_token:
                    break
        except FirecrawlV2Error as e:
            logger.error(f"Error retrieving V2 batch results for batch {batch_id}: {e}")
            # Continue with next batch
            continue
    
    # Get pending scrape pages
    pending_scrape_pages = db.execute(
        select(ScrapePage)
        .where(
            ScrapePage.domain_id == domain.id,
            ScrapePage.scrape_session_id == scrape_session.id,
            ScrapePage.status == ScrapePageStatus.PENDING
        )
        .order_by(ScrapePage.id)
    ).scalars().all()
    
    # Pages that already exist for this URL+timestamp only need the project link
    page_ids_to_index = []
    scrape_pages_to_process = []
    for scrape_page in pending_scrape_pages:
        existing_page = find_page_by_url_timestamp(db, scrape_page.original_url, scrape_page.unix_timestamp)

        if not existing_page:
            scrape_pages_to_process.append(scrape_page)
        elif link_scrape_page(db, scrape_page, existing_page, domain.project_id, ERROR_EXISTING_PAGE,
                              f"Page {existing_page} already exists for this URL and timestamp"):
            page_ids_to_index.append(existing_page)
    
    db.commit()
    logger.info(f"Processing {len(scrape_pages_to_process)} pages from V2 batch")

    # Build a lookup from Firecrawl doc -> by source URL (we sent wayback URLs in the batch)
    url_to_doc = {}
    for doc in all_documents:
        meta = (doc or {}).get("metadata") or {}
        source_url = meta.get("sourceURL") or meta.get("url") or doc.get("url")
        if source_url:
            url_to_doc[source_url] = doc

    # Map results to ScrapePage and create Page records
    for scrape_page in scrape_pages_to_process:
        try:
            # Mark as in progress
            scrape_page.status = ScrapePageStatus.IN_PROGRESS
            scrape_page.last_attempt_at = datetime.utcnow()
            db.flush()
            
            # Find matching Firecrawl document by wayback URL
            doc = url_to_doc.get(scrape_page.content_url)
            if not doc:
                # No result found for this page in batch output
                record_failure(db, scrape_page, "v2_batch_miss", "No Firecrawl batch result for this URL")
                pages_failed += 1
                continue

            metadata = (doc.get("metadata") or {})
            title = metadata.get("title") or doc.get("title") or scrape_page.title or scrape_page.original_url
            markdown = doc.get("markdown") or ""
            html = doc.get("html") or doc.get("rawHtml") or ""
            status_code = metadata.get("statusCode")
            description = metadata.get("description")
            language = metadata.get("language")

            # Detect language if not provided by Firecrawl
            text_content = markdown or html or ""
            if not language and text_content:
                try:
                    from langdetect import detect
                    language = detect(text_content[:2000])
                except Exception:
                    language = None

            # Compute quality score based on content heuristics
            word_count = len(text_content.split())
            char_count = len(text_content)
            quality = 0.0
            if title:
                quality += 0.25
            if description:
                quality += 0.15
            if word_count >= 100:
                quality += 0.25
            elif word_count >= 50:
                quality += 0.15
            elif word_count >= 20:
                quality += 0.05
            if char_count >= 500:
                quality += 0.20
            elif char_count >= 200:
                quality += 0.10
            if language:
                quality += 0.10
            if status_code and 200 <= int(status_code) < 300:
                quality += 0.05
            quality = round(min(quality, 1.0), 2)

            # One Page row holds the text; the scrape row just points at it.
            with db.begin_nested():
                outcome = persist_extracted_page(db, scrape_page, domain.project_id, {
                    "title": title,
                    "text": text_content,
                    "markdown": markdown,
                    "description": description,
                    "language": language,
                    "status_code": int(status_code) if status_code else None,
                    "quality_score": quality,
                    "word_count": word_count,
                    "extraction_method": "firecrawl_v2_batch",
                })
            pages_created += 1
            if outcome.created_page or outcome.project_page_created:
                page_ids_to_index.append(outcome.page_id)

            # Broadcast progress
            try:
                from app.services.websocket_service import broadcast_page_progress_sync
                broadcast_page_progress_sync({
                    "scrape_session_id": scrape_session.id,
                    "scrape_page_id": scrape_page.id,
                    "domain_id": domain.id,
                    "domain_name": domain.domain_name,
                    "page_url": scrape_page.original_url,
                    "content_url": scrape_page.content_url,
                    "status": ScrapePageStatus.COMPLETED,
                    "processing_stage": "v2_batch_completed"
                })
            except Exception:
                pass
                
        except Exception as e:
            scrape_page.page_id = None
            record_failure(db, scrape_page, "v2_batch_error", f"V2 batch processing failed: {str(e)}")
            pages_failed += 1
            logger.error(f"Failed to process page in V2 batch: {scrape_page.original_url}: {str(e)}")
    
    # Commit all changes
    db.commit()
    
    # Re-sync the pages created/linked above with Meilisearch (await directly: already async).
    try:
        await reindex_pages_and_mark(db, page_ids_to_index)
    except Exception as e:
        logger.error(f"Meilisearch indexing failed for V2 batch: {e}")

    logger.info(f"V2 batch processing completed: {pages_created} pages created, {pages_failed} failed")
    return pages_created, pages_failed


def _needs_wayback(scrape_page: ScrapePage) -> bool:
    """True when fetching this page sends a request to web.archive.org (Common Crawl pages do not)."""
    return scrape_page.warc_filename is None and "web.archive.org" in (scrape_page.content_url or "")


async def _wayback_pause_remaining() -> float:
    """Seconds left on the global Wayback pause; 0 when not paused or Redis cannot be read."""
    try:
        return await get_archive_rate_limiter().pause_remaining()
    except Exception as exc:
        logger.warning(f"Could not read the Wayback pause state (the limiter will still gate each request): {exc}")
        return 0.0


async def _process_individual_firecrawl(db, scrape_session, domain, task_self, scrape_session_id,
                                        scrape_page_ids: Optional[List[int]] = None):
    """
    Fetch and extract pending ScrapePage records one by one (rolling window).

    Args:
        db: Database session
        scrape_session: ScrapeSession object
        domain: Domain object
        task_self: Celery task instance for state updates
        scrape_session_id: ID of the scrape session
        scrape_page_ids: When given (retry runs), process exactly these PENDING rows and leave
            the session's counters alone; otherwise process the session's PENDING rows.

    Returns:
        Tuple of (pages_created, pages_failed) — "created" counts every page that was
        resolved: a new Page, or a link to an existing one (digest reuse, duplicate content).
    """
    from collections import deque

    pages_created = 0
    pages_failed = 0
    retry_mode = scrape_page_ids is not None
    project_id = domain.project_id

    conditions = [ScrapePage.status == ScrapePageStatus.PENDING]
    if retry_mode:
        conditions.append(ScrapePage.id.in_(scrape_page_ids))
    else:
        conditions += [ScrapePage.domain_id == domain.id, ScrapePage.scrape_session_id == scrape_session_id,
                       # rows the limiter deferred wait for their retry time (retry_failed_scrape_pages)
                       or_(ScrapePage.next_retry_at.is_(None), ScrapePage.next_retry_at <= utcnow())]
    pending_scrape_pages = db.execute(
        select(ScrapePage).where(*conditions).order_by(ScrapePage.id)
    ).scalars().all()

    page_ids_pending_index: List[Any] = []
    # digest -> Page id, filled as pages are created so identical captures later in this
    # run are linked instead of fetched.
    digest_to_page: Dict[str, Any] = {}

    # Pages that already exist for this URL+timestamp need no fetch, only the project link.
    scrape_pages_to_process = []
    for scrape_page in pending_scrape_pages:
        existing_page = find_page_by_url_timestamp(db, scrape_page.original_url, scrape_page.unix_timestamp)
        if existing_page is None:
            scrape_pages_to_process.append(scrape_page)
            continue
        if link_scrape_page(db, scrape_page, existing_page, project_id, ERROR_EXISTING_PAGE,
                            f"Page {existing_page} already exists for this URL and timestamp"):
            page_ids_pending_index.append(existing_page)
        pages_created += 1
    db.commit()

    # Early stop check function
    def _should_stop_individual(local_db: Session, session_id: int) -> bool:
        sess = local_db.get(scrape_session.__class__, session_id)
        if not sess:
            return True
        try:
            return sess.status in {scrape_session.status.__class__.CANCELLED, scrape_session.status.__class__.FAILED}
        except Exception:
            return False

    class _ShimCDXRecord:
        """CDX-like record built from a ScrapePage, for content extraction."""

        def __init__(self, scrape_page):
            self.original_url = scrape_page.original_url
            self.content_url = scrape_page.content_url
            self.timestamp = scrape_page.unix_timestamp
            self.mime_type = scrape_page.mime_type
            self.status_code = scrape_page.status_code
            self.digest = scrape_page.digest_hash
            self.content_length_bytes = scrape_page.content_length
            self.capture_date = scrape_page.first_seen_at
            # Common Crawl captures are read from their WARC record (persisted on the row).
            self.warc_filename = scrape_page.warc_filename
            self.warc_offset = scrape_page.warc_offset
            self.warc_length = scrape_page.warc_length
            self.is_common_crawl = scrape_page.warc_filename is not None

    # Rolling-window processing: keep up to `concurrency` extractions in flight
    # and handle each result as it completes, instead of fixed batches that wait
    # on their slowest page (with rotating exits a single straggler can take
    # minutes). Results are committed/indexed every `flush_every` completions so
    # progress is durable and visible throughout million-page runs.
    extractor = get_content_extraction_service()
    concurrency = max(1, int(getattr(settings, "SCRAPE_CONTENT_CONCURRENCY", 20)))
    flush_every = 10

    extraction_sem = asyncio.Semaphore(concurrency)

    async def _run_one(scrape_page, rec):
        async with extraction_sem:
            extracted = await _extract_one_record(extractor, rec)
        return scrape_page, rec, extracted

    total_to_process = len(scrape_pages_to_process)
    queue = deque(scrape_pages_to_process)
    deferred: List[ScrapePage] = []  # same digest as a page still in flight: wait for its result
    held: List[ScrapePage] = []  # Wayback pages held back while all Wayback traffic is paused
    limiter_deferred = 0  # pages the limiter refused: back to pending, not an attempt, not failed
    inflight_digests = set()
    in_flight: Dict[asyncio.Task, ScrapePage] = {}
    processed_count = 0
    since_flush = 0
    stop_requested = False

    logger.info(
        f"Processing {total_to_process} pending ScrapePage records "
        f"with a rolling window of {concurrency}"
        + (" (retry run)" if retry_mode else "")
    )

    while True:
        # Top up the window. All DB access stays in this coroutine — the
        # extraction tasks only do network fetches and parsing.
        queue.extend(deferred)
        deferred.clear()
        wayback_paused_for = await _wayback_pause_remaining()
        if held and wayback_paused_for <= 0:
            queue.extend(held)
            held.clear()
        dirty = False
        while not stop_requested and queue and len(in_flight) < concurrency * 2:
            scrape_page = queue.popleft()
            if wayback_paused_for > 0 and _needs_wayback(scrape_page):
                # Wayback is paused: do not dispatch (every dispatch would just be refused).
                held.append(scrape_page)
                continue
            digest = scrape_page.digest_hash
            if digest:
                reuse_page = digest_to_page.get(digest) or find_page_by_digest(db, digest)
                if reuse_page is not None:
                    digest_to_page[digest] = reuse_page
                    if link_scrape_page(db, scrape_page, reuse_page, project_id, ERROR_DIGEST_REUSE,
                                        f"Reused page {reuse_page}: identical archive payload digest {digest}"):
                        page_ids_pending_index.append(reuse_page)
                    pages_created += 1
                    processed_count += 1
                    since_flush += 1
                    dirty = True
                    continue
                if digest in inflight_digests:
                    deferred.append(scrape_page)
                    continue
                inflight_digests.add(digest)
            scrape_page.status = ScrapePageStatus.IN_PROGRESS
            scrape_page.last_attempt_at = datetime.utcnow()
            scrape_page.next_retry_at = None  # a deferral's wake-up time no longer applies
            dirty = True
            try:
                from app.services.websocket_service import broadcast_page_progress_sync
                broadcast_page_progress_sync({
                    "scrape_session_id": scrape_page.scrape_session_id,
                    "scrape_page_id": scrape_page.id,
                    "domain_id": domain.id,
                    "domain_name": domain.domain_name,
                    "page_url": scrape_page.original_url,
                    "content_url": scrape_page.content_url,
                    "status": ScrapePageStatus.IN_PROGRESS,
                    "processing_stage": "content_fetch"
                })
            except Exception:
                pass
            task = asyncio.create_task(_run_one(scrape_page, _ShimCDXRecord(scrape_page)))
            in_flight[task] = scrape_page
        if dirty:
            db.commit()

        if not in_flight:
            if deferred and not stop_requested:
                continue  # the page they waited for is done; re-check them against it
            if held and not stop_requested:
                if wayback_paused_for <= 0:
                    continue  # the pause ended meanwhile; dispatch them
                if wayback_paused_for <= float(settings.WAYBACK_ACQUIRE_TIMEOUT):
                    logger.info(
                        f"Wayback paused for {wayback_paused_for:.0f}s; holding {len(held)} pages "
                        f"(nothing in flight) until it ends"
                    )
                    await asyncio.sleep(wayback_paused_for + 0.5)
                    continue
                # A long pause: leave the rest to the beat retry instead of blocking a worker.
                resume_at = None
                for held_page in held:
                    resume_at = defer_scrape_page(held_page, wayback_paused_for)
                limiter_deferred += len(held)
                logger.warning(
                    f"Wayback paused for {wayback_paused_for:.0f}s: deferred {len(held)} pages to "
                    f"{resume_at.isoformat()} without consuming retries (session {scrape_session_id})"
                )
                held.clear()
                db.commit()
            break

        done, _ = await asyncio.wait(in_flight.keys(), return_when=asyncio.FIRST_COMPLETED)
        drained = []
        for finished in done:
            sp = in_flight.pop(finished)
            try:
                _sp, rec, extracted = finished.result()
                drained.append((sp, rec, extracted))
            except Exception as e:
                drained.append((sp, None, {
                    '_extraction_error': True,
                    'error': str(e),
                    'error_type': type(e).__name__,
                }))

        # Process completed results and create pages with indexing
        for scrape_page, cdx_record, extracted_content in drained:
            inflight_digests.discard(scrape_page.digest_hash)
            try:
                # --- Classification of extraction results ---
                fetch_time = (extracted_content or {}).get('fetch_time')

                if extracted_content is None:
                    record_failure(db, scrape_page, "no_data", "Extraction returned no data")
                    pages_failed += 1

                elif extracted_content.get('_deferred'):
                    # The limiter refused (Wayback paused / no capacity in time): nothing was sent,
                    # so this is not an attempt. Back to pending, looked at again after the pause;
                    # retry_count and the failed counters stay untouched.
                    resume_at = defer_scrape_page(scrape_page, extracted_content.get('retry_after'))
                    limiter_deferred += 1  # stays pending; the beat retry task picks it up at next_retry_at
                    logger.info(
                        f"Deferred scrape_page={scrape_page.id} until {resume_at.isoformat()} "
                        f"(retry_count stays {scrape_page.retry_count}): {extracted_content.get('error')}"
                    )

                elif extracted_content.get('_fetch_error'):
                    # The archive fetch itself failed: honest, typed, retried later with backoff
                    # (non-retryable types such as a 404 stay failed).
                    record_failure(
                        db, scrape_page, extracted_content.get('error_type', 'fetch_error'),
                        extracted_content.get('error', 'Archive fetch failed'),
                        retryable=extracted_content.get('retryable', True),
                        retry_after=extracted_content.get('retry_after'),
                        status_code=extracted_content.get('status_code'),
                        fetch_time=fetch_time,
                    )
                    pages_failed += 1

                elif extracted_content.get('_extraction_error'):
                    # Unexpected exception during extraction — retriable
                    error_msg = extracted_content.get('error', 'Unknown extraction error')
                    record_failure(
                        db, scrape_page, extracted_content.get('error_type', 'extraction_exception'),
                        f"Extraction exception: {error_msg}", fetch_time=fetch_time,
                    )
                    scrape_page.filter_details = {
                        "error": error_msg,
                        "error_type": extracted_content.get('error_type', 'unknown'),
                    }
                    pages_failed += 1

                elif extracted_content.get('_low_content'):
                    # Fetched fine but content is below threshold — SKIPPED, not FAILED
                    wc = extracted_content.get('word_count', 0)
                    method = extracted_content.get('extraction_method', 'unknown')
                    title = extracted_content.get('title', '')
                    preview = extracted_content.get('text_preview', '')

                    scrape_page.status = ScrapePageStatus.SKIPPED
                    scrape_page.fetch_time = fetch_time
                    scrape_page.error_message = (
                        f"Low content: {wc} words (min 50) via {method}. "
                        f"Title: '{title[:80]}'"
                    )
                    scrape_page.error_type = "insufficient_content"
                    scrape_page.filter_details = {
                        "word_count": wc,
                        "min_threshold": 50,
                        "extraction_method": method,
                        "title": title[:200] if title else None,
                        "text_preview": preview[:300] if preview else None,
                        "reason": "low_content",
                    }
                    scrape_page.retry_count += 1
                    pages_failed += 1
                    logger.info(
                        f"Low content SKIPPED for {scrape_page.original_url}: "
                        f"{wc} words via {method}"
                    )

                elif extracted_content.get('word_count', 0) > 50:
                    # Successful extraction with enough content: one Page row holds the text.
                    scrape_page.fetch_time = fetch_time
                    with db.begin_nested():
                        outcome = persist_extracted_page(db, scrape_page, project_id, extracted_content)
                    pages_created += 1
                    if scrape_page.digest_hash:
                        digest_to_page[scrape_page.digest_hash] = outcome.page_id
                    if outcome.created_page or outcome.project_page_created:
                        page_ids_pending_index.append(outcome.page_id)

                    # Broadcast successful completion
                    try:
                        from app.services.websocket_service import broadcast_page_progress_sync
                        broadcast_page_progress_sync({
                            "scrape_session_id": scrape_session_id,
                            "scrape_page_id": scrape_page.id,
                            "domain_id": domain.id,
                            "domain_name": domain.domain_name,
                            "page_url": scrape_page.original_url,
                            "content_url": scrape_page.content_url,
                            "status": ScrapePageStatus.COMPLETED,
                            "processing_stage": "content_extract"
                        })
                    except Exception:
                        pass

                else:
                    # Fallback — extraction returned data but word_count check failed
                    wc = extracted_content.get('word_count', 0)
                    scrape_page.status = ScrapePageStatus.SKIPPED
                    scrape_page.fetch_time = fetch_time
                    scrape_page.error_message = f"Content below threshold: {wc} words (min 50)"
                    scrape_page.error_type = "insufficient_content"
                    scrape_page.filter_details = {
                        "word_count": wc,
                        "min_threshold": 50,
                        "reason": "low_content",
                    }
                    scrape_page.retry_count += 1
                    pages_failed += 1

            except Exception as e:
                # Persisting the result failed (e.g. a concurrent insert); keep it retryable.
                scrape_page.page_id = None
                record_failure(db, scrape_page, "persist_error", str(e))
                pages_failed += 1
                logger.error(f"Failed to store page for {scrape_page.original_url}: {str(e)}")

        # Broadcast page-level failures so the live log shows them (successful
        # pages are broadcast at creation time above).
        for scrape_page, _rec, _extracted in drained:
            if scrape_page.status in (ScrapePageStatus.FAILED, ScrapePageStatus.SKIPPED):
                try:
                    from app.services.websocket_service import broadcast_page_progress_sync
                    broadcast_page_progress_sync({
                        "scrape_session_id": scrape_session_id,
                        "scrape_page_id": scrape_page.id,
                        "domain_id": domain.id,
                        "domain_name": domain.domain_name,
                        "page_url": scrape_page.original_url,
                        "content_url": scrape_page.content_url,
                        "status": scrape_page.status,
                        "processing_stage": "content_extract",
                        "error_message": scrape_page.error_message,
                        "error_type": scrape_page.error_type,
                    })
                except Exception:
                    pass

        processed_count += len(drained)
        since_flush += len(drained)

        if since_flush >= flush_every or not in_flight:
            since_flush = 0

            # Persist statuses/pages; keep the session row live for the UI (retry runs
            # must not overwrite the counters of the session that originally created the rows).
            if not retry_mode:
                scrape_session.completed_urls = pages_created
                scrape_session.failed_urls = pages_failed
            db.commit()

            # Re-sync the pages created/linked since the last flush with Meilisearch
            # (await directly; we are already inside an async context).
            if page_ids_pending_index:
                try:
                    await reindex_pages_and_mark(db, page_ids_pending_index)
                except Exception as e:
                    logger.error(f"Meilisearch indexing failed for flush: {e}")
                page_ids_pending_index = []

            # Session-level stats for the live log / WS clients
            if not retry_mode:
                try:
                    from app.services.websocket_service import broadcast_session_stats_sync
                    broadcast_session_stats_sync({
                        "scrape_session_id": scrape_session_id,
                        "total_urls": total_to_process,
                        "pending_urls": max(0, total_to_process - processed_count - len(in_flight)) + limiter_deferred,
                        "in_progress_urls": len(in_flight),
                        "completed_urls": pages_created,
                        "failed_urls": pages_failed,
                        "skipped_urls": 0,
                        "progress_percentage": (processed_count / total_to_process * 100) if total_to_process else 100.0,
                        "active_domains": 1,
                        "completed_domains": 0,
                        "failed_domains": 0,
                    })
                except Exception:
                    pass

            task_self.update_state(
                state="PROGRESS",
                meta={
                    "current": 3,
                    "total": 4,
                    "status": f"Processed {processed_count}/{total_to_process} pages...",
                    "domain_id": domain.id,
                    "pages_processed": pages_created + pages_failed,
                    "total_pages": total_to_process
                }
            )

            logger.info(
                f"Progress: {processed_count}/{total_to_process} processed "
                f"({pages_created} pages created, {pages_failed} failed, {len(in_flight)} in flight)"
            )

            # Re-read the session status for cancellation. The task session uses
            # expire_on_commit=False, so db.get() would return the cached (stale)
            # instance without an expire first.
            if not stop_requested and not retry_mode:
                db.expire(scrape_session)
                if _should_stop_individual(db, scrape_session_id):
                    stop_requested = True
                    logger.info(
                        f"Session {scrape_session_id} cancelled; draining "
                        f"{len(in_flight)} in-flight pages and stopping"
                    )

    # Rows still waiting when a cancel stopped the run stay pending (reset from nothing: never marked in_progress).
    if page_ids_pending_index:
        db.commit()
        await reindex_pages_and_mark(db, page_ids_pending_index)
    db.commit()
    logger.info(
        f"Individual processing completed: {pages_created} pages created, {pages_failed} failed, "
        f"{limiter_deferred} deferred (pending, retry later)"
    )
    return pages_created, pages_failed


@celery_app.task(bind=True, name="app.tasks.firecrawl_scraping.process_requeued_scrape_pages")
def process_requeued_scrape_pages(self, scrape_page_ids: List[int]) -> Dict[str, Any]:
    """Fetch/extract specific PENDING scrape pages (re-queued failures or reaped rows), by domain/session."""
    db = get_sync_session()
    try:
        rows = db.execute(
            select(ScrapePage).where(ScrapePage.id.in_(scrape_page_ids), ScrapePage.status == ScrapePageStatus.PENDING)
        ).scalars().all()
        created = failed = 0
        for (domain_id, session_id), ids in group_ids_by_session(rows).items():
            domain = db.get(Domain, domain_id)
            session = db.get(ScrapeSession, session_id) if session_id else None
            if domain is None:
                logger.warning(f"Cannot process re-queued scrape pages {ids[:5]}...: domain {domain_id} missing")
                continue
            c, f = run_async_in_sync(_process_individual_firecrawl(
                db, session, domain, self, session_id, scrape_page_ids=ids))
            created += c
            failed += f
        logger.info(f"Re-queued scrape pages processed: {created} resolved, {failed} failed")
        return {"requested": len(scrape_page_ids), "resolved": created, "failed": failed}
    finally:
        db.close()


@celery_app.task(name="app.tasks.firecrawl_scraping.retry_failed_scrape_pages")
def retry_failed_scrape_pages() -> Dict[str, Any]:
    """Beat task: re-queue due retryable failures (SCRAPE_RETRY_BATCH per run) and process them."""
    db = get_sync_session()
    try:
        rows = requeue_due_failures(db)
        ids = [r.id for r in rows]
    finally:
        db.close()
    if ids:
        process_requeued_scrape_pages.delay(ids)
    return {"requeued": len(ids)}


@celery_app.task(name="app.tasks.firecrawl_scraping.reap_stale_scrape_pages")
def reap_stale_scrape_pages() -> Dict[str, Any]:
    """Beat task: unstick scrape pages left in_progress by a dead worker and re-process the reset ones."""
    db = get_sync_session()
    try:
        result = reap_stale_in_progress(db)
        reset_ids = result.pop("reset_ids")
    finally:
        db.close()
    if reset_ids:
        process_requeued_scrape_pages.delay(reset_ids)
    return result


# Incremental Scraping Tasks


@celery_app.task(bind=True)
def scrape_domain_incremental(self, domain_id: int, run_type: str = "scheduled") -> Dict[str, Any]:
    """
    Dedicated incremental scraping task that handles the complete incremental workflow.
    
    This task:
    1. Determines optimal date range for incremental scraping
    2. Creates incremental history record
    3. Runs the main scraping task with incremental mode enabled
    4. Updates domain coverage and statistics
    
    Args:
        domain_id: ID of the domain to scrape incrementally
        run_type: Type of incremental run ("scheduled", "gap_fill", "backfill", "manual")
        
    Returns:
        Dictionary with incremental scraping results
    """
    logger.info(f"Starting incremental scraping for domain {domain_id}, run_type: {run_type}")
    
    try:
        # Convert run_type string to enum
        if run_type == "scheduled":
            incremental_run_type = IncrementalRunType.SCHEDULED
        elif run_type == "gap_fill":
            incremental_run_type = IncrementalRunType.GAP_FILL
        elif run_type == "backfill":
            incremental_run_type = IncrementalRunType.BACKFILL
        elif run_type == "manual":
            incremental_run_type = IncrementalRunType.MANUAL
        else:
            incremental_run_type = IncrementalRunType.SCHEDULED
        
        # Determine scraping range using async service
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            async def setup_incremental_run():
                from app.core.database import get_async_session
                async_db = anext(get_async_session())
                async_db_session = await async_db
                
                try:
                    # Check if incremental scraping should be triggered
                    should_trigger, trigger_metadata = await IncrementalScrapingService.should_trigger_incremental(
                        async_db_session, domain_id, force_check=(run_type == "manual")
                    )
                    
                    if not should_trigger:
                        return {
                            "status": "skipped",
                            "domain_id": domain_id,
                            "reason": trigger_metadata.get("reason", "not_triggered"),
                            "metadata": trigger_metadata
                        }
                    
                    # Determine optimal scraping range
                    start_date, end_date, range_metadata = await IncrementalScrapingService.determine_scraping_range(
                        async_db_session, domain_id, incremental_run_type
                    )
                    
                    if not start_date or not end_date:
                        return {
                            "status": "skipped",
                            "domain_id": domain_id,
                            "reason": range_metadata.get("reason", "no_date_range"),
                            "metadata": range_metadata
                        }
                    
                    # Create incremental history record
                    config = {
                        "run_type": run_type,
                        "date_range": {
                            "start": start_date.isoformat(),
                            "end": end_date.isoformat()
                        },
                        "trigger_metadata": trigger_metadata,
                        **range_metadata
                    }
                    
                    history_id = await IncrementalScrapingService.create_incremental_history(
                        async_db_session, domain_id, incremental_run_type,
                        start_date, end_date, config, 
                        trigger_reason=trigger_metadata.get("reason")
                    )
                    
                    if not history_id:
                        return {
                            "status": "failed",
                            "domain_id": domain_id,
                            "reason": "failed_to_create_history"
                        }
                    
                    return {
                        "status": "success",
                        "start_date": start_date,
                        "end_date": end_date,
                        "history_id": history_id,
                        "trigger_metadata": trigger_metadata,
                        "range_metadata": range_metadata
                    }
                finally:
                    await async_db_session.close()
            
            setup_result = run_async_in_sync(setup_incremental_run)
            
            if setup_result["status"] != "success":
                return setup_result
                
            start_date = setup_result["start_date"]
            end_date = setup_result["end_date"]
            history_id = setup_result["history_id"]
            trigger_metadata = setup_result["trigger_metadata"]
            range_metadata = setup_result["range_metadata"]
            
        finally:
            loop.close()
        
        # Create scrape session for this incremental run
        db = get_sync_session()
        try:
            from app.models.project import Domain
            domain = db.get(Domain, domain_id)
            if not domain:
                error_msg = f"Domain {domain_id} not found - may have been deleted during incremental scraping"
                logger.error(error_msg)
                
                # Log error to PageErrorLog
                from app.models.scraping import PageErrorLog
                error_log = PageErrorLog(
                    error_type="domain_not_found",
                    error_message=error_msg,
                    error_details={
                        "domain_id": domain_id,
                        "run_type": run_type,
                        "task_id": None,
                        "function": "scrape_domain_incremental",
                        "recovery_action": "verify_domain_exists_before_retry"
                    },
                    wayback_url="unknown",
                    original_url="unknown",
                    is_recoverable=False,
                    suggested_retry_delay=None
                )
                
                # Create sync session and add error log
                sync_db = get_sync_session()
                try:
                    sync_db.add(error_log)
                    sync_db.commit()
                finally:
                    sync_db.close()
                
                return {
                    "status": "failed",
                    "error": "domain_not_found",
                    "message": error_msg,
                    "domain_id": domain_id,
                    "run_type": run_type,
                    "pages_created": 0,
                    "pages_failed": 0,
                    "runtime_seconds": 0
                }
            
            scrape_session = ScrapeSession(
                project_id=domain.project_id,
                session_name=f"Incremental scrape ({run_type}) - {domain.domain_name}",
                status=ScrapeSessionStatus.PENDING,
                total_urls=0,
                completed_urls=0,
                failed_urls=0,
                cancelled_urls=0
            )
            
            db.add(scrape_session)
            db.commit()
            db.refresh(scrape_session)
            
            session_id = scrape_session.id
            
        finally:
            db.close()
        
        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={
                "status": f"Running incremental scraping ({run_type})",
                "domain_id": domain_id,
                "history_id": history_id,
                "date_range": f"{start_date.date()} to {end_date.date()}"
            }
        )
        
        # Run the main scraping task with incremental mode enabled
        scraping_result = scrape_domain_with_intelligent_extraction.apply(
            args=[domain_id, session_id, history_id, True],
            throw=True
        )
        
        # Extract result
        result = scraping_result.get()
        
        logger.info(f"Incremental scraping completed for domain {domain_id}: {result.get('pages_created', 0)} pages created")
        
        return {
            "status": "completed",
            "domain_id": domain_id,
            "history_id": history_id,
            "session_id": session_id,
            "run_type": run_type,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "scraping_result": result,
            "message": f"Incremental scraping ({run_type}) completed for domain {domain_id}"
        }
        
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Incremental scraping failed for domain {domain_id}: {error_msg}")
        
        # Update history record with failure if we created one
        if 'history_id' in locals():
            try:
                async def update_incremental_failure():
                    from app.core.database import get_async_session
                    async_db = anext(get_async_session())
                    async_db_session = await async_db
                    try:
                        failure_stats = {
                            "status": "failed",
                            "error_message": error_msg,
                            "error_details": {"exception_type": type(exc).__name__}
                        }
                        
                        await IncrementalScrapingService.update_incremental_statistics(
                            async_db_session, domain_id, history_id, failure_stats
                        )
                    finally:
                        await async_db_session.close()
                
                run_async_in_sync(update_incremental_failure)
            except Exception as e:
                logger.warning(f"Failed to update incremental history failure: {e}")
        
        raise


@celery_app.task(bind=True)
def check_domains_for_incremental(self, force_check: bool = False) -> Dict[str, Any]:
    """
    Scheduled task to check all domains for incremental scraping needs.
    
    This task:
    1. Finds all domains with incremental scraping enabled
    2. Checks each domain to see if incremental scraping should be triggered
    3. Queues incremental scraping tasks for qualifying domains
    
    Args:
        force_check: Force check all domains regardless of schedule
        
    Returns:
        Dictionary with check results and queued tasks
    """
    logger.info(f"Checking domains for incremental scraping (force_check: {force_check})")
    
    try:
        # Get all domains with incremental scraping enabled
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            async def check_and_queue_domains():
                from app.core.database import get_async_session
                from app.models.project import Domain
                from sqlalchemy import and_
                async_db = anext(get_async_session())
                async_db_session = await async_db
                
                try:
                    # Find domains with incremental scraping enabled
                    stmt = select(Domain).where(
                        and_(
                            Domain.incremental_enabled == True,
                            Domain.status != DomainStatus.ARCHIVED
                        )
                    )
                    result = await async_db_session.execute(stmt)
                    domains = result.scalars().all()
                    
                    logger.info(f"Found {len(domains)} domains with incremental scraping enabled")
                    
                    # Check each domain for incremental scraping needs
                    tasks_queued = []
                    domains_checked = 0
                    domains_triggered = 0
                    
                    for domain in domains:
                        domains_checked += 1
                        
                        try:
                            should_trigger, metadata = await IncrementalScrapingService.should_trigger_incremental(
                                async_db_session, domain.id, force_check=force_check
                            )
                            
                            if should_trigger:
                                # Queue incremental scraping task
                                task = scrape_domain_incremental.delay(domain.id, "scheduled")
                                
                                tasks_queued.append({
                                    "domain_id": domain.id,
                                    "domain_name": domain.domain_name,
                                    "task_id": task.id,
                                    "trigger_reason": metadata.get("reason"),
                                    "metadata": metadata
                                })
                                
                                domains_triggered += 1
                                logger.info(f"Queued incremental scraping for domain {domain.id}: {domain.domain_name}")
                                
                        except Exception as e:
                            logger.error(f"Error checking domain {domain.id} for incremental scraping: {e}")
                    
                    return {
                        "domains_checked": domains_checked,
                        "domains_triggered": domains_triggered,
                        "tasks_queued": tasks_queued
                    }
                finally:
                    await async_db_session.close()
            
            check_result = run_async_in_sync(check_and_queue_domains)
            
        finally:
            loop.close()
        
        result = {
            "status": "completed",
            "domains_checked": check_result["domains_checked"],
            "domains_triggered": check_result["domains_triggered"],
            "tasks_queued": len(check_result["tasks_queued"]),
            "queued_tasks": check_result["tasks_queued"],
            "force_check": force_check,
            "message": f"Checked {check_result['domains_checked']} domains, queued {len(check_result['tasks_queued'])} incremental tasks"
        }
        
        logger.info(f"Domain incremental check completed: {result['message']}")
        return result
        
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Domain incremental check failed: {error_msg}")
        raise


@celery_app.task(bind=True)
def fill_coverage_gaps(self, domain_id: int, max_gaps: int = 3) -> Dict[str, Any]:
    """
    Task to identify and fill coverage gaps for a domain.
    
    This task:
    1. Identifies critical gaps in domain coverage
    2. Prioritizes gaps by importance
    3. Queues gap-fill tasks for the most critical gaps
    
    Args:
        domain_id: ID of the domain to analyze
        max_gaps: Maximum number of gaps to fill in this run
        
    Returns:
        Dictionary with gap analysis and fill results
    """
    logger.info(f"Starting gap fill analysis for domain {domain_id}")
    
    try:
        # Run gap analysis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            async def analyze_and_queue_gaps():
                from app.core.database import get_async_session
                async_db = anext(get_async_session())
                async_db_session = await async_db
                
                try:
                    # Get domain information
                    domain = await IncrementalScrapingService._get_domain(async_db_session, domain_id)
                    if not domain:
                        return {
                            "status": "failed",
                            "domain_id": domain_id,
                            "reason": "domain_not_found"
                        }
                    
                    if not domain.incremental_enabled:
                        return {
                            "status": "skipped",
                            "domain_id": domain_id,
                            "reason": "incremental_disabled"
                        }
                    
                    # Identify critical gaps
                    critical_gaps = await IncrementalScrapingService.identify_critical_gaps(async_db_session, domain_id)
                    
                    if not critical_gaps:
                        return {
                            "status": "completed",
                            "domain_id": domain_id,
                            "gaps_found": 0,
                            "gaps_queued": 0,
                            "message": "No critical gaps found"
                        }
                    
                    # Prioritize gaps
                    prioritized_gaps = await IncrementalScrapingService.prioritize_gaps(
                        async_db_session, domain_id, critical_gaps
                    )
                    
                    return {
                        "status": "success",
                        "domain": domain,
                        "critical_gaps": critical_gaps,
                        "prioritized_gaps": prioritized_gaps
                    }
                finally:
                    await async_db_session.close()
            
            gap_analysis = run_async_in_sync(analyze_and_queue_gaps)
            
            if gap_analysis["status"] != "success":
                return gap_analysis
            
            domain = gap_analysis["domain"]
            critical_gaps = gap_analysis["critical_gaps"]
            prioritized_gaps = gap_analysis["prioritized_gaps"]
            
            # Queue gap-fill tasks for top gaps
            gaps_to_fill = prioritized_gaps[:max_gaps]
            queued_tasks = []
            
            for i, gap in enumerate(gaps_to_fill):
                try:
                    # Queue incremental scraping task with gap_fill type
                    task = scrape_domain_incremental.delay(domain_id, "gap_fill")
                    
                    queued_tasks.append({
                        "gap_index": i,
                        "task_id": task.id,
                        "gap_info": gap,
                        "estimated_duration": gap.get("estimated_processing_time", {})
                    })
                    
                    logger.info(f"Queued gap fill task for domain {domain_id}: {gap['start_date']} to {gap['end_date']}")
                    
                except Exception as e:
                    logger.error(f"Failed to queue gap fill task for domain {domain_id}: {e}")
            
        finally:
            loop.close()
        
        result = {
            "status": "completed",
            "domain_id": domain_id,
            "domain_name": domain.domain_name,
            "gaps_found": len(critical_gaps),
            "gaps_prioritized": len(prioritized_gaps),
            "gaps_queued": len(queued_tasks),
            "max_gaps_requested": max_gaps,
            "queued_tasks": queued_tasks,
            "critical_gaps": critical_gaps,
            "message": f"Queued {len(queued_tasks)} gap fill tasks for domain {domain_id}"
        }
        
        logger.info(f"Gap fill analysis completed: {result['message']}")
        return result
        
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Gap fill analysis failed for domain {domain_id}: {error_msg}")
        raise


@celery_app.task(bind=True)
def update_incremental_statistics(self) -> Dict[str, Any]:
    """
    Periodic task to update incremental scraping statistics for all domains.
    
    This task:
    1. Calculates coverage statistics for all domains
    2. Updates domain statistics and metadata
    3. Performs maintenance on incremental history records
    
    Returns:
        Dictionary with update results
    """
    logger.info("Starting incremental statistics update")
    
    try:
        # Get all domains with incremental scraping enabled
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            async def update_all_statistics():
                from app.core.database import get_async_session
                from app.models.project import Domain
                from sqlalchemy import func
                async_db = anext(get_async_session())
                async_db_session = await async_db
                
                try:
                    # Find domains with incremental scraping enabled
                    stmt = select(Domain).where(Domain.incremental_enabled == True)
                    result = await async_db_session.execute(stmt)
                    domains = result.scalars().all()
                    
                    logger.info(f"Updating statistics for {len(domains)} domains")
                    
                    domains_updated = 0
                    total_gaps_found = 0
                    total_coverage_calculated = 0
                    
                    for domain in domains:
                        try:
                            # Update domain coverage
                            coverage_updated = await IncrementalScrapingService.update_domain_coverage(
                                async_db_session, domain.id
                            )
                            
                            if coverage_updated:
                                domains_updated += 1
                                
                                # Get updated statistics
                                stats = await IncrementalScrapingService.get_scraping_statistics(
                                    async_db_session, domain.id
                                )
                                
                                total_gaps_found += stats.get("total_gaps", 0)
                                if stats.get("coverage_percentage") is not None:
                                    total_coverage_calculated += 1
                                
                                logger.debug(f"Updated statistics for domain {domain.id}: "
                                           f"{stats.get('coverage_percentage', 'N/A')}% coverage, "
                                           f"{stats.get('total_gaps', 0)} gaps")
                            
                        except Exception as e:
                            logger.error(f"Failed to update statistics for domain {domain.id}: {e}")
                    
                    # Clean up old incremental history records (keep last 100 per domain)
                    try:
                        from app.models.scraping import IncrementalScrapingHistory
                        
                        # This is a simplified cleanup - in practice, you might want more sophisticated logic
                        cleanup_stmt = select(func.count(IncrementalScrapingHistory.id))
                        cleanup_result = await async_db_session.execute(cleanup_stmt)
                        total_history_records = cleanup_result.scalar() or 0
                        
                        logger.info(f"Total incremental history records: {total_history_records}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to perform history cleanup: {e}")
                    
                    return {
                        "domains_processed": len(domains),
                        "domains_updated": domains_updated,
                        "total_gaps_found": total_gaps_found,
                        "domains_with_coverage": total_coverage_calculated
                    }
                    
                finally:
                    await async_db_session.close()
            
            update_result = run_async_in_sync(update_all_statistics)
            
        finally:
            loop.close()
        
        result = {
            "status": "completed",
            "domains_processed": update_result["domains_processed"],
            "domains_updated": update_result["domains_updated"],
            "total_gaps_found": update_result["total_gaps_found"],
            "domains_with_coverage": update_result["domains_with_coverage"],
            "message": f"Updated statistics for {update_result['domains_updated']}/{update_result['domains_processed']} domains"
        }
        
        logger.info(f"Incremental statistics update completed: {result['message']}")
        return result
        
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Incremental statistics update failed: {error_msg}")
        raise


async def _discover_and_filter_pages(domain: Domain, enable_attachments: bool = True):
    """
    Discover pages from archive sources and apply intelligent filtering.

    1. Query the project's archive source: Wayback, Common Crawl, or Hybrid (Common
       Crawl first, then Wayback records Common Crawl does not already cover).
    2. Look up which capture digests already exist as Pages (any project): those
       records are decided as "already processed" and linked by the caller, not fetched.
    3. Apply intelligent filtering to the rest.

    Returns:
        Tuple of (cdx_records, filtering_decisions, filter_stats)
    """
    logger.info(f"Starting archive discovery for domain {domain.domain_name} "
               f"using project archive configuration")

    # Get the project to access archive source configuration (use sync session to avoid loop issues)
    db = get_sync_session()
    try:
        project = db.get(Project, domain.project_id)
        if not project:
            raise Exception(f"Project not found for domain {domain.id}")
        from_date = domain.from_date.strftime("%Y%m%d") if domain.from_date else "20100101"
        to_date = domain.to_date.strftime("%Y%m%d") if domain.to_date else datetime.now().strftime("%Y%m%d")

        match_type = domain.match_type.value if hasattr(domain.match_type, 'value') else str(domain.match_type)
        archive_source_value = (project.archive_source if isinstance(project.archive_source, str)
                                else project.archive_source.value)
        routing_config = create_enhanced_routing_config_from_project(project)
    finally:
        db.close()

    logger.info(f"Querying archive source {archive_source_value} for {domain.domain_name} "
               f"from {from_date} to {to_date} (match_type: {match_type})")

    is_hybrid = archive_source_value == 'hybrid'
    is_cc = archive_source_value in ('common_crawl', 'commoncrawl') or is_hybrid
    is_wayback = archive_source_value in ('wayback', 'wayback_machine') or is_hybrid

    cc_records, wayback_records, archive_stats = [], [], {}

    if is_cc:
        from app.services.cc_simple_fetcher import fetch_cc_cdx_records
        try:
            cc_records, archive_stats = await fetch_cc_cdx_records(
                domain_name=domain.domain_name,
                from_date=from_date,
                to_date=to_date,
                match_type=match_type,
                url_path=domain.url_path,
                include_attachments=enable_attachments,
            )
            logger.info(f"Common Crawl fetch for {domain.domain_name}: {len(cc_records)} records")
        except Exception as exc:
            if not is_hybrid:
                raise
            logger.warning(f"Common Crawl discovery failed for {domain.domain_name}: {exc}; "
                           f"continuing with Wayback only")

    if is_wayback:
        from app.services.archive_service_router import ArchiveSource as BaseArchiveSource
        router = EnhancedArchiveServiceRouter(routing_config)
        wayback_records, wayback_stats = await router.query_archive_unified(
            domain=domain.domain_name,
            from_date=from_date,
            to_date=to_date,
            archive_source=BaseArchiveSource.WAYBACK_MACHINE,
            match_type=match_type,
            url_path=domain.url_path
        )
        archive_stats = {**archive_stats, **wayback_stats} if is_hybrid else wayback_stats

    if is_hybrid:
        cdx_records, merge_stats = merge_hybrid_records(
            cc_records, wayback_records,
            mode=settings.HYBRID_DEDUP_MODE, period=settings.HYBRID_DEDUP_PERIOD,
        )
        archive_stats = {**archive_stats, "hybrid_merge": merge_stats, "total_records": merge_stats["final"]}
    else:
        cdx_records = cc_records if is_cc else wayback_records

    if len(cdx_records) > settings.DISCOVERY_MAX_RECORDS:
        logger.warning(f"Discovery for {domain.domain_name} found {len(cdx_records)} records; "
                       f"truncating to DISCOVERY_MAX_RECORDS={settings.DISCOVERY_MAX_RECORDS}")
        cdx_records = cdx_records[:settings.DISCOVERY_MAX_RECORDS]

    logger.info(f"Archive query completed: {len(cdx_records)} records retrieved "
               f"({archive_source_value}) for {domain.domain_name}")

    if not cdx_records:
        logger.warning(f"No CDX records found for domain {domain.domain_name}")
        return [], [], {"total_pages": 0, "filtered_pages": 0, "filter_rate": 0.0}

    logger.info(f"Applying intelligent filtering to {len(cdx_records)} CDX records")
    intelligent_filter = get_enhanced_intelligent_filter()

    # Captures whose payload digest already exists as a Page anywhere are linked, not fetched.
    lookup_db = get_sync_session()
    try:
        digest_pages = find_pages_by_digests(lookup_db, (r.digest for r in cdx_records))
    finally:
        lookup_db.close()

    records_with_decisions, filter_stats = intelligent_filter.filter_records_with_individual_reasons(
        cdx_records,
        set(digest_pages),
        include_attachments=enable_attachments
    )

    filtered_records = []
    filtering_decisions = []
    for record, decision in records_with_decisions:
        if decision.reason == FilterReason.ALREADY_PROCESSED_DIGEST:
            decision.filter_details["existing_page_id"] = str(digest_pages[record.digest])
        filtering_decisions.append(decision)
        if decision.status in [ScrapePageStatus.PENDING, ScrapePageStatus.AWAITING_MANUAL_REVIEW]:
            filtered_records.append(record)

    logger.info(
        f"Intelligent filtering completed: {len(filtered_records)}/{len(cdx_records)} records to fetch, "
        f"{filter_stats.get('already_processed_filtered', 0)} reuse an existing page by digest"
    )
    return filtered_records, filtering_decisions, {**archive_stats, **filter_stats}
