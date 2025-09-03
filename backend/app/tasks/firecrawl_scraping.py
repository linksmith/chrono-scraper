"""
Intelligent extraction scraping tasks for Celery

This module provides a streamlined scraping system that:
1. Uses CDX API for discovery with intelligent filtering
2. Uses intelligent extraction for high-speed content processing
3. Provides simple, reliable task execution with 99.9% faster extraction
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlmodel import select, Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.models.project import Domain, Project, ScrapeSession, ScrapeSessionStatus, DomainStatus
from app.models.scraping import ScrapePage, ScrapePageStatus, IncrementalRunType, IncrementalRunStatus
from app.models.shared_pages import PageV2, ProjectPage
from app.services.content_extraction_service import get_content_extraction_service
from app.services.firecrawl_v2_client import FirecrawlV2Client, FirecrawlV2Error
from app.services.enhanced_intelligent_filter import get_enhanced_intelligent_filter
from app.services.archive_service_router import query_archive_unified
from app.services.meilisearch_service import meilisearch_service
from app.models.extraction_data import ExtractedContent
from app.services.incremental_scraping import IncrementalScrapingService

logger = logging.getLogger(__name__)


def get_sync_session():
    """Create a synchronous database session for Celery tasks"""
    engine = create_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,  # Disable connection pooling for Celery
        echo=False,
    )
    SessionLocal = sessionmaker(
        engine,
        class_=Session,
        expire_on_commit=False,
    )
    return SessionLocal()


def run_async_in_sync(async_func):
    """
    Helper to run async functions from sync Celery tasks.
    Creates a new event loop if needed and runs the async function.
    """
    try:
        # Try to get current loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(async_func)
            loop.close()
            return result
        else:
            return loop.run_until_complete(async_func)
    except RuntimeError:
        # No current loop, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(async_func)
            return result
        finally:
            loop.close()


@celery_app.task(bind=True)
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
            raise ValueError(f"Domain {domain_id} not found")
        if not scrape_session:
            raise ValueError(f"Scrape session {scrape_session_id} not found")
            
        # Get project to check attachment download setting
        from app.models.project import Project
        project = db.get(Project, domain.project_id)
        if not project:
            raise ValueError(f"Project {domain.project_id} not found")
            
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
        
        # Run async CDX discovery in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            cdx_records, all_filtering_decisions, filter_stats = loop.run_until_complete(
                _discover_and_filter_pages(domain, project.enable_attachment_download)
            )
        finally:
            loop.close()
        
        logger.info(f"CDX discovery completed: {len(cdx_records)} records after filtering")

        # If no new CDX records were found for a prefix target, try reusing existing
        # pages captured by other projects so the content is accessible without
        # re-scraping. This mirrors the user's expectation for shared archive data.
        try:
            if len(cdx_records) == 0:
                # Determine if this is a prefix target with a full URL path
                is_prefix = False
                try:
                    if hasattr(domain.match_type, 'value'):
                        is_prefix = (domain.match_type.value == "prefix")
                    elif isinstance(domain.match_type, str):
                        is_prefix = (domain.match_type == "prefix")
                    else:
                        is_prefix = (str(domain.match_type) == "prefix")
                except Exception:
                    is_prefix = False

                if is_prefix and (domain.url_path or "").startswith(("http://", "https://")):
                    prefix_path = domain.url_path
                    logger.info(f"No new CDX results; attempting reuse of existing pages for prefix: {prefix_path}")

                    # Find pages from other domains/projects that match this prefix
                    reused_count = 0
                    from app.models.shared_pages import PageV2 as PageModel
                    # Fetch a reasonable cap to avoid huge imports at once
                    existing_pages = db.execute(
                        select(PageModel)
                        .join(Domain, PageModel.domain_id == Domain.id)
                        .where(
                            Domain.domain_name == domain.domain_name,
                            Domain.id != domain.id,
                            PageModel.original_url.like(f"{prefix_path}%")
                        )
                        .order_by(PageModel.id.asc())
                    ).scalars().all()

                    logger.info(f"Found {len(existing_pages)} reusable pages from other projects for prefix")

                    for src in existing_pages:
                        try:
                            # Avoid duplicates within this domain
                            dup = db.execute(
                                select(Page)
                                .where(
                                    Page.domain_id == domain.id,
                                    Page.original_url == src.original_url,
                                    Page.unix_timestamp == src.unix_timestamp
                                )
                                .limit(1)
                            ).scalars().first()
                            if dup:
                                continue

                            cloned = Page(
                                domain_id=domain.id,
                                original_url=src.original_url,
                                content_url=src.content_url,
                                title=src.title or src.extracted_title,
                                extracted_text=src.extracted_text,
                                unix_timestamp=src.unix_timestamp,
                                mime_type=src.mime_type,
                                status_code=src.status_code,
                                meta_description=src.meta_description,
                                author=src.author,
                                language=src.language,
                                word_count=src.word_count,
                                character_count=src.character_count,
                                content_length=src.content_length,
                                capture_date=src.capture_date,
                                scraped_at=datetime.utcnow(),
                                processed=True,
                                indexed=False
                            )
                            db.add(cloned)
                            reused_count += 1
                        except Exception as e:
                            logger.warning(f"Failed to reuse page {src.original_url}: {e}")

                    db.commit()

                    if reused_count > 0:
                        # Update session/domain stats and return early (skip Firecrawl)
                        scrape_session.total_urls = reused_count
                        scrape_session.completed_urls = reused_count
                        scrape_session.failed_urls = 0
                        scrape_session.status = ScrapeSessionStatus.COMPLETED
                        scrape_session.completed_at = datetime.utcnow()

                        domain.total_pages += reused_count
                        domain.scraped_pages += reused_count
                        domain.last_scraped = datetime.utcnow()
                        db.commit()

                        logger.info(f"Reused {reused_count} existing pages for prefix target; skipping Firecrawl")
                        return {
                            "status": "completed",
                            "domain_name": domain.domain_name,
                            "domain_id": domain_id,
                            "session_id": scrape_session_id,
                            "pages_found": reused_count,
                            "pages_created": reused_count,
                            "pages_failed": 0,
                            "filter_stats": filter_stats,
                            "message": f"Reused {reused_count} existing pages (no new CDX)"
                        }
        except Exception:
            # Non-fatal: continue to normal flow
            pass
        
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
        
        # Step 4: Broadcast session-level statistics instead of page-level progress
        if batch_progress_data:
            try:
                from app.services.websocket_service import broadcast_session_stats_sync
                # Use session-level stats broadcast instead of page progress
                broadcast_session_stats_sync({
                    "scrape_session_id": scrape_session_id,
                    "pages_discovered": len(all_filtering_decisions),
                    "pages_created": scrape_pages_created,
                    "pages_pending": scrape_pages_created,  # All newly created pages are pending
                    "pages_completed": 0,
                    "pages_failed": 0,
                    "pages_filtered": len(all_filtering_decisions) - scrape_pages_created,
                    "pages_duplicates": len(existing_combinations)
                })
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

        if _should_stop(db, scrape_session_id):
            logger.info(f"Session {scrape_session_id} cancelled; stopping before processing pages")
            domain.status = DomainStatus.PAUSED
            scrape_session.status = ScrapeSessionStatus.CANCELLED
            scrape_session.completed_at = datetime.utcnow()
            db.commit()
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
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                pages_created, pages_failed = loop.run_until_complete(
                    _process_v2_batch_results(db, scrape_session, domain, cdx_records, self)
                )
            finally:
                loop.close()
        elif use_intelligent_only:
            # Use intelligent extraction only (bypass Firecrawl entirely)
            logger.info(f"Processing session {scrape_session_id} using intelligent extraction (robust content extractor)")
            
            # Process with individual intelligent extraction calls
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                pages_created, pages_failed = loop.run_until_complete(
                    _process_individual_firecrawl(db, scrape_session, domain, cdx_records, self, scrape_session_id)
                )
            finally:
                loop.close()
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
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    pages_created, pages_failed = loop.run_until_complete(
                        _process_individual_firecrawl(db, scrape_session, domain, cdx_records, self, scrape_session_id)
                    )
                finally:
                    loop.close()
        
        
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
            scrape_session.status = ScrapeSessionStatus.COMPLETED
            scrape_session.completed_at = datetime.utcnow()
        
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
                    scrape_session.status = ScrapeSessionStatus.FAILED
                    scrape_session.error_message = error_msg
                    
                db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update database after error: {db_error}")
        
        # Raise the exception and let Celery record proper failure metadata
        raise
        
    finally:
        if db:
            db.close()


async def _discover_and_filter_pages(domain: Domain, include_attachments: bool = True) -> tuple[List, List, Dict[str, Any]]:
    """
    Discover pages using archive service router with enhanced intelligent filtering that captures individual reasons
    
    Args:
        domain: Domain object to scrape
        include_attachments: Whether to include PDF and other attachments in scraping
        
    Returns:
        Tuple of (filtered_cdx_records, all_filtering_decisions, filter_statistics)
    """
    
    # Get project configuration for archive routing
    project_config = None
    try:
        # Create database session to query project
        db = get_sync_session()
        try:
            project = db.get(Project, domain.project_id)
            if project:
                # Extract archive configuration from project
                project_config = {
                    'archive_source': project.archive_source,
                    'fallback_enabled': project.fallback_enabled,
                    'archive_config': project.archive_config or {}
                }
                logger.info(f"Using archive source: {project.archive_source} for project {project.name}")
            else:
                logger.warning(f"Project {domain.project_id} not found, using default Wayback Machine")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to get project configuration: {e}, using default Wayback Machine")
    
    # Set up date range
    from_date = domain.from_date.strftime("%Y%m%d") if domain.from_date else "20200101"
    to_date = domain.to_date.strftime("%Y%m%d") if domain.to_date else datetime.now().strftime("%Y%m%d")
    
    # Get existing digests to avoid duplicates using enhanced filter
    enhanced_filter = get_enhanced_intelligent_filter()
    # Scope existing-digest lookup to domain_id and, for prefix targets, to the specific URL path
    prefix_path = None
    try:
        if hasattr(domain.match_type, 'value'):
            mt_val = domain.match_type.value
        elif isinstance(domain.match_type, str):
            mt_val = domain.match_type
        else:
            mt_val = str(domain.match_type)
        if mt_val == "prefix" and (domain.url_path or "").startswith(("http://", "https://")):
            prefix_path = domain.url_path
    except Exception:
        pass
    existing_digests = await enhanced_filter.get_existing_digests(
        domain.domain_name,
        domain_id=domain.id,
        url_prefix=prefix_path
    )
    
    logger.info(f"Found {len(existing_digests)} existing digests for {domain.domain_name}")
    logger.info(f"PDF attachment processing: {'ENABLED' if include_attachments else 'DISABLED'} for domain: {domain.domain_name}")
    
    # Handle both enum and string cases for match_type
    if hasattr(domain.match_type, 'value'):
        extracted_match_type = domain.match_type.value
    elif isinstance(domain.match_type, str):
        extracted_match_type = domain.match_type
    else:
        extracted_match_type = str(domain.match_type)
    
    # Determine CDX min_size dynamically:
    # For precise prefix targets (single URL captures), allow tiny captures
    # to ensure we don't filter out small but valid snapshots.
    min_size_for_cdx = 1000
    try:
        if extracted_match_type == "prefix" and (domain.url_path or "").startswith(("http://", "https://")):
            min_size_for_cdx = 0
    except Exception:
        pass

    # Fetch CDX records using archive service router with intelligent routing and fallback
    try:
        raw_records, raw_stats = await query_archive_unified(
            domain=domain.domain_name,
            from_date=from_date,
            to_date=to_date,
            project_config=project_config,
            match_type=extracted_match_type,
            url_path=domain.url_path
        )
        
        # Log which archive source was actually used
        if raw_stats and 'source_used' in raw_stats:
            logger.info(f"Successfully queried {raw_stats['source_used']} for domain {domain.domain_name}")
        
    except Exception as e:
        logger.error(f"Archive query failed for domain {domain.domain_name}: {e}")
        raise
    
    # Apply enhanced intelligent filtering that creates filtering decisions for ALL records
    records_with_decisions, filter_stats = enhanced_filter.filter_records_with_individual_reasons(
        raw_records, 
        existing_digests, 
        include_attachments=include_attachments
    )
    
    # Separate filtered records and all filtering decisions
    filtered_records = []
    all_filtering_decisions = []
    
    for record, decision in records_with_decisions:
        all_filtering_decisions.append(decision)
        # Only include records that should be processed further (not filtered out)
        if decision.status in [ScrapePageStatus.PENDING, ScrapePageStatus.AWAITING_MANUAL_REVIEW]:
            filtered_records.append(record)
    
    # Sort by priority (high-value content first)
    filtered_records.sort(
        key=lambda r: enhanced_filter.get_scraping_priority(r, include_attachments), 
        reverse=True
    )
    
    # Combine statistics
    combined_stats = {**raw_stats, **filter_stats}
    
    logger.info(f"CDX filtering complete: {len(raw_records)} -> {len(filtered_records)} records for processing")
    logger.info(f"Individual filtering decisions created for ALL {len(all_filtering_decisions)} discovered URLs")
    
    # Log static asset pre-filtering savings if any
    if combined_stats.get('static_assets_filtered', 0) > 0:
        logger.info(f"Static asset pre-filtering prevented {combined_stats['static_assets_filtered']} "
                   f"potential database entries (JS, CSS, images, etc.)")
    
    return filtered_records, all_filtering_decisions, combined_stats


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
            try:
                extracted_content = await extractor.extract_content(cdx_record)
                
                if extracted_content.text and len(extracted_content.text.strip()) > 50:
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
                        'extraction_time': extracted_content.extraction_time
                    }
                else:
                    logger.warning(f"Intelligent extraction returned minimal content for: {cdx_record.original_url}")
                    return None
                    
            except Exception as e:
                logger.error(f"Intelligent extraction failed for {cdx_record.original_url}: {str(e)}")
                return None
    
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
            raise ValueError(f"Domain {domain_id} not found")
        
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
    from app.models.shared_pages import PageV2 as Page
    
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
    
    # Filter out pages that already have final Page records
    scrape_pages_to_process = []
    for scrape_page in pending_scrape_pages:
        existing_page = db.execute(
            select(Page.id)
            .where(
                Page.domain_id == domain.id,
                Page.original_url == scrape_page.original_url,
                Page.unix_timestamp == scrape_page.unix_timestamp
            )
            .limit(1)
        ).scalars().first()
        
        if not existing_page:
            scrape_pages_to_process.append(scrape_page)
        else:
            scrape_page.status = ScrapePageStatus.COMPLETED
            scrape_page.completed_at = datetime.utcnow()
    
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
                scrape_page.status = ScrapePageStatus.FAILED
                scrape_page.error_message = "No Firecrawl batch result for this URL"
                scrape_page.error_type = "v2_batch_miss"
                scrape_page.retry_count += 1
                pages_failed += 1
                continue

            metadata = (doc.get("metadata") or {})
            title = metadata.get("title") or doc.get("title") or scrape_page.title or scrape_page.original_url
            markdown = doc.get("markdown") or ""
            html = doc.get("html") or doc.get("rawHtml") or ""
            status_code = metadata.get("statusCode")
            description = metadata.get("description")
            language = metadata.get("language")

            # Update ScrapePage with real values
            scrape_page.status = ScrapePageStatus.COMPLETED
            scrape_page.completed_at = datetime.utcnow()
            scrape_page.title = title
            scrape_page.extracted_text = markdown or html or ""
            scrape_page.extracted_content = html or ""
            scrape_page.markdown_content = markdown or ""
            scrape_page.extraction_method = "firecrawl_v2_batch"
            
            # Create final Page record
            page = Page(
                domain_id=domain.id,
                original_url=scrape_page.original_url,
                content_url=scrape_page.content_url,
                title=title,
                extracted_text=markdown or html or "",
                unix_timestamp=scrape_page.unix_timestamp,
                mime_type=scrape_page.mime_type,
                status_code=status_code or scrape_page.status_code,
                meta_description=description,
                language=language,
                word_count=len((markdown or html or "").split()),
                character_count=len(markdown or html or ""),
                content_length=scrape_page.content_length,
                capture_date=scrape_page.first_seen_at,
                scraped_at=datetime.utcnow(),
                processed=True,
                indexed=False
            )
            
            db.add(page)
            db.flush()
            
            pages_created += 1
            
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
            scrape_page.status = ScrapePageStatus.FAILED
            scrape_page.error_message = f"V2 batch processing failed: {str(e)}"
            scrape_page.error_type = "v2_batch_error"
            scrape_page.retry_count += 1
            pages_failed += 1
            logger.error(f"Failed to process page in V2 batch: {scrape_page.original_url}: {str(e)}")
    
    # Commit all changes
    db.commit()
    
    # Index pages to Meilisearch
    try:
        index_name = f"project_{domain.project_id}"
        async with meilisearch_service as ms:
            for scrape_page in scrape_pages_to_process:
                if scrape_page.status == ScrapePageStatus.COMPLETED:
                    # Find the corresponding page
                    page = db.execute(
                        select(Page)
                        .where(
                            Page.domain_id == domain.id,
                            Page.original_url == scrape_page.original_url,
                            Page.unix_timestamp == scrape_page.unix_timestamp
                        )
                        .limit(1)
                    ).scalars().first()
                    
                    if page:
                        # Create ExtractedContent object
                        extracted_content = ExtractedContent(
                            title=page.title or "No Title",
                            text=page.extracted_text or "",
                            markdown=page.extracted_text or "",
                            html="",
                            word_count=page.word_count or 0,
                            character_count=page.character_count or 0,
                            extraction_method="firecrawl_v2_batch"
                        )
                        
                        # Index the document
                        await ms.index_document_with_entities(
                            index_name,
                            page,
                            extracted_content,
                            None  # No entities for now
                        )
                        
                        # Mark as indexed
                        page.indexed = True
        
        db.commit()
        logger.info(f"V2 batch indexing completed: {pages_created} pages indexed")
        
    except Exception as e:
        logger.error(f"Meilisearch indexing failed for V2 batch: {e}")
    
    logger.info(f"V2 batch processing completed: {pages_created} pages created, {pages_failed} failed")
    return pages_created, pages_failed


async def _process_individual_firecrawl(db, scrape_session, domain, cdx_records, task_self, scrape_session_id):
    """
    Process pages using individual Firecrawl calls (fallback mode when V2_BATCH_ONLY is False)
    
    Args:
        db: Database session
        scrape_session: ScrapeSession object
        domain: Domain object
        cdx_records: List of CDX records
        task_self: Celery task instance for state updates
        scrape_session_id: ID of the scrape session
        
    Returns:
        Tuple of (pages_created, pages_failed)
    """
    from app.models.scraping import ScrapePage, ScrapePageStatus
    from app.models.shared_pages import PageV2 as Page
    
    pages_created = 0
    pages_failed = 0
    batch_size = 10  # Process 10 pages in parallel for better performance
    
    # Get ScrapePage records that need processing (PENDING status and no existing final Page)
    pending_scrape_pages = db.execute(
        select(ScrapePage)
        .where(
            ScrapePage.domain_id == domain.id,
            ScrapePage.scrape_session_id == scrape_session_id,
            ScrapePage.status == ScrapePageStatus.PENDING
        )
        .order_by(ScrapePage.id)
    ).scalars().all()
    
    # Filter out pages that already have PageV2 records
    scrape_pages_to_process = []
    for scrape_page in pending_scrape_pages:
        # Check if PageV2 already exists for this URL and timestamp
        existing_page = db.execute(
            select(PageV2.id)
            .where(
                PageV2.url == scrape_page.original_url,
                PageV2.unix_timestamp == int(scrape_page.unix_timestamp)
            )
            .limit(1)
        ).scalars().first()
        
        if not existing_page:
            scrape_pages_to_process.append(scrape_page)
        else:
            # Mark as completed if PageV2 already exists
            scrape_page.status = ScrapePageStatus.COMPLETED
            scrape_page.completed_at = datetime.utcnow()
            scrape_page.page_id = existing_page  # Link to existing PageV2
            logger.debug(f"Final page already exists for: {scrape_page.original_url}")
    
    db.commit()
    logger.info(f"Processing {len(scrape_pages_to_process)} pending ScrapePage records in parallel batches of {batch_size}")
    
    # Early stop check function
    def _should_stop_individual(local_db: Session, session_id: int) -> bool:
        sess = local_db.get(scrape_session.__class__, session_id)
        if not sess:
            return True
        try:
            return sess.status in {scrape_session.status.__class__.CANCELLED, scrape_session.status.__class__.FAILED}
        except Exception:
            return False
    
    # Process in batches for better performance with slow Wayback Machine
    for batch_start in range(0, len(scrape_pages_to_process), batch_size):
        if _should_stop_individual(db, scrape_session_id):
            logger.info(f"Session {scrape_session_id} cancelled; stopping mid-run before batch at offset {batch_start}")
            break
            
        batch_scrape_pages = scrape_pages_to_process[batch_start:batch_start + batch_size]
        
        # Mark ScrapePage records as IN_PROGRESS
        for scrape_page in batch_scrape_pages:
            scrape_page.status = ScrapePageStatus.IN_PROGRESS
            scrape_page.last_attempt_at = datetime.utcnow()
            
            # Broadcast status update
            try:
                from app.services.websocket_service import broadcast_page_progress_sync
                broadcast_page_progress_sync({
                    "scrape_session_id": scrape_session_id,
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
        
        db.commit()
        
        # Create CDX-like records for Firecrawl processing
        batch_records = []
        for scrape_page in batch_scrape_pages:
            # Create a simple object that mimics CDX record structure
            class CDXRecord:
                def __init__(self, scrape_page):
                    self.original_url = scrape_page.original_url
                    self.content_url = scrape_page.content_url
                    self.timestamp = scrape_page.unix_timestamp
                    self.mime_type = scrape_page.mime_type
                    self.status_code = scrape_page.status_code
                    self.content_length_bytes = scrape_page.content_length
                    self.capture_date = scrape_page.first_seen_at
            
            batch_records.append(CDXRecord(scrape_page))
        
        # Update progress
        task_self.update_state(
            state="PROGRESS",
            meta={
                "current": 3,
                "total": 4,
                "status": f"Processing batch {batch_start//batch_size + 1}/{(len(scrape_pages_to_process)-1)//batch_size + 1} ({len(batch_scrape_pages)} pages)...",
                "domain_id": domain.id,
                "pages_processed": pages_created + pages_failed,
                "total_pages": len(scrape_pages_to_process)
            }
        )
        
        # Process batch with individual Firecrawl calls
        batch_results = await _process_batch_with_firecrawl(batch_records)
        
        # Process results and create pages with indexing
        for scrape_page, cdx_record, extracted_content in zip(batch_scrape_pages, batch_records, batch_results):
            try:
                if extracted_content and extracted_content.get('word_count', 0) > 50:
                    # Update ScrapePage with extraction results
                    scrape_page.status = ScrapePageStatus.COMPLETED
                    scrape_page.completed_at = datetime.utcnow()
                    scrape_page.title = extracted_content['title']
                    scrape_page.extracted_text = extracted_content['text']
                    scrape_page.extracted_content = extracted_content.get('text', '')
                    scrape_page.markdown_content = extracted_content.get('markdown', '')
                    scrape_page.extraction_method = extracted_content.get('extraction_method', 'firecrawl')
                    scrape_page.extraction_time = extracted_content.get('extraction_time', 0.0)
                    
                    # Create final Page record with extracted content
                    page = Page(
                        domain_id=domain.id,
                        original_url=scrape_page.original_url,
                        content_url=scrape_page.content_url,
                        title=extracted_content['title'],
                        extracted_text=extracted_content['text'],
                        unix_timestamp=scrape_page.unix_timestamp,
                        mime_type=scrape_page.mime_type,
                        status_code=scrape_page.status_code,
                        meta_description=extracted_content.get('description'),
                        author=extracted_content.get('author'),
                        language=extracted_content.get('language'),
                        word_count=extracted_content['word_count'],
                        character_count=len(extracted_content['text']),
                        content_length=scrape_page.content_length,
                        capture_date=scrape_page.first_seen_at,
                        scraped_at=datetime.utcnow(),
                        processed=True,
                        indexed=False  # Will be set to True after indexing
                    )
                    
                    db.add(page)
                    db.flush()  # Get the page ID
                    
                    pages_created += 1
                    
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
                    # Mark ScrapePage as failed due to insufficient content
                    scrape_page.status = ScrapePageStatus.FAILED
                    scrape_page.error_message = "Extraction failed or returned minimal content"
                    scrape_page.error_type = "insufficient_content"
                    scrape_page.retry_count += 1
                    pages_failed += 1
                    logger.warning(f"Individual intelligent extraction failed or returned minimal content: {scrape_page.original_url}")
                    
            except Exception as e:
                # Mark ScrapePage as failed due to exception
                scrape_page.status = ScrapePageStatus.FAILED
                scrape_page.error_message = str(e)
                scrape_page.error_type = "extraction_exception"
                scrape_page.retry_count += 1
                pages_failed += 1
                logger.error(f"Failed to create page for {scrape_page.original_url}: {str(e)}")
        
        # Commit pages to database first
        db.commit()
        
        # Index pages to Meilisearch
        try:
            # Get project index name
            index_name = f"project_{domain.project_id}"
            
            async with meilisearch_service as ms:
                for cdx_record, extracted_content in zip(batch_records, batch_results):
                    if extracted_content and extracted_content.get('word_count', 0) > 50:
                        # Find the corresponding page
                        page = db.execute(
                            select(Page)
                            .where(
                                Page.domain_id == domain.id,
                                Page.original_url == cdx_record.original_url,
                                Page.unix_timestamp == str(cdx_record.timestamp)
                            )
                            .order_by(Page.id.asc())
                            .limit(1)
                        ).scalars().first()
                        
                        if page:
                            # Convert to ExtractedContent object
                            extracted_content_obj = ExtractedContent(
                                title=extracted_content['title'],
                                text=extracted_content['text'],
                                markdown=extracted_content['markdown'],
                                html="",
                                meta_description=extracted_content.get('description'),
                                author=extracted_content.get('author'),
                                language=extracted_content.get('language'),
                                source_url=extracted_content.get('source_url'),
                                status_code=extracted_content.get('status_code'),
                                error=extracted_content.get('error'),
                                word_count=extracted_content['word_count'],
                                character_count=len(extracted_content['text']),
                                extraction_method=extracted_content.get('extraction_method', 'firecrawl'),
                                extraction_time=extracted_content.get('extraction_time', 0.0)
                            )
                            
                            # Index with extracted content
                            await ms.index_document_with_entities(
                                index_name, 
                                page, 
                                extracted_content_obj, 
                                None  # No entities for now
                            )
                            
                            # Mark as indexed
                            page.indexed = True
                            
            # Commit indexing status
            db.commit()
            
        except Exception as e:
            logger.error(f"Meilisearch indexing failed for individual batch: {e}")
            
        logger.info(f"Individual batch completed: {pages_created} total pages created, {pages_failed} failed")
        
        # Brief pause between batches to avoid overwhelming services
        import time
        time.sleep(2)
    
    logger.info(f"Individual processing completed: {pages_created} pages created, {pages_failed} failed")
    return pages_created, pages_failed


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
                raise ValueError(f"Domain {domain_id} not found")
            
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
                            Domain.incremental_enabled is True,
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
                    stmt = select(Domain).where(Domain.incremental_enabled is True)
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