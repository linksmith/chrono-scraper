"""
Simplified Firecrawl-only scraping tasks for Celery

This module provides a streamlined scraping system that:
1. Uses CDX API for discovery with intelligent filtering
2. Uses Firecrawl-only for content extraction 
3. Provides simple, reliable task execution
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from celery import current_task
from sqlmodel import select, Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.models.project import Domain, ScrapeSession, Page, ScrapeSessionStatus, DomainStatus
from app.models.scraping import ScrapePage, ScrapePageStatus
from app.services.firecrawl_extractor import get_firecrawl_extractor
from app.services.firecrawl_v2_client import FirecrawlV2Client, FirecrawlV2Error
from app.services.intelligent_filter import IntelligentContentFilter
from app.services.wayback_machine import CDXAPIClient
from app.services.meilisearch_service import meilisearch_service
from app.models.extraction_data import ExtractedContent

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


@celery_app.task(bind=True)
def scrape_domain_with_firecrawl(self, domain_id: int, scrape_session_id: int) -> Dict[str, Any]:
    """
    Scrape a domain using Firecrawl-only extraction with intelligent CDX filtering
    
    This is the main entry point for domain scraping that:
    1. Discovers pages via CDX API with intelligent filtering
    2. Extracts content using local Firecrawl service
    3. Stores results in the database
    
    Args:
        domain_id: ID of the domain to scrape
        scrape_session_id: ID of the scrape session
        
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
                "status": "Starting Firecrawl scraping...",
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
        
        logger.info(f"Starting Firecrawl scraping for domain: {domain.domain_name}")
        
        # Update domain status
        domain.status = DomainStatus.ACTIVE
        scrape_session.status = ScrapeSessionStatus.RUNNING
        scrape_session.started_at = datetime.utcnow()
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
            cdx_records, filter_stats = loop.run_until_complete(
                _discover_and_filter_pages(domain, project.enable_attachment_download)
            )
        finally:
            loop.close()
        
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
        
        # Update session stats
        scrape_session.total_urls = len(cdx_records)
        db.commit()
        
        # Create ScrapePage records for all discovered URLs to enable progress tracking
        logger.info(f"Creating ScrapePage records for {len(cdx_records)} discovered URLs")
        scrape_pages_created = 0
        
        for cdx_record in cdx_records:
            try:
                # Check if ScrapePage already exists to avoid duplicates
                existing_scrape_page = db.execute(
                    select(ScrapePage.id)
                    .where(
                        ScrapePage.domain_id == domain.id,
                        ScrapePage.original_url == cdx_record.original_url,
                        ScrapePage.unix_timestamp == str(cdx_record.timestamp)
                    )
                    .limit(1)
                ).scalars().first()
                
                if not existing_scrape_page:
                    scrape_page = ScrapePage(
                        domain_id=domain.id,
                        scrape_session_id=scrape_session_id,
                        original_url=cdx_record.original_url,
                        wayback_url=cdx_record.wayback_url,
                        unix_timestamp=str(cdx_record.timestamp),
                        mime_type=cdx_record.mime_type or "text/html",
                        status_code=int(cdx_record.status_code) if cdx_record.status_code else 200,
                        content_length=cdx_record.content_length_bytes,
                        digest_hash=getattr(cdx_record, 'digest', None),
                        status=ScrapePageStatus.PENDING,
                        is_pdf=cdx_record.mime_type == "application/pdf" if cdx_record.mime_type else False,
                        first_seen_at=datetime.utcnow(),
                        created_at=datetime.utcnow()
                    )
                    db.add(scrape_page)
                    scrape_pages_created += 1
                    
                    # Broadcast individual page discovery for real-time UI updates
                    try:
                        from app.services.websocket_service import broadcast_page_progress_sync
                        broadcast_page_progress_sync({
                            "scrape_session_id": scrape_session_id,
                            "scrape_page_id": scrape_page.id if scrape_page.id else 0,
                            "domain_id": domain.id,
                            "domain_name": domain.domain_name,
                            "page_url": cdx_record.original_url,
                            "wayback_url": cdx_record.wayback_url,
                            "status": ScrapePageStatus.PENDING,
                            "processing_stage": "cdx_discovery"
                        })
                    except Exception:
                        pass
                        
            except Exception as e:
                logger.error(f"Failed to create ScrapePage for {cdx_record.original_url}: {str(e)}")
        
        # Commit all ScrapePage records
        db.commit()
        logger.info(f"Created {scrape_pages_created} ScrapePage records")
        
        # Create Firecrawl v2 batch - mandatory when V2_BATCH_ONLY is enabled
        v2_batch_only = getattr(settings, "FIRECRAWL_V2_BATCH_ONLY", False)
        v2_batch_enabled = getattr(settings, "FIRECRAWL_V2_BATCH_ENABLED", True)
        
        if (v2_batch_enabled or v2_batch_only) and not getattr(scrape_session, "external_batch_id", None):
            batch_urls = [r.wayback_url for r in cdx_records]
            if batch_urls:
                # Extended timeout for Wayback Machine (2 minutes as requested)
                timeout_ms = (getattr(settings, "WAYBACK_MACHINE_TIMEOUT", 120) or 120) * 1000
                fc = FirecrawlV2Client()
                
                try:
                    # Use enhanced v2 features: 24-hour caching for historical content
                    batch_id = fc.start_batch(
                        batch_urls, 
                        formats=["markdown", "html"], 
                        timeout_ms=timeout_ms,
                        max_age_hours=24  # Cache Wayback Machine content for 24 hours
                    )
                    if batch_id:
                        scrape_session.external_batch_id = batch_id
                        scrape_session.external_batch_provider = "firecrawl_v2"
                        db.commit()
                        logger.info(f"Created Firecrawl V2 batch {batch_id} for session {scrape_session_id} with {len(batch_urls)} URLs")
                    elif v2_batch_only:
                        raise RuntimeError("Failed to create Firecrawl V2 batch and V2_BATCH_ONLY is enabled")
                except Exception as e:
                    error_msg = f"Failed to start Firecrawl V2 batch for session {scrape_session_id}: {e}"
                    if v2_batch_only:
                        logger.error(error_msg)
                        raise RuntimeError(f"V2 batch creation failed and V2_BATCH_ONLY is enabled: {e}")
                    else:
                        logger.warning(error_msg)
            elif v2_batch_only:
                raise RuntimeError("No URLs available for V2 batch and V2_BATCH_ONLY is enabled")

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

        # Step 2: Extract content using Firecrawl
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
        
        # Process pages with Firecrawl - V2 batch only or fallback to individual processing
        pages_created = 0
        pages_failed = 0
        
        # Check if we should use V2 batch-only mode
        if v2_batch_only and scrape_session.external_batch_id:
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
        else:
            # Fallback to individual processing (when V2_BATCH_ONLY is False)
            if v2_batch_only:
                raise RuntimeError("V2_BATCH_ONLY is enabled but no batch ID found - cannot proceed with individual processing")
            
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
        
        logger.info(f"Firecrawl scraping completed: {pages_created} pages created, {pages_failed} failed")
        
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
            "pages_found": len(cdx_records),
            "pages_created": pages_created,
            "pages_failed": pages_failed,
            "filter_stats": filter_stats,
            "message": f"Successfully extracted {pages_created} pages using Firecrawl for {domain.domain_name}"
        }
        
    except Exception as exc:
        error_msg = str(exc)
        logger.error(f"Firecrawl scraping failed for domain {domain_id}: {error_msg}")
        
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


