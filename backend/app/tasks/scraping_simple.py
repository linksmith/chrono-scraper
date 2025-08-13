"""
Simplified scraping tasks for Celery
This module provides a working implementation of scraping tasks
that properly handles async/await with Celery workers.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from celery import current_task
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

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.scraping_simple.start_domain_scrape")
def start_domain_scrape(self, domain_id: int, scrape_session_id: int) -> Dict[str, Any]:
    """
    Start scraping a domain - simplified version
    This task updates the session status and creates sample pages for testing
    """
    # Use asyncio.run() to handle async database operations
    return asyncio.run(_start_domain_scrape_async(domain_id, scrape_session_id))


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
                        wayback_url=f"https://web.archive.org/web/20240101000000/{url}",
                        unix_timestamp=1704067200 + (i * 86400),  # Sample timestamps
                        status_code=200,
                        mime_type="text/html",
                        processed=False,
                        indexed=False,
                        title=f"Sample Page {i+1}"
                    )
                    db.add(page)
                    pages_created += 1
            
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
                    Page.processed == False
                )
            )
            pages_to_process = page_results.scalars().all()
            
            for page in pages_to_process:
                # For demonstration, just mark as processed
                page.processed = True
                page.extracted_text = f"Sample content for {page.original_url}"
                page.extracted_title = page.title or "Sample Title"
                page.word_count = 100
                page.character_count = 500
            
            await db.commit()
            
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
                if scrape_session:
                    scrape_session.status = ScrapeSessionStatus.FAILED
                    scrape_session.error_message = str(e)
                    await db.commit()
            except:
                pass
            
            return {
                "status": "error",
                "message": str(e),
                "domain_id": domain_id,
                "session_id": scrape_session_id
            }


@celery_app.task(bind=True, name="app.tasks.scraping_simple.process_page_content")
def process_page_content(self, page_id: int) -> Dict[str, Any]:
    """
    Process a single page's content - simplified version
    """
    return asyncio.run(_process_page_async(page_id))


async def _process_page_async(page_id: int) -> Dict[str, Any]:
    """
    Async implementation of page processing
    """
    async with AsyncSessionLocal() as db:
        try:
            page_result = await db.execute(
                select(Page).where(Page.id == page_id)
            )
            page = page_result.scalar_one_or_none()
            
            if not page:
                return {"status": "error", "message": f"Page {page_id} not found"}
            
            # Simulate content processing
            page.processed = True
            page.indexed = True
            page.extracted_text = f"Processed content for page {page_id}"
            page.word_count = 250
            page.character_count = 1500
            
            await db.commit()
            
            return {
                "status": "success",
                "page_id": page_id,
                "url": page.original_url
            }
            
        except Exception as e:
            logger.error(f"Error processing page {page_id}: {str(e)}")
            return {
                "status": "error", 
                "message": str(e),
                "page_id": page_id
            }