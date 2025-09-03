"""
Simplified scraping tasks for Celery
This module provides a working implementation of scraping tasks
that properly handles async/await with Celery workers.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any
from sqlmodel import select

from app.tasks.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.project import (
    Domain, 
    ScrapeSession, 
    ScrapeSessionStatus, 
    DomainStatus,
    Page
)
# Simple Meilisearch integration without external dependencies
try:
    import meilisearch_python_async as meilisearch
    MEILISEARCH_AVAILABLE = True
except ImportError:
    MEILISEARCH_AVAILABLE = False

from app.core.config import settings
from app.services.websocket_service import (
    broadcast_page_progress_sync,
    broadcast_cdx_discovery_sync,
    broadcast_processing_stage_sync,
    broadcast_session_stats_sync
)
from app.models.scraping import ScrapePageStatus

logger = logging.getLogger(__name__)


async def _simple_meilisearch_index(index_name: str, page: Page) -> bool:
    """Simple Meilisearch indexing without external dependencies"""
    if not MEILISEARCH_AVAILABLE:
        logger.info(f"Mock: Indexed page {page.id} in index '{index_name}'")
        return True
        
    try:
        # Create simple client
        client = meilisearch.Client(
            url=settings.MEILISEARCH_HOST or "http://localhost:7700",
            api_key=settings.MEILISEARCH_MASTER_KEY
        )
        
        # Get or create index
        try:
            await client.create_index(index_name, "id")
        except:
            pass  # Index might already exist
        
        # Prepare document
        document = {
            "id": page.id,
            "original_url": page.original_url,
            "content_url": page.content_url or "",
            "title": page.title or page.extracted_title or "",
            "extracted_text": page.extracted_text or "",
            "domain_id": page.domain_id,
            "word_count": page.word_count or 0,
            "character_count": page.character_count or 0,
            "mime_type": page.mime_type or "",
            "status_code": page.status_code or 200,
            "unix_timestamp": page.unix_timestamp or 0
        }
        
        # Index document
        index = client.index(index_name)
        await index.add_documents([document])
        
        logger.info(f"Successfully indexed page {page.id} in Meilisearch")
        return True
        
    except Exception as e:
        logger.error(f"Failed to index page {page.id}: {e}")
        return False


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
    # Ensure we have a proper event loop
    loop = _ensure_event_loop()
    
    try:
        # Run the async task in the current loop
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
    Async implementation of domain scraping
    """
    async with AsyncSessionLocal() as db:
        try:
            # Get domain and scrape session
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
            
            # Update session status to running
            scrape_session.status = ScrapeSessionStatus.RUNNING
            scrape_session.started_at = datetime.utcnow()
            
            # Domain status remains active during scraping
            # domain.status = DomainStatus.ACTIVE  # Keep as active
            await db.commit()
            
            # Broadcast CDX discovery start
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
            
            # For now, create some sample pages to demonstrate functionality
            # In production, this would call the Wayback Machine API
            sample_urls = [
                f"https://{domain.domain_name}/",
                f"https://{domain.domain_name}/about",
                f"https://{domain.domain_name}/contact",
                f"https://{domain.domain_name}/products",
                f"https://{domain.domain_name}/services"
            ]
            
            pages_created = 0
            for i, url in enumerate(sample_urls):
                # Check if page already exists
                existing_page = await db.execute(
                    select(Page).where(
                        Page.domain_id == domain_id,
                        Page.original_url == url
                    )
                )
                
                if not existing_page.scalar_one_or_none():
                    # Create new page
                    page = Page(
                        domain_id=domain_id,
                        original_url=url,
                        content_url=f"https://web.archive.org/web/20240101000000if_/{url}",
                        unix_timestamp=1704067200 + (i * 86400),  # Sample timestamps
                        status_code=200,
                        mime_type="text/html",
                        processed=False,
                        indexed=False,
                        title=f"Sample Page {i+1}"
                    )
                    db.add(page)
                    pages_created += 1
                    
                    # Broadcast CDX discovery progress
                    broadcast_cdx_discovery_sync({
                        "scrape_session_id": scrape_session_id,
                        "domain_id": domain_id,
                        "domain_name": domain.domain_name,
                        "current_page": 1,
                        "total_pages": 1,
                        "results_found": i + 1,
                        "results_processed": i + 1,
                        "duplicates_filtered": 0,
                        "list_pages_filtered": 0,
                        "high_value_pages": 1 if i % 2 == 0 else 0  # Simulate some high value pages
                    })
            
            # Update session with progress
            scrape_session.total_urls = len(sample_urls)
            scrape_session.completed_urls = pages_created
            scrape_session.status = ScrapeSessionStatus.COMPLETED
            scrape_session.completed_at = datetime.utcnow()
            
            # Update domain statistics
            domain.total_pages = pages_created
            domain.status = DomainStatus.COMPLETED
            domain.last_scraped = datetime.utcnow()
            
            await db.commit()
            
            logger.info(f"Completed scraping for domain {domain.domain_name}. Created {pages_created} pages.")
            
            # Queue page processing tasks (simplified - just mark as processed)
            # In production, this would queue actual content extraction tasks
            page_results = await db.execute(
                select(Page).where(
                    Page.domain_id == domain_id,
                    Page.processed is False
                )
            )
            pages_to_process = page_results.scalars().all()
            
            # Index pages in Meilisearch
            index_name = f"project_{domain.project_id}"
            pages_indexed = 0
            for page in pages_to_process:
                # Broadcast content fetch stage
                broadcast_processing_stage_sync({
                    "scrape_session_id": scrape_session_id,
                    "scrape_page_id": page.id,
                    "domain_id": domain_id,
                    "page_url": page.original_url,
                    "stage": "content_fetch",
                    "stage_status": "started"
                })
                
                # For demonstration, just mark as processed
                page.processed = True
                page.extracted_text = f"Sample content for {page.original_url}"
                page.extracted_title = page.title or "Sample Title"
                page.word_count = 100
                page.character_count = 500
                
                # Broadcast content extraction stage
                broadcast_processing_stage_sync({
                    "scrape_session_id": scrape_session_id,
                    "scrape_page_id": page.id,
                    "domain_id": domain_id,
                    "page_url": page.original_url,
                    "stage": "content_extract",
                    "stage_status": "completed",
                    "stage_details": {
                        "word_count": page.word_count,
                        "character_count": page.character_count
                    }
                })
                
                # Broadcast indexing stage
                broadcast_processing_stage_sync({
                    "scrape_session_id": scrape_session_id,
                    "scrape_page_id": page.id,
                    "domain_id": domain_id,
                    "page_url": page.original_url,
                    "stage": "indexing",
                    "stage_status": "started"
                })
                
                # Index the page in Meilisearch
                indexed = await _simple_meilisearch_index(index_name, page)
                page.indexed = indexed
                if indexed:
                    pages_indexed += 1
                
                # Broadcast page completion
                broadcast_page_progress_sync({
                    "scrape_session_id": scrape_session_id,
                    "scrape_page_id": page.id,
                    "domain_id": domain_id,
                    "domain_name": domain.domain_name,
                    "page_url": page.original_url,
                    "content_url": page.content_url or "",
                    "status": ScrapePageStatus.COMPLETED,
                    "processing_stage": "completed",
                    "stage_progress": 1.0
                })
            
            await db.commit()
            
            logger.info(f"Indexed {pages_indexed}/{len(pages_to_process)} pages")
            
            # Broadcast final session stats
            broadcast_session_stats_sync({
                "scrape_session_id": scrape_session_id,
                "total_urls": len(sample_urls),
                "pending_urls": 0,
                "in_progress_urls": 0,
                "completed_urls": pages_created,
                "failed_urls": 0,
                "skipped_urls": 0,
                "progress_percentage": 100.0,
                "active_domains": 0,
                "completed_domains": 1,
                "failed_domains": 0,
                "performance_metrics": {
                    "pages_indexed": pages_indexed,
                    "indexing_success_rate": (pages_indexed / len(pages_to_process)) * 100 if pages_to_process else 0
                }
            })
            
            return {
                "status": "success",
                "domain_id": domain_id,
                "session_id": scrape_session_id,
                "pages_created": pages_created,
                "domain_name": domain.domain_name
            }
            
        except Exception as e:
            logger.error(f"Error in domain scrape task: {str(e)}")
            
            # Try to update session status to failed
            try:
                if 'scrape_session' in locals() and scrape_session:
                    scrape_session.status = ScrapeSessionStatus.FAILED
                    scrape_session.error_message = str(e)
                    await db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to update session status: {commit_error}")
            
            # Re-raise the exception to be handled by the task wrapper
            raise


