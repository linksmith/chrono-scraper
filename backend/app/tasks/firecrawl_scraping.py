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
        
        logger.info(f"Starting Firecrawl scraping for domain: {domain.domain_name}")
        
        # Update domain status
        domain.status = DomainStatus.ACTIVE
        scrape_session.status = ScrapeSessionStatus.RUNNING
        scrape_session.started_at = datetime.utcnow()
        db.commit()
        
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
                _discover_and_filter_pages(domain)
            )
        finally:
            loop.close()
        
        logger.info(f"CDX discovery completed: {len(cdx_records)} records after filtering")
        
        # Update session stats
        scrape_session.total_urls = len(cdx_records)
        db.commit()
        
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
            existing_page = db.execute(
                select(Page).where(Page.original_url == cdx_record.original_url)
            ).scalar_one_or_none()
            
            if not existing_page:
                new_records.append(cdx_record)
            else:
                logger.debug(f"Page already exists: {cdx_record.original_url}")
        
        logger.info(f"Processing {len(new_records)} new pages in parallel batches of {batch_size}")
        
        # Process in batches for better performance with slow Wayback Machine
        for batch_start in range(0, len(new_records), batch_size):
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
            
            # Process results and create pages
            for cdx_record, extracted_content in zip(batch_records, batch_results):
                try:
                    if extracted_content and extracted_content.get('word_count', 0) > 50:
                        # Create page with extracted content
                        page = Page(
                            domain_id=domain.id,
                            original_url=cdx_record.original_url,
                            wayback_url=cdx_record.wayback_url,
                            title=extracted_content['title'],
                            content=extracted_content['text'],
                            extracted_text=extracted_content['text'],
                            extracted_content=extracted_content['markdown'],
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
                            indexed=False
                        )
                        
                        db.add(page)
                        pages_created += 1
                    else:
                        pages_failed += 1
                        logger.warning(f"Firecrawl extraction failed or returned minimal content: {cdx_record.original_url}")
                        
                except Exception as e:
                    pages_failed += 1
                    logger.error(f"Failed to create page for {cdx_record.original_url}: {str(e)}")
            
            # Commit after each batch
            db.commit()
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
        
        scrape_session.completed_urls = pages_created
        scrape_session.failed_urls = pages_failed
        scrape_session.status = ScrapeSessionStatus.COMPLETED
        scrape_session.completed_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Firecrawl scraping completed: {pages_created} pages created, {pages_failed} failed")
        
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
        
        # Update task state
        self.update_state(
            state="FAILURE",
            meta={
                "error": error_msg,
                "status": "failed",
                "domain_id": domain_id
            }
        )
        
        raise
        
    finally:
        if db:
            db.close()


async def _discover_and_filter_pages(domain: Domain) -> tuple[List, Dict[str, Any]]:
    """
    Discover pages using CDX API with intelligent filtering
    
    Args:
        domain: Domain object to scrape
        
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
            filter_list_pages=True
        )
    
    # Apply intelligent filtering
    filtered_records, filter_stats = intelligent_filter.filter_records_intelligent(
        raw_records, existing_digests, prioritize_changes=True
    )
    
    # Sort by priority (high-value content first)
    filtered_records.sort(
        key=lambda r: intelligent_filter.get_scraping_priority(r), 
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
                        'word_count': extracted_content.word_count,
                        'extraction_method': extracted_content.extraction_method
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