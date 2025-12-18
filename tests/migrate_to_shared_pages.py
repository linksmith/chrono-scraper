#!/usr/bin/env python3
"""
Migration script to populate shared_pages Meilisearch index with existing data

This bridges the gap between the legacy pages/domains/projects schema 
and the new shared pages architecture expectations.
"""
import asyncio
import logging
from typing import List, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import application modules
import sys
import os
sys.path.append('/app')  # Add backend to path

from app.core.database import get_db
from app.models.project import Page, Project, Domain  # Legacy models
from app.services.shared_pages_meilisearch import SharedPagesMeilisearchService


class LegacyToSharedPageMigrator:
    """Migrates legacy pages to shared pages index"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.meilisearch_service = SharedPagesMeilisearchService(db)
        
    async def migrate_all_pages(self) -> Dict[str, Any]:
        """Migrate all legacy pages to shared pages index"""
        logger.info("Starting migration of legacy pages to shared pages index...")
        
        try:
            # Get all pages with their project relationships
            pages_query = select(Page).order_by(Page.id)
            result = await self.db.execute(pages_query)
            all_pages = result.scalars().all()
            
            logger.info(f"Found {len(all_pages)} pages to migrate")
            
            migrated_count = 0
            failed_count = 0
            
            for page in all_pages:
                try:
                    await self._migrate_single_page(page)
                    migrated_count += 1
                    
                    if migrated_count % 10 == 0:
                        logger.info(f"Migrated {migrated_count}/{len(all_pages)} pages...")
                        
                except Exception as e:
                    logger.warning(f"Failed to migrate page {page.id}: {e}")
                    failed_count += 1
            
            logger.info(f"Migration completed: {migrated_count} successful, {failed_count} failed")
            
            return {
                "total_pages": len(all_pages),
                "migrated": migrated_count,
                "failed": failed_count
            }
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
    
    async def _migrate_single_page(self, page: Page) -> None:
        """Migrate a single legacy page to shared pages format"""
        
        # Get the domain and project for this page
        domain = None
        project = None
        
        if page.domain_id:
            domain = await self.db.get(Domain, page.domain_id)
            if domain and domain.project_id:
                project = await self.db.get(Project, domain.project_id)
        
        if not project:
            logger.warning(f"Page {page.id} has no valid project association, skipping")
            return
        
        # Create a document for Meilisearch indexing
        document = {
            "id": str(page.id),
            "url": page.original_url,  # Use original_url from PageBase
            "title": page.extracted_title or page.title or "",
            "content": page.extracted_text or "",  # Use extracted_text from PageBase
            "description": page.meta_description or "",
            "author": page.author or "",
            "language": page.language or "en",
            "timestamp": page.unix_timestamp,
            "capture_date": page.capture_date.isoformat() if page.capture_date else page.scraped_at.isoformat() if page.scraped_at else None,
            "created_at": page.created_at.isoformat() if page.created_at else datetime.utcnow().isoformat(),
            "quality_score": page.quality_score,  # Now available in PageBase
            "word_count": page.word_count or 0,
            "character_count": page.character_count or 0,
            
            # Project associations - single project for legacy pages
            "project_ids": [project.id],
            "domain_ids": [domain.id] if domain else [],
            "tags": page.tags or [],  # Tags are available in PageBase
            "is_starred": False,  # Will be determined by starred_items table
            "review_statuses": [page.review_status] if page.review_status else [],
            "categories": [page.page_category] if page.page_category else [],
            "priority_levels": [page.priority_level] if page.priority_level else [],
            
            # Sharing metadata
            "project_count": 1,  # Legacy pages belong to single project
            "is_shared": False   # Legacy pages are not shared
        }
        
        # Add to Meilisearch
        await self.meilisearch_service._configure_index()
        await self.meilisearch_service.index.add_documents([document])
        
        logger.debug(f"Migrated page {page.id} to shared pages index")


async def main():
    """Run the migration"""
    logger.info("Starting legacy to shared pages migration...")
    
    try:
        # Get database session
        async for db in get_db():
            migrator = LegacyToSharedPageMigrator(db)
            result = await migrator.migrate_all_pages()
            
            logger.info("Migration completed successfully!")
            logger.info(f"Results: {result}")
            break
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())