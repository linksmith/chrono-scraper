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
from app.services.firecrawl_extractor import get_firecrawl_extractor
from app.services.firecrawl_v2_client import FirecrawlV2Client
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
        
        # Optionally create a Firecrawl v2 batch to enable grouped cancellation
        try:
            if getattr(settings, "FIRECRAWL_V2_BATCH_ENABLED", True) and not getattr(scrape_session, "external_batch_id", None):
                batch_urls = [r.wayback_url for r in cdx_records]
                if batch_urls:
                    timeout_ms = (getattr(settings, "WAYBACK_MACHINE_TIMEOUT", 180) or 180) * 1000
                    fc = FirecrawlV2Client()
                    batch_id = fc.start_batch(batch_urls, formats=["markdown", "html"], timeout_ms=timeout_ms)
                    if batch_id:
                        scrape_session.external_batch_id = batch_id
                        scrape_session.external_batch_provider = "firecrawl_v2"
                        db.commit()
        except Exception as e:
            logger.warning(f"Failed to start Firecrawl batch for session {scrape_session_id}: {e}")

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
        
        # Process pages with Firecrawl in parallel batches
        pages_created = 0
        pages_failed = 0
        batch_size = 10  # Process 10 pages in parallel for better performance
        
        # Filter out existing pages first
        new_records = []
        for cdx_record in cdx_records:
            # Check existence by URL + timestamp to avoid duplicates and MultipleResultsFound
            existing_page = db.execute(
                select(Page.id)
                .where(
                    Page.domain_id == domain.id,
                    Page.original_url == cdx_record.original_url,
                    Page.unix_timestamp == str(cdx_record.timestamp)
                )
                .order_by(Page.id.asc())
                .limit(1)
            ).scalars().first()
            
            if not existing_page:
                new_records.append(cdx_record)
            else:
                logger.debug(f"Page already exists: {cdx_record.original_url}")
        
        logger.info(f"Processing {len(new_records)} new pages in parallel batches of {batch_size}")
        
        # Process in batches for better performance with slow Wayback Machine
        was_cancelled_midway = False
        for batch_start in range(0, len(new_records), batch_size):
            if _should_stop(db, scrape_session_id):
                was_cancelled_midway = True
                logger.info(f"Session {scrape_session_id} cancelled; stopping mid-run before batch at offset {batch_start}")
                break
            batch_records = new_records[batch_start:batch_start + batch_size]
            
            # Update progress
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": 3,
                    "total": 4,
                    "status": f"Processing batch {batch_start//batch_size + 1}/{(len(new_records)-1)//batch_size + 1} ({len(batch_records)} pages)...",
                    "domain_id": domain_id,
                    "pages_processed": pages_created + pages_failed,
                    "total_pages": len(new_records)
                }
            )
            
            # Process batch in parallel
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                batch_results = loop.run_until_complete(
                    _process_batch_with_firecrawl(batch_records)
                )
            finally:
                loop.close()
            
            # Process results and create pages with indexing
            for cdx_record, extracted_content in zip(batch_records, batch_results):
                try:
                    if extracted_content and extracted_content.get('word_count', 0) > 50:
                        # Create page with extracted content
                        page = Page(
                            domain_id=domain.id,
                            original_url=cdx_record.original_url,
                            wayback_url=cdx_record.wayback_url,
                            title=extracted_content['title'],
                            extracted_text=extracted_content['text'],
                            unix_timestamp=str(cdx_record.timestamp),
                            mime_type=cdx_record.mime_type,
                            status_code=int(cdx_record.status_code),
                            meta_description=extracted_content.get('description'),
                            author=extracted_content.get('author'),
                            language=extracted_content.get('language'),
                            word_count=extracted_content['word_count'],
                            character_count=len(extracted_content['text']),
                            content_length=cdx_record.content_length_bytes,
                            capture_date=cdx_record.capture_date,
                            scraped_at=datetime.utcnow(),
                            processed=True,
                            indexed=False  # Will be set to True after indexing
                        )
                        
                        db.add(page)
                        db.flush()  # Get the page ID
                        
                        # Convert extracted_content dict back to ExtractedContent object
                        extracted_content_obj = ExtractedContent(
                            title=extracted_content['title'],
                            text=extracted_content['text'],
                            markdown=extracted_content['markdown'],
                            html="",  # Not available from the dict
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
                        
                        pages_created += 1
                    else:
                        pages_failed += 1
                        logger.warning(f"Firecrawl extraction failed or returned minimal content: {cdx_record.original_url}")
                        
                except Exception as e:
                    pages_failed += 1
                    logger.error(f"Failed to create page for {cdx_record.original_url}: {str(e)}")
            
            # Commit pages to database first
            db.commit()
            
            # Index pages to Meilisearch
            loop_for_indexing = asyncio.new_event_loop()
            asyncio.set_event_loop(loop_for_indexing)
            
            try:
                # Get project index name
                index_name = f"project_{domain.project_id}"
                
                async def index_batch():
                    async with meilisearch_service as ms:
                        for cdx_record, extracted_content in zip(batch_records, batch_results):
                            if extracted_content and extracted_content.get('word_count', 0) > 50:
                                # Find the corresponding page (limit to one to avoid MultipleResultsFound)
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
                                    # Broadcast page completion
                                    try:
                                        from app.services.websocket_service import broadcast_page_progress_sync
                                        from app.models.scraping import ScrapePageStatus
                                        broadcast_page_progress_sync({
                                            "scrape_session_id": scrape_session_id,
                                            "scrape_page_id": page.id,
                                            "domain_id": domain.id,
                                            "domain_name": domain.domain_name,
                                            "page_url": page.original_url,
                                            "wayback_url": page.wayback_url or "",
                                            "status": ScrapePageStatus.COMPLETED,
                                            "processing_stage": "completed",
                                            "stage_progress": 1.0,
                                        })
                                    except Exception:
                                        pass
                                    
                    # Commit indexing status
                    db.commit()
                
                loop_for_indexing.run_until_complete(index_batch())
                logger.info(f"Batch indexed: {pages_created} pages indexed to Meilisearch")
                
            except Exception as e:
                logger.error(f"Meilisearch indexing failed for batch: {e}")
            finally:
                loop_for_indexing.close()
                
            logger.info(f"Batch completed: {pages_created} total pages created, {pages_failed} failed")
            
            # Brief pause between batches to avoid overwhelming services
            import time
            time.sleep(2)
        
        # Step 3: Update statistics
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
        
        if was_cancelled_midway:
            scrape_session.status = ScrapeSessionStatus.CANCELLED
            scrape_session.completed_at = datetime.utcnow()
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
    
    # Fetch CDX records with intelligent filtering
    async with CDXAPIClient() as cdx_client:
        raw_records, raw_stats = await cdx_client.fetch_cdx_records(
            domain_name=domain.domain_name,
            from_date=from_date,
            to_date=to_date,
            match_type=getattr(domain.match_type, 'value', 'domain'),
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