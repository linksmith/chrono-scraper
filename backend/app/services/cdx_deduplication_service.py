"""
Enhanced CDX processing service with deduplication support
"""
import logging
from typing import List, Tuple, Dict, Optional, Set
from uuid import UUID
from datetime import datetime
from fastapi import Depends
from sqlmodel import Session, select, and_, or_
from sqlalchemy import text, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.database import get_db as get_db_gen
from app.models.shared_pages import (
    PageV2, ProjectPage, CDXPageRegistry, ScrapeStatus, 
    ProcessingStats, PageReviewStatus, PagePriority
)
from app.models.project import Domain, Project
from app.services.cache_service import PageCacheService
from app.tasks.shared_pages_scraping import scrape_wayback_page_deduplicated

logger = logging.getLogger(__name__)


class CDXRecord:
    """CDX record data structure"""
    def __init__(self, url: str, timestamp: int, wayback_url: str = None):
        self.url = url
        self.timestamp = timestamp
        self.wayback_url = wayback_url or f"https://web.archive.org/web/{timestamp}/{url}"


class EnhancedCDXService:
    """Enhanced CDX processing with deduplication"""
    
    def __init__(self, db: AsyncSession, cache_service: Optional[PageCacheService] = None):
        self.db = db
        self.cache = cache_service or PageCacheService()
    
    async def process_cdx_results(
        self,
        cdx_results: List[CDXRecord],
        project_id: int,
        domain_id: int
    ) -> ProcessingStats:
        """Process CDX results with comprehensive deduplication"""
        logger.info(f"Processing {len(cdx_results)} CDX records for project {project_id}")
        
        stats = ProcessingStats()
        
        if not cdx_results:
            return stats
        
        # Step 1: Bulk check cache for existing pages
        url_timestamp_pairs = [(record.url, record.timestamp) for record in cdx_results]
        
        # Check cache first for performance
        cached_existing = await self.cache.bulk_check_pages(url_timestamp_pairs)
        cached_keys = set(cached_existing.keys())
        
        # Get remaining pairs to check in database
        uncached_pairs = [pair for pair in url_timestamp_pairs if pair not in cached_keys]
        
        # Bulk database check for uncached pairs
        db_existing = {}
        if uncached_pairs:
            db_existing = await self._bulk_check_existing_pages(uncached_pairs)
            
            # Update cache with newly found pages
            for (url, timestamp), page_id in db_existing.items():
                await self.cache.set_page_exists(url, timestamp, page_id)
        
        # Combine cached and database results
        existing_pages = {**cached_existing, **db_existing}
        
        # Step 2: Check CDX registry for pages in progress
        processing_pages = await self._check_cdx_registry_status(url_timestamp_pairs)
        
        # Step 3: Categorize CDX records
        to_link = []
        to_scrape = []
        already_processing = []
        
        for record in cdx_results:
            key = (record.url, record.timestamp)
            
            if key in existing_pages:
                # Page exists, link to project
                page_id = existing_pages[key]
                to_link.append((page_id, record))
                stats.pages_linked += 1
                
            elif key in processing_pages:
                # Page is being processed
                registry_entry = processing_pages[key]
                if registry_entry.scrape_status in [ScrapeStatus.PENDING, ScrapeStatus.IN_PROGRESS]:
                    already_processing.append((registry_entry, record))
                    stats.pages_already_processing += 1
                else:
                    # Failed or completed without page creation, retry
                    to_scrape.append(record)
                    stats.pages_to_scrape += 1
            else:
                # New page, needs scraping
                to_scrape.append(record)
                stats.pages_to_scrape += 1
        
        # Step 4: Bulk link existing pages to project
        if to_link:
            linked_count = await self._bulk_link_pages_to_project(
                to_link, project_id, domain_id
            )
            logger.info(f"Linked {linked_count} existing pages to project {project_id}")
        
        # Step 5: Create project associations for pages already being processed
        if already_processing:
            processing_count = await self._link_processing_pages_to_project(
                already_processing, project_id, domain_id
            )
            logger.info(f"Created associations for {processing_count} pages in progress")
        
        # Step 6: Create CDX registry entries and scraping tasks for new pages
        if to_scrape:
            await self._create_scraping_tasks(to_scrape, project_id, domain_id)
            logger.info(f"Created {len(to_scrape)} scraping tasks for project {project_id}")
        
        stats.total_processed = len(cdx_results)
        
        logger.info(
            f"CDX processing complete for project {project_id}: "
            f"{stats.pages_linked} linked, {stats.pages_to_scrape} queued, "
            f"{stats.pages_already_processing} in progress"
        )
        
        return stats
    
    async def _bulk_check_existing_pages(
        self,
        url_timestamp_pairs: List[Tuple[str, int]]
    ) -> Dict[Tuple[str, int], UUID]:
        """Efficiently check for existing pages in database"""
        if not url_timestamp_pairs:
            return {}
        
        # Create VALUES clause for bulk checking
        values_list = []
        for url, timestamp in url_timestamp_pairs:
            # Escape single quotes in URL
            escaped_url = url.replace("'", "''")
            values_list.append(f"('{escaped_url}', {timestamp})")
        
        values_clause = ",".join(values_list)
        
        query = text(f"""
            SELECT p.id, v.url, v.timestamp 
            FROM pages_v2 p
            JOIN (VALUES {values_clause}) AS v(url, timestamp)
                ON p.url = v.url AND p.unix_timestamp = v.timestamp
        """)
        
        result = await self.db.execute(query)
        rows = result.fetchall()
        
        existing = {}
        for row in rows:
            page_id, url, timestamp = row
            existing[(url, timestamp)] = page_id
        
        return existing
    
    async def _check_cdx_registry_status(
        self,
        url_timestamp_pairs: List[Tuple[str, int]]
    ) -> Dict[Tuple[str, int], CDXPageRegistry]:
        """Check CDX registry for pages being processed"""
        if not url_timestamp_pairs:
            return {}
        
        # Build OR conditions for bulk query
        conditions = []
        for url, timestamp in url_timestamp_pairs:
            conditions.append(
                and_(CDXPageRegistry.url == url, CDXPageRegistry.unix_timestamp == timestamp)
            )
        
        stmt = select(CDXPageRegistry).where(or_(*conditions))
        result = await self.db.execute(stmt)
        registry_entries = result.scalars().all()
        
        processing = {}
        for entry in registry_entries:
            key = (entry.url, entry.unix_timestamp)
            processing[key] = entry
        
        return processing
    
    async def _bulk_link_pages_to_project(
        self,
        page_record_pairs: List[Tuple[UUID, CDXRecord]],
        project_id: int,
        domain_id: int
    ) -> int:
        """Bulk create project-page associations for existing pages"""
        if not page_record_pairs:
            return 0
        
        # Get user_id for the project
        project_stmt = select(Project.user_id).where(Project.id == project_id)
        project_result = await self.db.execute(project_stmt)
        user_id = project_result.scalar_one()
        
        # Prepare bulk insert data
        associations = []
        for page_id, record in page_record_pairs:
            associations.append({
                "project_id": project_id,
                "page_id": page_id,
                "domain_id": domain_id,
                "added_at": datetime.utcnow(),
                "added_by": user_id,
                "review_status": PageReviewStatus.PENDING.value,
                "priority_level": PagePriority.MEDIUM.value,
                "is_starred": False,
                "tags": [],
                "is_duplicate": False
            })
        
        # Use PostgreSQL's ON CONFLICT DO NOTHING for idempotency
        stmt = pg_insert(ProjectPage).values(associations)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=['project_id', 'page_id']
        )
        
        result = await self.db.execute(stmt)
        await self.db.commit()
        
        return len(associations)
    
    async def _link_processing_pages_to_project(
        self,
        registry_record_pairs: List[Tuple[CDXPageRegistry, CDXRecord]],
        project_id: int,
        domain_id: int
    ) -> int:
        """Create project associations for pages currently being processed"""
        if not registry_record_pairs:
            return 0
        
        # Get user_id for the project
        project_stmt = select(Project.user_id).where(Project.id == project_id)
        project_result = await self.db.execute(project_stmt)
        user_id = project_result.scalar_one()
        
        associations = []
        for registry_entry, record in registry_record_pairs:
            if registry_entry.page_id:
                # Page has been created, link it
                associations.append({
                    "project_id": project_id,
                    "page_id": registry_entry.page_id,
                    "domain_id": domain_id,
                    "added_at": datetime.utcnow(),
                    "added_by": user_id,
                    "review_status": PageReviewStatus.PENDING.value,
                    "priority_level": PagePriority.MEDIUM.value,
                    "is_starred": False,
                    "tags": [],
                    "is_duplicate": False
                })
        
        if associations:
            stmt = pg_insert(ProjectPage).values(associations)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=['project_id', 'page_id']
            )
            
            await self.db.execute(stmt)
            await self.db.commit()
        
        return len(associations)
    
    async def _create_scraping_tasks(
        self,
        cdx_records: List[CDXRecord],
        project_id: int,
        domain_id: int
    ) -> None:
        """Create CDX registry entries and Celery scraping tasks"""
        if not cdx_records:
            return
        
        # Step 1: Bulk create CDX registry entries
        registry_entries = []
        for record in cdx_records:
            registry_entries.append({
                "url": record.url,
                "unix_timestamp": record.timestamp,
                "scrape_status": ScrapeStatus.PENDING.value,
                "first_seen_at": datetime.utcnow(),
                "created_by_project_id": project_id
            })
        
        # Use ON CONFLICT DO NOTHING to handle race conditions
        stmt = pg_insert(CDXPageRegistry).values(registry_entries)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=['url', 'unix_timestamp']
        )
        
        await self.db.execute(stmt)
        await self.db.commit()
        
        # Step 2: Queue Celery tasks
        for record in cdx_records:
            scrape_wayback_page_deduplicated.delay(
                url=record.url,
                timestamp=record.timestamp,
                project_id=str(project_id),
                domain_id=str(domain_id)
            )
        
        logger.info(f"Queued {len(cdx_records)} scraping tasks for project {project_id}")
    
    async def mark_page_completed(
        self,
        url: str,
        timestamp: int,
        page_id: UUID,
        project_id: int
    ) -> None:
        """Mark a page as completed in CDX registry and link to project"""
        
        # Update CDX registry
        update_stmt = (
            CDXPageRegistry.__table__.update()
            .where(
                and_(
                    CDXPageRegistry.url == url,
                    CDXPageRegistry.unix_timestamp == timestamp
                )
            )
            .values(
                scrape_status=ScrapeStatus.COMPLETED.value,
                page_id=page_id
            )
        )
        
        await self.db.execute(update_stmt)
        
        # Cache the page existence
        await self.cache.set_page_exists(url, timestamp, page_id)
        
        logger.debug(f"Marked page {page_id} as completed for URL {url}:{timestamp}")
    
    async def mark_page_failed(
        self,
        url: str,
        timestamp: int,
        error_message: str
    ) -> None:
        """Mark a page as failed in CDX registry"""
        
        update_stmt = (
            CDXPageRegistry.__table__.update()
            .where(
                and_(
                    CDXPageRegistry.url == url,
                    CDXPageRegistry.unix_timestamp == timestamp
                )
            )
            .values(scrape_status=ScrapeStatus.FAILED.value)
        )
        
        await self.db.execute(update_stmt)
        await self.db.commit()
        
        logger.warning(f"Marked page as failed for URL {url}:{timestamp} - {error_message}")
    
    async def get_processing_statistics(self, project_id: Optional[int] = None) -> Dict:
        """Get CDX processing statistics"""
        
        base_query = select(CDXPageRegistry.scrape_status, CDXPageRegistry.created_by_project_id)
        
        if project_id:
            base_query = base_query.where(CDXPageRegistry.created_by_project_id == project_id)
        
        result = await self.db.execute(base_query)
        rows = result.fetchall()
        
        stats = {
            "total": len(rows),
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
            "by_project": {}
        }
        
        for status, proj_id in rows:
            stats[status] += 1
            
            if proj_id not in stats["by_project"]:
                stats["by_project"][proj_id] = {
                    "pending": 0,
                    "in_progress": 0, 
                    "completed": 0,
                    "failed": 0
                }
            stats["by_project"][proj_id][status] += 1
        
        return stats


async def get_cdx_service(db: AsyncSession = Depends(get_db)) -> EnhancedCDXService:
    """Dependency injection for CDX service"""
    cache_service = PageCacheService()
    return EnhancedCDXService(db, cache_service)