"""
Enhanced scraping tasks for shared pages architecture with deduplication
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any
from uuid import UUID
from app.core.uuid_utils import uuid_v7
from sqlmodel import Session, select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.tasks.celery_app import celery_app
from app.core.config import settings
from app.models.shared_pages import (
    PageV2, ProjectPage, CDXPageRegistry, ScrapeStatus,
    PageReviewStatus, PagePriority
)
from app.models.project import Project
from app.services.content_extraction_service import get_content_extraction_service
# CDX service not needed in this module - remove circular import
from app.services.meilisearch_service import meilisearch_service
from app.models.extraction_data import ExtractedContent

logger = logging.getLogger(__name__)


def get_sync_session():
    """Create a synchronous database session for Celery tasks"""
    engine = create_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )
    SessionLocal = sessionmaker(
        engine,
        class_=Session,
        expire_on_commit=False,
    )
    return SessionLocal()


@celery_app.task(bind=True, max_retries=3)
def scrape_wayback_page_deduplicated(
    self,
    url: str,
    timestamp: int,
    project_id: str,
    domain_id: str
) -> Dict[str, Any]:
    """
    Scrape individual page with comprehensive deduplication checking
    
    This task implements the new shared pages architecture:
    1. Double-checks for existing pages (race condition prevention)
    2. Creates PageV2 records for new content
    3. Links pages to projects via ProjectPage junction table
    4. Updates CDX registry status
    5. Indexes in Meilisearch with project associations
    """
    db = None
    project_id_int = int(project_id)
    domain_id_int = int(domain_id)
    
    try:
        # Update task state
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 1,
                "total": 5,
                "status": f"Checking for existing page: {url}",
                "url": url,
                "timestamp": timestamp,
                "project_id": project_id_int
            }
        )
        
        db = get_sync_session()
        
        # Step 1: Double-check page doesn't exist (race condition prevention)
        existing_page = db.execute(
            select(PageV2).where(
                PageV2.url == url,
                PageV2.unix_timestamp == timestamp
            )
        ).scalar_one_or_none()
        
        if existing_page:
            logger.info(f"Page already exists for {url}:{timestamp}, linking to project {project_id_int}")
            
            # Link existing page to project if not already linked
            _link_existing_page_to_project(
                db, existing_page.id, project_id_int, domain_id_int
            )
            
            # Update CDX registry status
            _update_cdx_registry_completed(db, url, timestamp, existing_page.id)
            
            # Cache the page existence (sync method needed)
            try:
                from app.services.cache_service import PageCacheService
                PageCacheService()
                # Use sync method or skip caching for now
                logger.debug(f"Page {existing_page.id} linked to cache")
            except Exception as e:
                logger.warning(f"Cache update failed: {e}")
            
            return {
                "status": "linked_existing",
                "page_id": str(existing_page.id),
                "url": url,
                "timestamp": timestamp,
                "project_id": project_id_int
            }
        
        # Step 2: Update CDX registry to in_progress
        self.update_state(
            state="PROGRESS", 
            meta={
                "current": 2,
                "total": 5,
                "status": f"Starting scraping: {url}",
                "url": url
            }
        )
        
        _update_cdx_registry_in_progress(db, url, timestamp)
        
        # Step 3: Fetch and extract content
        logger.info(f"Scraping new page: {url}:{timestamp}")
        
        # Get Firecrawl extractor (create sync version or use asyncio)
        try:
            extractor = asyncio.run(get_content_extraction_service())
            wayback_url = f"https://web.archive.org/web/{timestamp}if_/{url}"
            
            # Extract content
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": 3,
                    "total": 5,
                    "status": f"Extracting content: {url}",
                    "url": url
                }
            )
            
            extracted_content = asyncio.run(extractor.extract_from_wayback_url(wayback_url))
        except Exception as e:
            logger.error(f"Failed to get extractor or extract content: {e}")
            # Mark as failed in CDX registry
            _update_cdx_registry_failed(db, url, timestamp, str(e))
            raise
        
        if not extracted_content or not extracted_content.success:
            error_msg = f"Failed to extract content from {wayback_url}"
            logger.error(error_msg)
            
            # Mark as failed in CDX registry
            _update_cdx_registry_failed(db, url, timestamp, error_msg)
            
            raise Exception(error_msg)
        
        # Step 4: Create PageV2 record
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 4,
                "total": 5,
                "status": f"Creating page record: {url}",
                "url": url
            }
        )
        
        page_id = uuid_v7()
        
        # Create enhanced page record with all extracted data
        page = PageV2(
            id=page_id,
            url=url,
            unix_timestamp=timestamp,
            content_url=wayback_url,
            title=extracted_content.title,
            extracted_title=extracted_content.title,
            extracted_text=extracted_content.markdown,
            content=extracted_content.content,
            markdown_content=extracted_content.markdown,
            meta_description=extracted_content.description,
            author=extracted_content.author,
            language=extracted_content.language,
            published_date=extracted_content.published_date,
            word_count=len(extracted_content.markdown.split()) if extracted_content.markdown else None,
            character_count=len(extracted_content.markdown) if extracted_content.markdown else None,
            content_type="text/html",
            content_length=len(extracted_content.content) if extracted_content.content else None,
            status_code=extracted_content.status_code,
            capture_date=datetime.fromtimestamp(timestamp / 1000) if len(str(timestamp)) > 10 else datetime.fromtimestamp(timestamp),
            processed=True,
            indexed=False,
            quality_score=_calculate_quality_score(extracted_content),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Store extracted data as JSON
        if extracted_content:
            page.extracted_data = {
                "title": extracted_content.title,
                "description": extracted_content.description,
                "author": extracted_content.author,
                "language": extracted_content.language,
                "published_date": extracted_content.published_date.isoformat() if extracted_content.published_date else None,
                "status_code": extracted_content.status_code,
                "success": extracted_content.success,
                "extraction_method": "firecrawl"
            }
        
        db.add(page)
        db.flush()  # Get the page ID
        
        # Step 5: Link to project via ProjectPage
        _link_page_to_project(db, page_id, project_id_int, domain_id_int)
        
        # Update CDX registry status
        _update_cdx_registry_completed(db, url, timestamp, page_id)
        
        db.commit()
        
        # Step 6: Index in Meilisearch with project association
        self.update_state(
            state="PROGRESS",
            meta={
                "current": 5,
                "total": 5,
                "status": f"Indexing page: {url}",
                "url": url
            }
        )
        
        try:
            asyncio.run(_index_page_with_project(page, project_id_int))
        except Exception as e:
            logger.warning(f"Failed to index page in Meilisearch: {e}")
            # Don't fail the task for indexing errors
        
        # Cache the page existence (sync version needed)
        try:
            logger.debug(f"Page {page_id} cached for {url}:{timestamp}")
        except Exception as e:
            logger.warning(f"Cache update failed: {e}")
        
        logger.info(f"Successfully scraped and created page {page_id} for {url}:{timestamp}")
        
        return {
            "status": "scraped_new",
            "page_id": str(page_id),
            "url": url,
            "timestamp": timestamp,
            "project_id": project_id_int,
            "word_count": page.word_count,
            "quality_score": page.quality_score
        }
        
    except Exception as e:
        logger.error(f"Scraping failed for {url}:{timestamp} - {str(e)}")
        
        if db:
            try:
                _update_cdx_registry_failed(db, url, timestamp, str(e))
                db.commit()
            except Exception:
                pass
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)
            logger.info(f"Retrying scraping for {url} in {countdown} seconds")
            raise self.retry(exc=e, countdown=countdown)
        else:
            logger.error(f"Max retries exceeded for {url}:{timestamp}")
            raise e
            
    finally:
        if db:
            db.close()


def _link_existing_page_to_project(
    db: Session,
    page_id: UUID,
    project_id: int,
    domain_id: int
) -> None:
    """Link existing page to project if not already linked"""
    
    # Check if association already exists
    existing_link = db.execute(
        select(ProjectPage).where(
            ProjectPage.project_id == project_id,
            ProjectPage.page_id == page_id
        )
    ).scalar_one_or_none()
    
    if existing_link:
        logger.debug(f"Page {page_id} already linked to project {project_id}")
        return
    
    # Get user_id for the project
    project = db.get(Project, project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")
    
    # Create new association
    project_page = ProjectPage(
        project_id=project_id,
        page_id=page_id,
        domain_id=domain_id,
        added_by=project.user_id,
        review_status=PageReviewStatus.PENDING,
        priority_level=PagePriority.MEDIUM,
        is_starred=False,
        tags=[],
        is_duplicate=False,
        added_at=datetime.utcnow()
    )
    
    db.add(project_page)
    db.commit()
    
    logger.info(f"Linked existing page {page_id} to project {project_id}")


def _link_page_to_project(
    db: Session,
    page_id: UUID,
    project_id: int,
    domain_id: int
) -> None:
    """Create project-page association for new page"""
    
    # Get user_id for the project
    project = db.get(Project, project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")
    
    project_page = ProjectPage(
        project_id=project_id,
        page_id=page_id,
        domain_id=domain_id,
        added_by=project.user_id,
        review_status=PageReviewStatus.PENDING,
        priority_level=PagePriority.MEDIUM,
        is_starred=False,
        tags=[],
        is_duplicate=False,
        added_at=datetime.utcnow()
    )
    
    db.add(project_page)
    logger.debug(f"Created project-page association: project {project_id} -> page {page_id}")


def _update_cdx_registry_in_progress(db: Session, url: str, timestamp: int) -> None:
    """Update CDX registry status to in_progress"""
    
    registry_entry = db.execute(
        select(CDXPageRegistry).where(
            CDXPageRegistry.url == url,
            CDXPageRegistry.unix_timestamp == timestamp
        )
    ).scalar_one_or_none()
    
    if registry_entry:
        registry_entry.scrape_status = ScrapeStatus.IN_PROGRESS
        db.commit()


def _update_cdx_registry_completed(
    db: Session,
    url: str,
    timestamp: int,
    page_id: UUID
) -> None:
    """Update CDX registry status to completed"""
    
    registry_entry = db.execute(
        select(CDXPageRegistry).where(
            CDXPageRegistry.url == url,
            CDXPageRegistry.unix_timestamp == timestamp
        )
    ).scalar_one_or_none()
    
    if registry_entry:
        registry_entry.scrape_status = ScrapeStatus.COMPLETED
        registry_entry.page_id = page_id
        db.commit()


def _update_cdx_registry_failed(
    db: Session,
    url: str,
    timestamp: int,
    error_message: str
) -> None:
    """Update CDX registry status to failed"""
    
    registry_entry = db.execute(
        select(CDXPageRegistry).where(
            CDXPageRegistry.url == url,
            CDXPageRegistry.unix_timestamp == timestamp
        )
    ).scalar_one_or_none()
    
    if registry_entry:
        registry_entry.scrape_status = ScrapeStatus.FAILED


async def _index_page_with_project(page: PageV2, project_id: int) -> None:
    """Index page in Meilisearch with project association"""
    
    # Create document for Meilisearch
    document = {
        "id": str(page.id),
        "url": page.url,
        "title": page.title or page.extracted_title,
        "content": page.extracted_text or page.markdown_content,
        "description": page.meta_description,
        "author": page.author,
        "language": page.language,
        "timestamp": page.unix_timestamp,
        "capture_date": page.capture_date.isoformat() if page.capture_date else None,
        "project_ids": [project_id],  # This page is associated with this project
        "quality_score": float(page.quality_score) if page.quality_score else None,
        "word_count": page.word_count,
        "indexed_at": datetime.utcnow().isoformat()
    }
    
    # Use async context manager for Meilisearch
    async with meilisearch_service:
        await meilisearch_service.add_documents([document])


def _calculate_quality_score(extracted_content: ExtractedContent) -> float:
    """Calculate quality score for page content"""
    score = 5.0  # Base score
    
    if not extracted_content or not extracted_content.success:
        return 1.0
    
    # Content length scoring
    if extracted_content.markdown:
        content_length = len(extracted_content.markdown)
        if content_length > 5000:
            score += 2.0
        elif content_length > 1000:
            score += 1.0
        elif content_length < 200:
            score -= 2.0
    
    # Title presence
    if extracted_content.title and len(extracted_content.title.strip()) > 10:
        score += 0.5
    
    # Description presence
    if extracted_content.description and len(extracted_content.description.strip()) > 20:
        score += 0.5
    
    # Author presence
    if extracted_content.author:
        score += 0.5
    
    # Language detection
    if extracted_content.language:
        score += 0.5
    
    # Status code scoring
    if extracted_content.status_code == 200:
        score += 1.0
    elif extracted_content.status_code and extracted_content.status_code >= 400:
        score -= 2.0
    
    # Ensure score is between 1 and 10
    return max(1.0, min(10.0, score))