"""
Celery tasks for Wayback Machine scraping workflow
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set

from celery import chain, group
from celery.exceptions import Retry
from sqlalchemy.orm import Session

from ..celery_app import celery_app
from ..database import get_db
from ..models import (
    Project, Domain, Page, ScrapeSession, ScrapePage, 
    CDXResumeState, ScrapeMonitoringLog, PageErrorLog,
    ScrapeSessionStatus, DomainStatus, ScrapePageStatus, CDXResumeStatus
)
from ..services.wayback_machine import CDXRecord
from ..services.parallel_cdx_fetcher import fetch_cdx_records_parallel
from ..services.content_extractor import extract_content_from_record, ContentExtractionException
from ..services.hybrid_content_extractor import extract_content_hybrid
from ..services.meilisearch_service import index_page, create_project_index
from ..core.config import settings

logger = logging.getLogger(__name__)


# Task configuration with robust settings
SCRAPING_TASK_CONFIG = {
    'bind': True,
    'task_acks_late': True,  # Acknowledge task only after completion
    'task_reject_on_worker_lost': True,  # Reject tasks if worker dies
    'task_time_limit': 7200,  # 2 hours hard limit
    'task_soft_time_limit': 6600,  # 1h 50m soft limit with graceful shutdown
    'autoretry_for': (ConnectionError, TimeoutError, Retry),
    'retry_kwargs': {'max_retries': 3, 'countdown': 60},
    'retry_backoff': True,
    'retry_backoff_max': 600,  # 10 minutes max backoff
    'retry_jitter': True
}


@celery_app.task(**SCRAPING_TASK_CONFIG, name="scraping_tasks.start_domain_scrape")
def start_domain_scrape(domain_id: int, scrape_session_id: Optional[int] = None) -> bool:
    """
    Start scraping a domain with comprehensive workflow
    
    Args:
        domain_id: Domain to scrape
        scrape_session_id: Optional scrape session for tracking
        
    Returns:
        True if workflow started successfully
    """
    logger.info(f"Starting domain scrape for domain_id={domain_id}, session_id={scrape_session_id}")
    
    try:
        # Create workflow chain
        workflow = chain(
            update_domain_status.si(domain_id, DomainStatus.ACTIVE),
            fetch_cdx_records_task.si(domain_id, scrape_session_id),
            process_cdx_records.s(domain_id, scrape_session_id),
            finalize_domain_scrape.s(domain_id, scrape_session_id)
        )
        
        # Execute workflow asynchronously
        workflow.apply_async()
        
        logger.info(f"Domain scrape workflow started for domain_id={domain_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to start domain scrape for domain_id={domain_id}: {str(e)}")
        
        # Update domain status to error
        with next(get_db()) as db:
            domain = db.query(Domain).filter(Domain.id == domain_id).first()
            if domain:
                domain.status = DomainStatus.ERROR
                db.commit()
        
        raise


@celery_app.task(**SCRAPING_TASK_CONFIG, name="scraping_tasks.fetch_cdx_records_task")
def fetch_cdx_records_task(domain_id: int, scrape_session_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetch CDX records for a domain using parallel fetching
    
    Args:
        domain_id: Domain to fetch records for
        scrape_session_id: Optional scrape session for tracking
        
    Returns:
        List of CDX record dictionaries for next task
    """
    logger.info(f"Fetching CDX records for domain_id={domain_id}")
    
    with next(get_db()) as db:
        domain = db.query(Domain).filter(Domain.id == domain_id).first()
        if not domain:
            raise ValueError(f"Domain {domain_id} not found")
        
        # Prepare date range
        from_date = domain.from_date.strftime("%Y%m%d") if domain.from_date else "19900101"
        to_date = domain.to_date.strftime("%Y%m%d") if domain.to_date else datetime.now().strftime("%Y%m%d")
        
        # Check for existing digests to avoid duplicates
        existing_digests: Set[str] = set()
        existing_pages = db.query(ScrapePage.digest_hash).filter(
            ScrapePage.domain_id == domain_id,
            ScrapePage.digest_hash.isnot(None)
        ).all()
        existing_digests.update(page.digest_hash for page in existing_pages if page.digest_hash)
        
        # Create or update CDX resume state
        resume_state = get_or_create_cdx_resume_state(db, domain, scrape_session_id)
        
        try:
            # Run async CDX fetching in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            records, stats = loop.run_until_complete(
                fetch_cdx_records_parallel(
                    domain_name=domain.domain_name,
                    from_date=from_date,
                    to_date=to_date,
                    match_type=domain.match_type.value,
                    url_path=domain.url_path,
                    min_size=domain.min_page_size,
                    max_pages=domain.max_pages,
                    existing_digests=existing_digests,
                    resume_from_page=resume_state.current_page if resume_state.can_resume() else 0
                )
            )
            
            loop.close()
            
            # Update domain statistics
            domain.total_pages = stats.get("total_pages", 0)
            domain.list_pages_filtered = stats.get("list_filtered", 0)
            domain.duplicate_pages = stats.get("duplicate_filtered", 0)
            
            # Update CDX resume state
            resume_state.total_pages = stats.get("total_pages", 0)
            resume_state.total_results_found = stats.get("total_records", 0)
            resume_state.estimated_total_results = stats.get("filtered_records", 0)
            resume_state.mark_completed()
            
            db.commit()
            
            # Convert CDX records to dictionaries for serialization
            record_dicts = []
            for record in records:
                record_dicts.append({
                    'timestamp': record.timestamp,
                    'original_url': record.original_url,
                    'mime_type': record.mime_type,
                    'status_code': record.status_code,
                    'digest': record.digest,
                    'length': record.length,
                    'wayback_url': record.wayback_url,
                    'content_url': record.content_url
                })
            
            logger.info(f"Fetched {len(record_dicts)} CDX records for domain_id={domain_id}")
            return record_dicts
            
        except Exception as e:
            logger.error(f"CDX record fetching failed for domain_id={domain_id}: {str(e)}")
            
            # Mark resume state as failed
            resume_state.mark_failed(str(e))
            domain.status = DomainStatus.ERROR
            db.commit()
            
            raise