@celery_app.task(bind=True, name="app.tasks.scraping_simple.process_page_content")
def process_page_content(self, page_id: int) -> Dict[str, Any]:
    """
    Process a single page's content - simplified version
    """
    # Ensure we have a proper event loop
    loop = _ensure_event_loop()
    
    try:
        # Run the async task in the current loop
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
    Async implementation of page processing (for retries)
    """
    async with AsyncSessionLocal() as db:
        try:
            # First try to find as ScrapePage (for retries)
            from app.models.scraping import ScrapePage, ScrapePageStatus
            
            scrape_page_result = await db.execute(
                select(ScrapePage).where(ScrapePage.id == page_id)
            )
            scrape_page = scrape_page_result.scalar_one_or_none()
            
            if scrape_page:
                # This is a retry scenario
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
                    # Simulate content processing with retry
                    scrape_page.extracted_text = f"Retry content for {scrape_page.original_url}"
                    scrape_page.extracted_content = f"<h1>Retry Content</h1><p>This is retry content for {scrape_page.original_url}</p>"
                    scrape_page.title = f"Retry Page {scrape_page.id}"
                    scrape_page.markdown_content = f"# Retry Content\n\nThis is retry content for {scrape_page.original_url}"
                    
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
                            "text_length": len(scrape_page.extracted_text or "")
                        }
                    })
                    
                    # Broadcast indexing stage
                    broadcast_processing_stage_sync({
                        "scrape_session_id": scrape_page.scrape_session_id or 0,
                        "scrape_page_id": scrape_page.id,
                        "domain_id": scrape_page.domain_id or 0,
                        "page_url": scrape_page.original_url,
                        "stage": "indexing",
                        "stage_status": "started"
                    })
                    
                    # Simulate indexing success
                    index_name = f"project_{domain.project_id}"
                    # Create a temporary Page object for indexing
                    temp_page = Page(
                        domain_id=scrape_page.domain_id,
                        original_url=scrape_page.original_url,
                        content_url=scrape_page.content_url,
                        title=scrape_page.title,
                        extracted_text=scrape_page.extracted_text,
                        word_count=len(scrape_page.extracted_text.split()) if scrape_page.extracted_text else 0,
                        character_count=len(scrape_page.extracted_text) if scrape_page.extracted_text else 0,
                        mime_type=scrape_page.mime_type
                    )
                    indexed = await _simple_meilisearch_index(index_name, temp_page)
                    
                    # Update scrape page status
                    scrape_page.status = ScrapePageStatus.COMPLETED if indexed else ScrapePageStatus.FAILED
                    scrape_page.completed_at = datetime.utcnow()
                    
                    if not indexed:
                        scrape_page.error_message = "Failed to index content"
                        scrape_page.error_type = "indexing_error"
                    
                    await db.commit()
                    
                    # Broadcast final status
                    broadcast_page_progress_sync({
                        "scrape_session_id": scrape_page.scrape_session_id or 0,
                        "scrape_page_id": scrape_page.id,
                        "domain_id": scrape_page.domain_id or 0,
                        "domain_name": domain.domain_name,
                        "page_url": scrape_page.original_url,
                        "content_url": scrape_page.content_url or "",
                        "status": scrape_page.status,
                        "processing_stage": "completed" if indexed else "failed",
                        "stage_progress": 1.0 if indexed else 0.0,
                        "retry_count": scrape_page.retry_count,
                        "error_message": scrape_page.error_message
                    })
                    
                    return {
                        "status": "success" if indexed else "failed",
                        "page_id": page_id,
                        "url": scrape_page.original_url,
                        "indexed": indexed,
                        "retry_count": scrape_page.retry_count
                    }
                    
                except Exception as processing_error:
                    # Handle processing failure
                    scrape_page.status = ScrapePageStatus.FAILED
                    scrape_page.error_message = str(processing_error)
                    scrape_page.error_type = "processing_error"
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
            
            else:
                # Try as regular Page (legacy)
                page_result = await db.execute(
                    select(Page).where(Page.id == page_id)
                )
                page = page_result.scalar_one_or_none()
                
                if not page:
                    return {"status": "error", "message": f"Page {page_id} not found"}
                
                # Get the domain to find project_id
                domain_result = await db.execute(
                    select(Domain).where(Domain.id == page.domain_id)
                )
                domain = domain_result.scalar_one_or_none()
                
                if not domain:
                    return {"status": "error", "message": f"Domain for page {page_id} not found"}
                
                # Simulate content processing
                page.processed = True
                page.extracted_text = f"Processed content for page {page_id}"
                page.word_count = 250
                page.character_count = 1500
                
                # Index the page
                index_name = f"project_{domain.project_id}"
                page.indexed = await _simple_meilisearch_index(index_name, page)
                
                await db.commit()
                
                return {
                    "status": "success",
                    "page_id": page_id,
                    "url": page.original_url,
                    "indexed": page.indexed
                }
            
        except Exception as e:
            logger.error(f"Error processing page {page_id}: {str(e)}")
            # Re-raise the exception to be handled by the task wrapper
            raise