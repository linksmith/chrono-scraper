"""
Scraping-related Celery tasks - Phase 4 implementation
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

from celery import current_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.project import Project, Domain, Page, ScrapeSession, DomainStatus, PageStatus
from app.services.wayback_service import wayback_service
from app.services.fetch_service import fetch_service, FetchConfig, ProxyConfig, RateLimitConfig
from app.services.content_extraction import content_extraction_service
from app.services.meilisearch_service import MeilisearchService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.scraping_tasks.start_domain_scrape")
def start_domain_scrape(self, domain_id: int, scrape_session_id: int) -> Dict[str, Any]:
    """
    Start scraping a domain using Wayback Machine
    """
    try:
        async def _start_scrape():
            async with AsyncSessionLocal() as db:
                # Get domain and scrape session
                domain_result = await db.execute(select(Domain).where(Domain.id == domain_id))
                domain = domain_result.scalar_one_or_none()
                
                session_result = await db.execute(select(ScrapeSession).where(ScrapeSession.id == scrape_session_id))
                scrape_session = session_result.scalar_one_or_none()
                
                if not domain:
                    raise Exception(f"Domain {domain_id} not found")
                if not scrape_session:
                    raise Exception(f"Scrape session {scrape_session_id} not found")
                
                # Update domain status
                domain.status = DomainStatus.SCRAPING
                await db.commit()
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 1, "total": 6, "status": "Discovering pages..."}
                )
                
                # Step 1: Discover pages using Wayback Machine
                try:
                    snapshots = await wayback_service.get_domain_snapshots(
                        domain=domain.domain_name,
                        from_date=scrape_session.date_from,
                        to_date=scrape_session.date_to,
                        limit=10000
                    )
                    
                    logger.info(f"Found {len(snapshots)} snapshots for domain {domain.domain_name}")
                    
                except Exception as e:
                    logger.error(f"Error discovering pages for domain {domain_id}: {str(e)}")
                    domain.status = DomainStatus.ERROR
                    await db.commit()
                    raise
                
                current_task.update_state(
                    state="PROGRESS", 
                    meta={"current": 2, "total": 6, "status": f"Found {len(snapshots)} pages, creating records..."}
                )
                
                # Step 2: Create page records
                pages_created = 0
                pages_skipped = 0
                
                for snapshot in snapshots:
                    # Check if page already exists
                    existing_page = await db.execute(
                        select(Page).where(
                            Page.domain_id == domain_id,
                            Page.original_url == snapshot["original_url"],
                            Page.snapshot_timestamp == snapshot["timestamp"]
                        )
                    )
                    
                    if existing_page.scalar_one_or_none():
                        pages_skipped += 1
                        continue
                    
                    # Create new page record
                    page = Page(
                        domain_id=domain_id,
                        original_url=snapshot["original_url"],
                        wayback_url=snapshot["wayback_url"],
                        snapshot_timestamp=snapshot["timestamp"],
                        capture_date=snapshot["capture_date"],
                        status_code=snapshot["status_code"],
                        content_type=snapshot["mime_type"],
                        content_length=snapshot["length"],
                        status=PageStatus.DISCOVERED,
                        scrape_session_id=scrape_session_id
                    )
                    
                    db.add(page)
                    pages_created += 1
                    
                    # Batch commit every 100 pages
                    if pages_created % 100 == 0:
                        await db.commit()
                
                await db.commit()
                
                # Update domain statistics
                domain.total_pages = pages_created + pages_skipped
                domain.scraped_pages = 0
                domain.failed_pages = 0
                await db.commit()
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 3, "total": 6, "status": f"Created {pages_created} page records"}
                )
                
                # Step 3: Queue page scraping tasks
                page_results = await db.execute(
                    select(Page).where(
                        Page.domain_id == domain_id,
                        Page.scrape_session_id == scrape_session_id,
                        Page.status == PageStatus.DISCOVERED
                    )
                )
                pages_to_scrape = page_results.scalars().all()
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 4, "total": 6, "status": f"Queuing {len(pages_to_scrape)} page scraping tasks..."}
                )
                
                # Queue scraping tasks in batches
                batch_size = 50
                queued_tasks = 0
                
                for i in range(0, len(pages_to_scrape), batch_size):
                    batch = pages_to_scrape[i:i + batch_size]
                    page_ids = [page.id for page in batch]
                    
                    # Queue batch scraping task
                    scrape_pages_batch.delay(page_ids, domain_id)
                    queued_tasks += len(page_ids)
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 5, "total": 6, "status": f"Queued {queued_tasks} pages for scraping"}
                )
                
                # Step 4: Update session status
                scrape_session.status = "in_progress"
                scrape_session.pages_discovered = pages_created
                await db.commit()
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 6, "total": 6, "status": "Domain scrape initialization completed"}
                )
                
                return {
                    "domain_id": domain_id,
                    "scrape_session_id": scrape_session_id,
                    "status": "queued",
                    "pages_found": len(snapshots),
                    "pages_created": pages_created,
                    "pages_skipped": pages_skipped,
                    "tasks_queued": queued_tasks
                }
        
        return asyncio.run(_start_scrape())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(bind=True, name="app.tasks.scraping_tasks.scrape_pages_batch")
def scrape_pages_batch(self, page_ids: List[int], domain_id: int) -> Dict[str, Any]:
    """
    Scrape a batch of pages concurrently
    """
    try:
        async def _scrape_batch():
            async with AsyncSessionLocal() as db:
                # Get domain for configuration
                domain_result = await db.execute(select(Domain).where(Domain.id == domain_id))
                domain = domain_result.scalar_one_or_none()
                
                if not domain:
                    raise Exception(f"Domain {domain_id} not found")
                
                # Get pages to scrape
                pages_result = await db.execute(
                    select(Page).where(Page.id.in_(page_ids))
                )
                pages = pages_result.scalars().all()
                
                if not pages:
                    return {"status": "no_pages", "processed": 0}
                
                # Create fetch configuration
                proxy_config = None
                if settings.USE_PROXY and settings.PROXY_URL:
                    proxy_config = ProxyConfig(
                        url=settings.PROXY_URL,
                        username=settings.PROXY_USERNAME,
                        password=settings.PROXY_PASSWORD
                    )
                
                rate_limit_config = RateLimitConfig(
                    requests_per_second=settings.DOMAIN_RATE_LIMIT,
                    burst_size=settings.DEFAULT_BURST_SIZE,
                    delay_between_requests=1.0 / settings.DOMAIN_RATE_LIMIT
                )
                
                fetch_config = FetchConfig(
                    timeout=settings.DEFAULT_REQUEST_TIMEOUT,
                    max_retries=settings.MAX_RETRIES,
                    retry_delay=settings.RETRY_DELAY,
                    user_agent=settings.USER_AGENT,
                    proxy=proxy_config,
                    rate_limit=rate_limit_config
                )
                
                # Scrape pages
                successful = 0
                failed = 0
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 0, "total": len(pages), "status": f"Scraping {len(pages)} pages..."}
                )
                
                for i, page in enumerate(pages):
                    try:
                        # Update page status
                        page.status = PageStatus.SCRAPING
                        await db.commit()
                        
                        # Fetch content from Wayback Machine
                        result = await fetch_service.fetch_url(
                            page.wayback_url,
                            config=fetch_config
                        )
                        
                        if result["success"] and result["text"]:
                            # Extract content
                            extracted = content_extraction_service.extract_content(
                                html=result["text"],
                                url=page.original_url,
                                method="auto"
                            )
                            
                            # Update page with extracted content
                            page.content = result["text"]
                            page.extracted_text = extracted.text_content
                            page.extracted_title = extracted.title
                            page.extracted_content = extracted.main_content
                            page.word_count = extracted.word_count
                            page.character_count = extracted.char_count
                            page.content_hash = extracted.content_hash
                            page.scraped_at = datetime.utcnow()
                            page.status = PageStatus.SCRAPED
                            page.processed = True
                            
                            # Store metadata
                            if extracted.meta_description:
                                page.meta_description = extracted.meta_description
                            if extracted.meta_keywords:
                                page.meta_keywords = extracted.meta_keywords
                            if extracted.author:
                                page.author = extracted.author
                            if extracted.published_date:
                                page.published_date = extracted.published_date
                            if extracted.lang:
                                page.language = extracted.lang
                                
                            successful += 1
                            
                            # Queue content processing task
                            process_page_content.delay(page.id)
                            
                        else:
                            # Mark as failed
                            page.status = PageStatus.FAILED
                            page.error_message = result.get("error", "Unknown error")
                            failed += 1
                        
                        await db.commit()
                        
                        # Update progress
                        current_task.update_state(
                            state="PROGRESS",
                            meta={
                                "current": i + 1,
                                "total": len(pages),
                                "status": f"Scraped {i + 1}/{len(pages)} pages",
                                "successful": successful,
                                "failed": failed
                            }
                        )
                        
                    except Exception as e:
                        logger.error(f"Error scraping page {page.id}: {str(e)}")
                        page.status = PageStatus.FAILED
                        page.error_message = str(e)
                        failed += 1
                        await db.commit()
                
                # Update domain statistics
                domain.scraped_pages = (domain.scraped_pages or 0) + successful
                domain.failed_pages = (domain.failed_pages or 0) + failed
                await db.commit()
                
                return {
                    "domain_id": domain_id,
                    "status": "completed",
                    "total_pages": len(pages),
                    "successful": successful,
                    "failed": failed
                }
        
        return asyncio.run(_scrape_batch())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(bind=True, name="app.tasks.scraping_tasks.process_page_content")
def process_page_content(self, page_id: int) -> Dict[str, Any]:
    """
    Process scraped page content and add to search index
    """
    try:
        async def _process_content():
            async with AsyncSessionLocal() as db:
                # Get page with domain and project
                page_result = await db.execute(
                    select(Page)
                    .join(Domain)
                    .join(Project)
                    .where(Page.id == page_id)
                )
                page = page_result.scalar_one_or_none()
                
                if not page:
                    raise Exception(f"Page {page_id} not found")
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 1, "total": 4, "status": "Processing content..."}
                )
                
                # Get the domain and project
                domain = page.domain
                project = domain.project
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 2, "total": 4, "status": "Analyzing content..."}
                )
                
                # Additional content analysis could go here
                # For now, we'll just ensure basic processing is done
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 3, "total": 4, "status": "Adding to search index..."}
                )
                
                # Add to Meilisearch index if project has search enabled
                if project.process_documents and page.extracted_text:
                    try:
                        document = {
                            "id": f"page_{page.id}",
                            "page_id": page.id,
                            "domain_id": page.domain_id,
                            "project_id": project.id,
                            "title": page.extracted_title or page.original_url,
                            "content": page.extracted_text,
                            "url": page.original_url,
                            "wayback_url": page.wayback_url,
                            "capture_date": page.capture_date.isoformat() if page.capture_date else None,
                            "scraped_at": page.scraped_at.isoformat() if page.scraped_at else None,
                            "word_count": page.word_count or 0,
                            "domain_name": domain.domain_name,
                            "meta_description": page.meta_description,
                            "meta_keywords": page.meta_keywords,
                            "author": page.author,
                            "published_date": page.published_date.isoformat() if page.published_date else None,
                            "language": page.language
                        }
                        
                        await MeilisearchService.add_document_to_project_index(
                            project, document
                        )
                        
                        logger.info(f"Added page {page_id} to search index")
                        
                    except Exception as e:
                        logger.error(f"Error adding page {page_id} to search index: {str(e)}")
                        # Don't fail the task if indexing fails
                
                current_task.update_state(
                    state="PROGRESS",
                    meta={"current": 4, "total": 4, "status": "Content processing completed"}
                )
                
                # Mark as fully processed
                page.indexed_at = datetime.utcnow()
                await db.commit()
                
                return {
                    "page_id": page_id,
                    "status": "completed",
                    "indexed": project.process_documents
                }
        
        return asyncio.run(_process_content())
        
    except Exception as exc:
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(exc)}
        )
        raise exc


@celery_app.task(name="app.tasks.scraping_tasks.cleanup_failed_scrapes")
def cleanup_failed_scrapes() -> Dict[str, Any]:
    """
    Cleanup failed scrape sessions (periodic task)
    """
    try:
        async def _cleanup():
            async with AsyncSessionLocal() as db:
                # Find failed scrape sessions older than 24 hours
                cutoff_time = datetime.utcnow() - timedelta(hours=24)
                
                result = await db.execute(
                    select(ScrapeSession).where(
                        ScrapeSession.status == "failed",
                        ScrapeSession.updated_at < cutoff_time
                    )
                )
                failed_sessions = result.scalars().all()
                
                cleaned_count = 0
                for session in failed_sessions:
                    # Reset session status to allow retry
                    session.status = "pending"
                    session.error_message = None
                    cleaned_count += 1
                
                await db.commit()
                
                return {
                    "cleaned_sessions": cleaned_count,
                    "status": "completed"
                }
        
        return asyncio.run(_cleanup())
        
    except Exception as exc:
        raise exc