@celery_app.task(**SCRAPING_TASK_CONFIG, name="scraping_tasks.process_cdx_records")
def process_cdx_records(cdx_records: List[Dict[str, Any]], domain_id: int, 
                       scrape_session_id: Optional[int] = None) -> Dict[str, int]:
    """
    Process CDX records by creating scrape page entries and starting content extraction
    
    Args:
        cdx_records: List of CDX record dictionaries
        domain_id: Domain ID
        scrape_session_id: Optional scrape session for tracking
        
    Returns:
        Processing statistics
    """
    logger.info(f"Processing {len(cdx_records)} CDX records for domain_id={domain_id}")
    
    if not cdx_records:
        logger.warning(f"No CDX records to process for domain_id={domain_id}")
        return {"total": 0, "created": 0, "skipped": 0}
    
    stats = {"total": len(cdx_records), "created": 0, "skipped": 0}
    
    with next(get_db()) as db:
        domain = db.query(Domain).filter(Domain.id == domain_id).first()
        if not domain:
            raise ValueError(f"Domain {domain_id} not found")
        
        # Create ScrapePage entries
        scrape_pages = []
        extraction_tasks = []
        
        for record_dict in cdx_records:
            # Check if page already exists
            existing_page = db.query(ScrapePage).filter(
                ScrapePage.domain_id == domain_id,
                ScrapePage.digest_hash == record_dict['digest']
            ).first()
            
            if existing_page:
                stats["skipped"] += 1
                logger.debug(f"Skipping existing page: {record_dict['original_url']}")
                continue
            
            # Create new ScrapePage
            scrape_page = ScrapePage(
                domain_id=domain_id,
                scrape_session_id=scrape_session_id,
                original_url=record_dict['original_url'],
                wayback_url=record_dict['wayback_url'],
                unix_timestamp=record_dict['timestamp'],
                mime_type=record_dict['mime_type'],
                status_code=int(record_dict['status_code']),
                content_length=int(record_dict['length']) if record_dict['length'].isdigit() else None,
                digest_hash=record_dict['digest'],
                status=ScrapePageStatus.PENDING,
                is_pdf=record_dict['mime_type'] == 'application/pdf'
            )
            
            db.add(scrape_page)
            scrape_pages.append(scrape_page)
            stats["created"] += 1
        
        # Commit ScrapePage entries first
        db.commit()
        
        # Create content extraction tasks
        for scrape_page in scrape_pages:
            # Refresh to get the ID
            db.refresh(scrape_page)
            extraction_tasks.append(
                extract_and_index_page.s(scrape_page.id, domain.project_id)
            )
        
        # Update domain statistics
        domain.pending_pages += stats["created"]
        db.commit()
    
    # Execute content extraction tasks in parallel (with limits)
    if extraction_tasks:
        logger.info(f"Starting {len(extraction_tasks)} content extraction tasks")
        
        # Process in batches to avoid overwhelming the system
        batch_size = min(50, len(extraction_tasks))
        for i in range(0, len(extraction_tasks), batch_size):
            batch = extraction_tasks[i:i + batch_size]
            group(*batch).apply_async()
    
    logger.info(f"CDX processing complete for domain_id={domain_id}: {stats}")
    return stats