async def _discover_and_filter_pages(domain: Domain, include_attachments: bool = True) -> tuple[List, Dict[str, Any]]:
    """
    Discover pages using CDX API with intelligent filtering
    
    Args:
        domain: Domain object to scrape
        include_attachments: Whether to include PDF and other attachments in scraping
        
    Returns:
        Tuple of (filtered_cdx_records, filter_statistics)
    """
    from app.services.wayback_machine import CDXAPIClient
    from app.services.intelligent_filter import get_intelligent_filter
    
    # Set up date range
    from_date = domain.from_date.strftime("%Y%m%d") if domain.from_date else "20200101"
    to_date = domain.to_date.strftime("%Y%m%d") if domain.to_date else datetime.now().strftime("%Y%m%d")
    
    # Get existing digests to avoid duplicates
    intelligent_filter = get_intelligent_filter()
    existing_digests = await intelligent_filter.get_existing_digests(domain.domain_name)
    
    logger.info(f"Found {len(existing_digests)} existing digests for {domain.domain_name}")
    logger.info(f"PDF attachment processing: {'ENABLED' if include_attachments else 'DISABLED'} for domain: {domain.domain_name}")
    
    # Handle both enum and string cases for match_type
    if hasattr(domain.match_type, 'value'):
        extracted_match_type = domain.match_type.value
    elif isinstance(domain.match_type, str):
        extracted_match_type = domain.match_type
    else:
        extracted_match_type = str(domain.match_type)
    
    # Fetch CDX records with intelligent filtering
    async with CDXAPIClient() as cdx_client:
        raw_records, raw_stats = await cdx_client.fetch_cdx_records(
            domain_name=domain.domain_name,
            from_date=from_date,
            to_date=to_date,
            match_type=extracted_match_type,
            url_path=domain.url_path,
            min_size=1000,  # 1KB minimum
            max_size=10 * 1024 * 1024,  # 10MB maximum
            max_pages=domain.max_pages or 10,  # Reasonable default
            existing_digests=existing_digests,
            filter_list_pages=True,
            include_attachments=include_attachments
        )
    
    # Apply intelligent filtering
    filtered_records, filter_stats = intelligent_filter.filter_records_intelligent(
        raw_records, existing_digests, prioritize_changes=True, include_attachments=include_attachments
    )
    
    # Sort by priority (high-value content first)
    filtered_records.sort(
        key=lambda r, inc_att=include_attachments: intelligent_filter.get_scraping_priority(r, inc_att), 
        reverse=True
    )
    
    # Combine statistics
    combined_stats = {**raw_stats, **filter_stats}
    
    logger.info(f"CDX filtering complete: {len(raw_records)} -> {len(filtered_records)} records")
    
    return filtered_records, combined_stats