@celery_app.task(**SCRAPING_TASK_CONFIG, name="scraping_tasks.extract_and_index_page")
def extract_and_index_page(scrape_page_id: int, project_id: int) -> bool:
    """
    Extract content from a single page and index it
    
    Args:
        scrape_page_id: ScrapePage ID to process
        project_id: Project ID for indexing
        
    Returns:
        True if successful
    """
    start_time = datetime.utcnow()
    
    with next(get_db()) as db:
        scrape_page = db.query(ScrapePage).filter(ScrapePage.id == scrape_page_id).first()
        if not scrape_page:
            logger.error(f"ScrapePage {scrape_page_id} not found")
            return False
        
        # Update status to in_progress
        scrape_page.status = ScrapePageStatus.IN_PROGRESS
        scrape_page.last_attempt_at = start_time
        db.commit()
        
        try:
            # Create CDX record object for extraction
            cdx_record = CDXRecord(
                timestamp=scrape_page.unix_timestamp,
                original_url=scrape_page.original_url,
                mime_type=scrape_page.mime_type,
                status_code=str(scrape_page.status_code),
                digest=scrape_page.digest_hash,
                length=str(scrape_page.content_length or 0)
            )
            
            # Extract content asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            extracted_content = loop.run_until_complete(
                extract_content_hybrid(cdx_record)
            )
            
            loop.close()
            
            # Update ScrapePage with extracted content
            scrape_page.title = extracted_content.title
            scrape_page.extracted_text = extracted_content.text
            scrape_page.extracted_content = extracted_content.markdown
            scrape_page.markdown_content = extracted_content.markdown
            scrape_page.extraction_method = extracted_content.extraction_method
            scrape_page.extraction_time = extracted_content.extraction_time
            scrape_page.total_processing_time = (datetime.utcnow() - start_time).total_seconds()
            scrape_page.completed_at = datetime.utcnow()
            scrape_page.status = ScrapePageStatus.COMPLETED
            
            # Create corresponding Page entry for the main application
            page = Page(
                domain_id=scrape_page.domain_id,
                original_url=scrape_page.original_url,
                wayback_url=scrape_page.wayback_url,
                title=extracted_content.title,
                content=extracted_content.text,
                extracted_text=extracted_content.text,
                extracted_content=extracted_content.markdown,
                unix_timestamp=int(scrape_page.unix_timestamp),
                mime_type=scrape_page.mime_type,
                status_code=scrape_page.status_code,
                meta_description=extracted_content.meta_description,
                author=extracted_content.author,
                published_date=extracted_content.published_date,
                language=extracted_content.language,
                word_count=extracted_content.word_count,
                character_count=extracted_content.character_count,
                content_length=scrape_page.content_length,
                capture_date=cdx_record.capture_date,
                scraped_at=datetime.utcnow(),
                processed=True
            )
            
            db.add(page)
            db.commit()
            
            # Index in Meilisearch if project has an index
            try:
                project = db.query(Project).filter(Project.id == project_id).first()
                if project and project.index_name:
                    # Refresh page to get ID
                    db.refresh(page)
                    
                    # Index asynchronously
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    loop.run_until_complete(
                        index_page(project.index_name, page, extracted_content)
                    )
                    
                    loop.close()
                    
                    page.indexed = True
                    db.commit()
                    
                    logger.debug(f"Indexed page {page.id} in project index {project.index_name}")
                    
            except Exception as e:
                logger.error(f"Failed to index page {scrape_page_id}: {str(e)}")
                # Don't fail the entire task for indexing errors
            
            # Update domain statistics
            domain = db.query(Domain).filter(Domain.id == scrape_page.domain_id).first()
            if domain:
                domain.scraped_pages += 1
                domain.pending_pages = max(0, domain.pending_pages - 1)
                domain.last_scraped = datetime.utcnow()
                db.commit()
            
            logger.debug(f"Successfully processed page {scrape_page_id}")
            return True
            
        except ContentExtractionException as e:
            # Content extraction specific error
            error_msg = f"Content extraction failed: {str(e)}"
            logger.warning(f"Page {scrape_page_id}: {error_msg}")
            
            scrape_page.status = ScrapePageStatus.FAILED
            scrape_page.error_message = error_msg
            scrape_page.error_type = "content_extraction"
            
            # Log the error for analysis
            error_log = PageErrorLog(
                scrape_page_id=scrape_page_id,
                scrape_session_id=scrape_page.scrape_session_id,
                error_type="content_extraction",
                error_message=error_msg,
                wayback_url=scrape_page.wayback_url,
                original_url=scrape_page.original_url,
                is_recoverable=True,
                suggested_retry_delay=300  # 5 minutes
            )
            db.add(error_log)
            
            # Update domain statistics
            domain = db.query(Domain).filter(Domain.id == scrape_page.domain_id).first()
            if domain:
                domain.failed_pages += 1
                domain.pending_pages = max(0, domain.pending_pages - 1)
                db.commit()
            
            db.commit()
            
            # Schedule retry if under retry limit
            if scrape_page.retry_count < scrape_page.max_retries:
                retry_delay = min(300 * (scrape_page.retry_count + 1), 1800)  # Max 30 minutes
                logger.info(f"Scheduling retry for page {scrape_page_id} in {retry_delay}s")
                
                extract_and_index_page.apply_async(
                    args=[scrape_page_id, project_id],
                    countdown=retry_delay
                )
                
                scrape_page.retry_count += 1
                scrape_page.status = ScrapePageStatus.RETRY
                db.commit()
            
            return False
            
        except Exception as e:
            # Unexpected error
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Page {scrape_page_id}: {error_msg}")
            
            scrape_page.status = ScrapePageStatus.FAILED
            scrape_page.error_message = error_msg
            scrape_page.error_type = "unexpected"
            
            # Log the error
            error_log = PageErrorLog(
                scrape_page_id=scrape_page_id,
                scrape_session_id=scrape_page.scrape_session_id,
                error_type="unexpected",
                error_message=error_msg,
                wayback_url=scrape_page.wayback_url,
                original_url=scrape_page.original_url,
                is_recoverable=False
            )
            db.add(error_log)
            
            # Update domain statistics
            domain = db.query(Domain).filter(Domain.id == scrape_page.domain_id).first()
            if domain:
                domain.failed_pages += 1
                domain.pending_pages = max(0, domain.pending_pages - 1)
                db.commit()
            
            db.commit()
            return False


@celery_app.task(**SCRAPING_TASK_CONFIG, name="scraping_tasks.update_domain_status")
def update_domain_status(domain_id: int, status: DomainStatus) -> bool:
    """Update domain status"""
    with next(get_db()) as db:
        domain = db.query(Domain).filter(Domain.id == domain_id).first()
        if domain:
            domain.status = status
            db.commit()
            logger.info(f"Updated domain {domain_id} status to {status.value}")
            return True
    return False


@celery_app.task(**SCRAPING_TASK_CONFIG, name="scraping_tasks.finalize_domain_scrape")
def finalize_domain_scrape(processing_stats: Dict[str, int], domain_id: int, 
                          scrape_session_id: Optional[int] = None) -> bool:
    """Finalize domain scraping process"""
    logger.info(f"Finalizing domain scrape for domain_id={domain_id}: {processing_stats}")
    
    with next(get_db()) as db:
        domain = db.query(Domain).filter(Domain.id == domain_id).first()
        if not domain:
            return False
        
        # Update domain status to completed
        domain.status = DomainStatus.COMPLETED
        domain.estimated_completion = datetime.utcnow()
        
        # Calculate success rate
        total_attempted = domain.scraped_pages + domain.failed_pages
        if total_attempted > 0:
            domain.success_rate = (domain.scraped_pages / total_attempted) * 100
        
        db.commit()
        
        # Update scrape session if provided
        if scrape_session_id:
            scrape_session = db.query(ScrapeSession).filter(ScrapeSession.id == scrape_session_id).first()
            if scrape_session:
                scrape_session.completed_urls += processing_stats.get("created", 0)
                
                # Check if all domains are complete
                project_domains = db.query(Domain).filter(
                    Domain.project_id == scrape_session.project_id,
                    Domain.active == True
                ).all()
                
                all_complete = all(d.status == DomainStatus.COMPLETED for d in project_domains)
                if all_complete:
                    scrape_session.status = ScrapeSessionStatus.COMPLETED
                    scrape_session.completed_at = datetime.utcnow()
                
                db.commit()
    
    logger.info(f"Domain scrape finalized for domain_id={domain_id}")
    return True