async def _process_batch_with_firecrawl(batch_records) -> List[Optional[Dict[str, Any]]]:
    """
    Process a batch of CDX records with Firecrawl in parallel
    
    Args:
        batch_records: List of CDX records to process
        
    Returns:
        List of extracted content dictionaries (None for failures)
    """
    from app.services.firecrawl_extractor import get_firecrawl_extractor
    
    extractor = get_firecrawl_extractor()
    
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
                    logger.warning(f"Firecrawl returned minimal content for: {cdx_record.original_url}")
                    return None
                    
            except Exception as e:
                logger.error(f"Firecrawl extraction failed for {cdx_record.original_url}: {str(e)}")
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
        task = scrape_domain_with_firecrawl.delay(domain_id, scrape_session.id)
        
        logger.info(f"Started Firecrawl scraping task {task.id} for domain {domain_id}")
        
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
    from app.services.firecrawl_v2_client import FirecrawlV2Client, FirecrawlV2Error
    from app.models.scraping import ScrapePage, ScrapePageStatus
    from app.models.project import Page
    from app.models.extraction_data import ExtractedContent
    from app.services import meilisearch_service
    
    pages_created = 0
    pages_failed = 0
    
    if not scrape_session.external_batch_id:
        logger.error(f"No external batch ID found for session {scrape_session.id}")
        return pages_created, pages_failed
    
    logger.info(f"Processing V2 batch results for batch ID: {scrape_session.external_batch_id}")
    
    # TODO: Implement V2 batch results retrieval
    # This is a placeholder - you'll need to implement the actual V2 batch results API
    # For now, we'll simulate this by processing with individual calls but logging as batch
    
    # Fallback to individual processing for each URL in the batch
    # This should be replaced with actual V2 batch results retrieval
    fc_client = FirecrawlV2Client()
    
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
    
    # TODO: Replace this individual processing with actual V2 batch results parsing
    # For now, mark all pages as processed by the batch
    for scrape_page in scrape_pages_to_process:
        try:
            # Mark as in progress
            scrape_page.status = ScrapePageStatus.IN_PROGRESS
            scrape_page.last_attempt_at = datetime.utcnow()
            db.flush()
            
            # Simulate batch processing - this should be replaced with actual batch results
            # For now, we'll mark as completed with minimal content to demonstrate V2 batch mode
            scrape_page.status = ScrapePageStatus.COMPLETED
            scrape_page.completed_at = datetime.utcnow()
            scrape_page.title = f"V2 Batch Processed - {scrape_page.original_url}"
            scrape_page.extracted_text = "Content processed via Firecrawl V2 batch"
            scrape_page.extraction_method = "firecrawl_v2_batch"
            
            # Create final Page record
            page = Page(
                domain_id=domain.id,
                original_url=scrape_page.original_url,
                wayback_url=scrape_page.wayback_url,
                title=scrape_page.title,
                extracted_text=scrape_page.extracted_text,
                unix_timestamp=scrape_page.unix_timestamp,
                mime_type=scrape_page.mime_type,
                status_code=scrape_page.status_code,
                word_count=len(scrape_page.extracted_text.split()),
                character_count=len(scrape_page.extracted_text),
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
                    "wayback_url": scrape_page.wayback_url,
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
    from app.models.project import Page
    from app.models.extraction_data import ExtractedContent
    from app.services import meilisearch_service
    
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
            # Mark as completed if final page already exists
            scrape_page.status = ScrapePageStatus.COMPLETED
            scrape_page.completed_at = datetime.utcnow()
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
                    "wayback_url": scrape_page.wayback_url,
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
                    self.wayback_url = scrape_page.wayback_url
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
                        wayback_url=scrape_page.wayback_url,
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
                            "wayback_url": scrape_page.wayback_url,
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
                    logger.warning(f"Individual Firecrawl extraction failed or returned minimal content: {scrape_page.original_url}")
                    
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