def get_or_create_cdx_resume_state(db: Session, domain: Domain, 
                                  scrape_session_id: Optional[int]) -> CDXResumeState:
    """Get existing or create new CDX resume state"""
    from_date = domain.from_date.strftime("%Y%m%d") if domain.from_date else "19900101"
    to_date = domain.to_date.strftime("%Y%m%d") if domain.to_date else datetime.now().strftime("%Y%m%d")
    
    # Try to find existing resume state
    resume_state = db.query(CDXResumeState).filter(
        CDXResumeState.domain_id == domain.id,
        CDXResumeState.scrape_session_id == scrape_session_id,
        CDXResumeState.from_date == from_date,
        CDXResumeState.to_date == to_date,
        CDXResumeState.match_type == domain.match_type.value,
        CDXResumeState.url_path == (domain.url_path or ""),
        CDXResumeState.status.in_([CDXResumeStatus.ACTIVE, CDXResumeStatus.FAILED])
    ).first()
    
    if resume_state:
        logger.info(f"Found existing CDX resume state for domain {domain.id}: page {resume_state.current_page}")
        return resume_state
    
    # Create new resume state
    resume_state = CDXResumeState(
        domain_id=domain.id,
        scrape_session_id=scrape_session_id,
        domain_name=domain.domain_name,
        from_date=from_date,
        to_date=to_date,
        match_type=domain.match_type.value,
        url_path=domain.url_path or "",
        min_size=domain.min_page_size,
        page_size=domain.page_size,
        max_pages=domain.max_pages,
        status=CDXResumeStatus.ACTIVE
    )
    
    db.add(resume_state)
    db.commit()
    
    logger.info(f"Created new CDX resume state for domain {domain.id}")
    return resume_state


# Convenience functions for starting scrapes
@celery_app.task(name="scraping_tasks.start_project_scrape")
def start_project_scrape(project_id: int) -> Dict[str, Any]:
    """Start scraping all domains in a project"""
    logger.info(f"Starting project scrape for project_id={project_id}")
    
    with next(get_db()) as db:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Create scrape session
        scrape_session = ScrapeSession(
            project_id=project_id,
            status=ScrapeSessionStatus.RUNNING,
            started_at=datetime.utcnow()
        )
        db.add(scrape_session)
        db.commit()
        db.refresh(scrape_session)
        
        # Get active domains
        domains = db.query(Domain).filter(
            Domain.project_id == project_id,
            Domain.active == True
        ).all()
        
        if not domains:
            scrape_session.status = ScrapeSessionStatus.COMPLETED
            scrape_session.completed_at = datetime.utcnow()
            db.commit()
            logger.warning(f"No active domains found for project {project_id}")
            return {"scrape_session_id": scrape_session.id, "domains_started": 0}
        
        # Start domain scraping tasks
        domain_tasks = []
        for domain in domains:
            task = start_domain_scrape.s(domain.id, scrape_session.id)
            domain_tasks.append(task)
        
        # Execute domain tasks in parallel
        group(*domain_tasks).apply_async()
        
        scrape_session.total_urls = sum(d.total_pages for d in domains if d.total_pages)
        db.commit()
        
        logger.info(f"Started scraping {len(domains)} domains for project {project_id}")
        return {"scrape_session_id": scrape_session.id, "domains_started": len(domains)}


# Monitoring and cleanup tasks
@celery_app.task(name="scraping_tasks.cleanup_old_scrape_data")
def cleanup_old_scrape_data(days_old: int = 30) -> Dict[str, int]:
    """Clean up old scrape data"""
    cutoff_date = datetime.utcnow() - timedelta(days=days_old)
    
    with next(get_db()) as db:
        # Clean up old error logs
        deleted_errors = db.query(PageErrorLog).filter(
            PageErrorLog.occurred_at < cutoff_date,
            PageErrorLog.resolved_at.isnot(None)
        ).count()
        
        db.query(PageErrorLog).filter(
            PageErrorLog.occurred_at < cutoff_date,
            PageErrorLog.resolved_at.isnot(None)
        ).delete()
        
        # Clean up completed CDX resume states
        deleted_resume = db.query(CDXResumeState).filter(
            CDXResumeState.completed_at < cutoff_date,
            CDXResumeState.status == CDXResumeStatus.COMPLETED
        ).count()
        
        db.query(CDXResumeState).filter(
            CDXResumeState.completed_at < cutoff_date,
            CDXResumeState.status == CDXResumeStatus.COMPLETED
        ).delete()
        
        db.commit()
        
        logger.info(f"Cleaned up {deleted_errors} error logs and {deleted_resume} resume states older than {days_old} days")
        return {"deleted_errors": deleted_errors, "deleted_resume_states": deleted_resume}