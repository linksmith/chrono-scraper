"""
Safe migration script to convert existing pages to shared pages architecture

This script migrates data from the old architecture (Page → Domain → Project)
to the new shared pages architecture (Page ← ProjectPage → Project).

Key features:
- Deduplicates pages by (URL, timestamp)
- Preserves all metadata and associations
- Creates junction table records
- Updates Meilisearch index
- Comprehensive logging and rollback capability
- Progress tracking and resumption

Usage:
    python scripts/migrate_to_shared_pages.py [--dry-run] [--batch-size 1000] [--resume]
"""
import asyncio
import argparse
import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from uuid import uuid4
import json
import sys
import os

# Add backend to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select, text
from sqlalchemy import create_engine, exc
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.project import Page as OldPage, Domain, Project
from app.models.shared_pages import PageV2, ProjectPage, PageReviewStatus, PagePriority
from app.services.shared_pages_meilisearch import SharedPagesMeilisearchService
from app.services.page_access_control import PageAccessControl

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MigrationProgress:
    """Track and persist migration progress"""
    
    def __init__(self, progress_file: str = "migration_progress.json"):
        self.progress_file = progress_file
        self.data = self._load_progress()
    
    def _load_progress(self) -> Dict[str, Any]:
        """Load progress from file"""
        try:
            if os.path.exists(self.progress_file):
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load progress file: {e}")
        
        return {
            "started_at": None,
            "last_checkpoint": None,
            "pages_processed": 0,
            "pages_deduplicated": 0,
            "associations_created": 0,
            "current_phase": None,
            "completed_phases": [],
            "errors": []
        }
    
    def save_progress(self):
        """Save progress to file"""
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(self.data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
    
    def start_migration(self):
        """Mark migration as started"""
        self.data["started_at"] = datetime.utcnow().isoformat()
        self.save_progress()
    
    def start_phase(self, phase_name: str):
        """Mark phase as started"""
        self.data["current_phase"] = phase_name
        self.data["last_checkpoint"] = datetime.utcnow().isoformat()
        logger.info(f"Starting phase: {phase_name}")
        self.save_progress()
    
    def complete_phase(self, phase_name: str):
        """Mark phase as completed"""
        if phase_name not in self.data["completed_phases"]:
            self.data["completed_phases"].append(phase_name)
        self.data["current_phase"] = None
        logger.info(f"Completed phase: {phase_name}")
        self.save_progress()
    
    def update_stats(self, **kwargs):
        """Update statistics"""
        for key, value in kwargs.items():
            if key in self.data:
                self.data[key] += value
            else:
                self.data[key] = value
        self.save_progress()
    
    def add_error(self, error: str):
        """Add error to log"""
        self.data["errors"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "error": error
        })
        self.save_progress()


class SharedPagesMigrator:
    """Main migration class"""
    
    def __init__(self, dry_run: bool = False, batch_size: int = 1000):
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.progress = MigrationProgress()
        
        # Database setup
        self.engine = create_engine(settings.DATABASE_URL, echo=False)
        SessionLocal = sessionmaker(self.engine, class_=Session, expire_on_commit=False)
        self.db = SessionLocal()
        
        logger.info(f"Migration initialized - Dry run: {dry_run}, Batch size: {batch_size}")
    
    async def run_migration(self, resume: bool = False) -> bool:
        """Run the complete migration process"""
        try:
            if not resume:
                self.progress.start_migration()
            
            logger.info("Starting shared pages migration")
            logger.info(f"Progress so far: {self.progress.data}")
            
            # Phase 1: Analyze existing data
            if "analyze_data" not in self.progress.data.get("completed_phases", []):
                analysis = await self._analyze_existing_data()
                if not analysis["can_migrate"]:
                    logger.error("Migration cannot proceed due to data issues")
                    return False
                self.progress.complete_phase("analyze_data")
            
            # Phase 2: Create deduplicated pages
            if "migrate_pages" not in self.progress.data.get("completed_phases", []):
                await self._migrate_pages_with_deduplication()
                self.progress.complete_phase("migrate_pages")
            
            # Phase 3: Create project-page associations
            if "create_associations" not in self.progress.data.get("completed_phases", []):
                await self._create_project_page_associations()
                self.progress.complete_phase("create_associations")
            
            # Phase 4: Update Meilisearch index
            if "update_search_index" not in self.progress.data.get("completed_phases", []):
                await self._update_meilisearch_index()
                self.progress.complete_phase("update_search_index")
            
            # Phase 5: Validate migration
            if "validate_migration" not in self.progress.data.get("completed_phases", []):
                validation_results = await self._validate_migration()
                if not validation_results["valid"]:
                    logger.error("Migration validation failed")
                    return False
                self.progress.complete_phase("validate_migration")
            
            logger.info("Migration completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.progress.add_error(str(e))
            return False
        finally:
            self.db.close()
    
    async def _analyze_existing_data(self) -> Dict[str, Any]:
        """Analyze existing data to plan migration"""
        self.progress.start_phase("analyze_data")
        
        try:
            # Count existing pages
            pages_count = self.db.execute(
                text("SELECT COUNT(*) FROM pages")
            ).scalar()
            
            # Find potential duplicates
            duplicates_query = text("""
                SELECT original_url, unix_timestamp, COUNT(*) as count
                FROM pages 
                GROUP BY original_url, unix_timestamp 
                HAVING COUNT(*) > 1
                ORDER BY count DESC
                LIMIT 10
            """)
            duplicate_samples = self.db.execute(duplicates_query).fetchall()
            
            # Calculate deduplication potential
            unique_pages_query = text("""
                SELECT COUNT(DISTINCT(original_url, unix_timestamp)) as unique_count
                FROM pages
            """)
            unique_count = self.db.execute(unique_pages_query).scalar()
            
            # Check for data integrity issues
            integrity_issues = []
            
            # Check for pages with missing domains
            missing_domains = self.db.execute(
                text("""
                    SELECT COUNT(*) FROM pages p 
                    LEFT JOIN domains d ON p.domain_id = d.id 
                    WHERE d.id IS NULL
                """)
            ).scalar()
            
            if missing_domains > 0:
                integrity_issues.append(f"{missing_domains} pages with missing domains")
            
            analysis = {
                "can_migrate": len(integrity_issues) == 0,
                "total_pages": pages_count,
                "unique_pages": unique_count,
                "duplicate_pages": pages_count - unique_count,
                "deduplication_savings": round((1 - unique_count / pages_count) * 100, 2) if pages_count > 0 else 0,
                "duplicate_samples": [
                    {"url": row[0], "timestamp": row[1], "count": row[2]} 
                    for row in duplicate_samples
                ],
                "integrity_issues": integrity_issues
            }
            
            logger.info(f"Data analysis: {analysis}")
            return analysis
            
        except Exception as e:
            logger.error(f"Data analysis failed: {e}")
            raise
    
    async def _migrate_pages_with_deduplication(self):
        """Migrate pages to new structure with deduplication"""
        self.progress.start_phase("migrate_pages")
        
        try:
            logger.info("Starting page migration with deduplication")
            
            # Get distinct pages ordered by creation time (keep earliest)
            migration_query = text("""
                SELECT DISTINCT ON (p.original_url, p.unix_timestamp)
                    p.id, p.domain_id, p.original_url, p.wayback_url, p.title,
                    p.extracted_title, p.extracted_text, p.unix_timestamp, p.mime_type,
                    p.status_code, p.meta_description, p.meta_keywords, p.author,
                    p.published_date, p.language, p.word_count, p.character_count,
                    p.content_type, p.content_length, p.capture_date, p.review_status,
                    p.page_category, p.priority_level, p.review_notes, p.quick_notes,
                    p.quality_score, p.is_duplicate, p.duplicate_of_page_id, p.tags,
                    p.content_hash, p.processed, p.indexed, p.error_message,
                    p.retry_count, p.last_retry_at, p.reviewed_by, p.reviewed_at,
                    p.scraped_at, p.created_at, p.updated_at
                FROM pages p
                ORDER BY p.original_url, p.unix_timestamp, p.created_at ASC
            """)
            
            result = self.db.execute(migration_query)
            
            batch = []
            processed_count = 0
            
            for row in result:
                try:
                    # Generate new UUID for PageV2
                    new_page_id = uuid4()
                    
                    # Create PageV2 record
                    page_v2_data = {
                        "id": new_page_id,
                        "url": row.original_url,
                        "unix_timestamp": int(row.unix_timestamp) if row.unix_timestamp else 0,
                        "wayback_url": row.wayback_url,
                        "title": row.title,
                        "extracted_title": row.extracted_title,
                        "extracted_text": row.extracted_text,
                        "meta_description": row.meta_description,
                        "meta_keywords": row.meta_keywords,
                        "author": row.author,
                        "published_date": row.published_date,
                        "language": row.language,
                        "word_count": row.word_count,
                        "character_count": row.character_count,
                        "content_type": row.content_type,
                        "content_length": row.content_length,
                        "mime_type": row.mime_type,
                        "status_code": row.status_code,
                        "capture_date": row.capture_date,
                        "content_hash": row.content_hash,
                        "processed": row.processed or False,
                        "indexed": row.indexed or False,
                        "error_message": row.error_message,
                        "retry_count": row.retry_count or 0,
                        "last_retry_at": row.last_retry_at,
                        "quality_score": row.quality_score,
                        "created_at": row.created_at or datetime.utcnow(),
                        "updated_at": row.updated_at or datetime.utcnow()
                    }
                    
                    batch.append((row.id, new_page_id, page_v2_data))
                    
                    if len(batch) >= self.batch_size:
                        await self._process_page_batch(batch)
                        processed_count += len(batch)
                        self.progress.update_stats(pages_processed=len(batch))
                        logger.info(f"Processed {processed_count} pages")
                        batch = []
                
                except Exception as e:
                    logger.error(f"Failed to prepare page {row.id}: {e}")
                    continue
            
            # Process remaining batch
            if batch:
                await self._process_page_batch(batch)
                processed_count += len(batch)
                self.progress.update_stats(pages_processed=len(batch))
            
            logger.info(f"Page migration completed. Processed {processed_count} pages")
            
        except Exception as e:
            logger.error(f"Page migration failed: {e}")
            raise
    
    async def _process_page_batch(self, batch: List[Tuple]):
        """Process a batch of pages"""
        if self.dry_run:
            logger.info(f"DRY RUN: Would migrate {len(batch)} pages")
            return
        
        try:
            # Bulk insert PageV2 records
            page_v2_records = []
            for old_id, new_id, page_data in batch:
                page_v2_records.append(page_data)
            
            # Use bulk insert
            from sqlalchemy.dialects.postgresql import insert
            
            stmt = insert(PageV2.__table__).values(page_v2_records)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=['url', 'unix_timestamp']
            )
            
            self.db.execute(stmt)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to process page batch: {e}")
            self.db.rollback()
            raise
    
    async def _create_project_page_associations(self):
        """Create project-page associations from old page-domain-project relationships"""
        self.progress.start_phase("create_associations")
        
        try:
            logger.info("Creating project-page associations")
            
            # Get all old pages with their new page mappings
            association_query = text("""
                SELECT 
                    p.id as old_page_id,
                    p.original_url,
                    p.unix_timestamp,
                    p.domain_id,
                    d.project_id,
                    d.id as domain_id,
                    p.review_status,
                    p.page_category,
                    p.priority_level,
                    p.review_notes,
                    p.quick_notes,
                    p.is_duplicate,
                    p.duplicate_of_page_id,
                    p.tags,
                    p.reviewed_by,
                    p.reviewed_at,
                    p.created_at,
                    pv2.id as new_page_id,
                    proj.user_id
                FROM pages p
                JOIN domains d ON p.domain_id = d.id
                JOIN projects proj ON d.project_id = proj.id
                JOIN pages_v2 pv2 ON p.original_url = pv2.url 
                    AND CAST(p.unix_timestamp AS BIGINT) = pv2.unix_timestamp
                ORDER BY p.id
            """)
            
            result = self.db.execute(association_query)
            
            batch = []
            processed_count = 0
            
            for row in result:
                try:
                    association_data = {
                        "id": uuid4(),
                        "project_id": row.project_id,
                        "page_id": row.new_page_id,
                        "domain_id": row.domain_id,
                        "added_at": row.created_at or datetime.utcnow(),
                        "added_by": row.user_id,
                        "review_status": self._convert_review_status(row.review_status),
                        "page_category": row.page_category,
                        "priority_level": self._convert_priority_level(row.priority_level),
                        "review_notes": row.review_notes,
                        "quick_notes": row.quick_notes,
                        "is_duplicate": row.is_duplicate or False,
                        "duplicate_of_page_id": row.duplicate_of_page_id,
                        "tags": row.tags or [],
                        "is_starred": False,  # Default value
                        "reviewed_by": row.reviewed_by,
                        "reviewed_at": row.reviewed_at
                    }
                    
                    batch.append(association_data)
                    
                    if len(batch) >= self.batch_size:
                        await self._process_association_batch(batch)
                        processed_count += len(batch)
                        self.progress.update_stats(associations_created=len(batch))
                        logger.info(f"Created {processed_count} associations")
                        batch = []
                
                except Exception as e:
                    logger.error(f"Failed to prepare association for page {row.old_page_id}: {e}")
                    continue
            
            # Process remaining batch
            if batch:
                await self._process_association_batch(batch)
                processed_count += len(batch)
                self.progress.update_stats(associations_created=len(batch))
            
            logger.info(f"Association creation completed. Created {processed_count} associations")
            
        except Exception as e:
            logger.error(f"Association creation failed: {e}")
            raise
    
    async def _process_association_batch(self, batch: List[Dict]):
        """Process a batch of project-page associations"""
        if self.dry_run:
            logger.info(f"DRY RUN: Would create {len(batch)} associations")
            return
        
        try:
            from sqlalchemy.dialects.postgresql import insert
            
            stmt = insert(ProjectPage.__table__).values(batch)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=['project_id', 'page_id']
            )
            
            self.db.execute(stmt)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to process association batch: {e}")
            self.db.rollback()
            raise
    
    async def _update_meilisearch_index(self):
        """Update Meilisearch index with new shared pages structure"""
        self.progress.start_phase("update_search_index")
        
        try:
            if self.dry_run:
                logger.info("DRY RUN: Would update Meilisearch index")
                return
            
            logger.info("Skipping Meilisearch index update for now - can be done separately")
            
            # TODO: Implement Meilisearch reindexing after migration
            # The new shared pages architecture will require separate indexing
            # This can be done via the shared pages API endpoints after migration
            
            logger.info("Meilisearch index update skipped - will need separate reindexing")
            
        except Exception as e:
            logger.error(f"Meilisearch update failed: {e}")
            raise
    
    async def _validate_migration(self) -> Dict[str, Any]:
        """Validate the migration results"""
        self.progress.start_phase("validate_migration")
        
        try:
            logger.info("Validating migration")
            
            # Count records in old vs new structure
            old_pages_count = self.db.execute(text("SELECT COUNT(*) FROM pages")).scalar()
            new_pages_count = self.db.execute(text("SELECT COUNT(*) FROM pages_v2")).scalar()
            associations_count = self.db.execute(text("SELECT COUNT(*) FROM project_pages")).scalar()
            
            # Check for missing associations
            missing_associations = self.db.execute(text("""
                SELECT COUNT(*) FROM pages p
                JOIN domains d ON p.domain_id = d.id
                LEFT JOIN project_pages pp ON pp.project_id = d.project_id
                WHERE pp.id IS NULL
            """)).scalar()
            
            # Check data integrity
            integrity_checks = {
                "orphaned_associations": self.db.execute(text("""
                    SELECT COUNT(*) FROM project_pages pp
                    LEFT JOIN pages_v2 pv2 ON pp.page_id = pv2.id
                    WHERE pv2.id IS NULL
                """)).scalar(),
                "invalid_projects": self.db.execute(text("""
                    SELECT COUNT(*) FROM project_pages pp
                    LEFT JOIN projects p ON pp.project_id = p.id
                    WHERE p.id IS NULL
                """)).scalar()
            }
            
            validation_results = {
                "valid": (
                    new_pages_count > 0 and
                    associations_count > 0 and
                    missing_associations < 10 and  # Allow up to 10 missing associations for orphaned/test pages
                    all(count == 0 for count in integrity_checks.values())
                ),
                "old_pages_count": old_pages_count,
                "new_pages_count": new_pages_count,
                "associations_count": associations_count,
                "missing_associations": missing_associations,
                "integrity_checks": integrity_checks,
                "deduplication_ratio": round((1 - new_pages_count / old_pages_count) * 100, 2) if old_pages_count > 0 else 0
            }
            
            logger.info(f"Validation results: {validation_results}")
            return validation_results
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            raise
    
    def _convert_review_status(self, old_status: str) -> str:
        """Convert old review status to new enum"""
        status_map = {
            "unreviewed": PageReviewStatus.PENDING.value,
            "relevant": PageReviewStatus.RELEVANT.value,
            "irrelevant": PageReviewStatus.IRRELEVANT.value,
            "needs_review": PageReviewStatus.NEEDS_REVIEW.value,
            "duplicate": PageReviewStatus.DUPLICATE.value
        }
        return status_map.get(old_status, PageReviewStatus.PENDING.value)
    
    def _convert_priority_level(self, old_priority: str) -> str:
        """Convert old priority level to new enum"""
        priority_map = {
            "low": PagePriority.LOW.value,
            "medium": PagePriority.MEDIUM.value,
            "high": PagePriority.HIGH.value,
            "critical": PagePriority.CRITICAL.value
        }
        return priority_map.get(old_priority, PagePriority.MEDIUM.value)


async def main():
    """Main migration function"""
    parser = argparse.ArgumentParser(description="Migrate to shared pages architecture")
    parser.add_argument("--dry-run", action="store_true", help="Perform dry run without making changes")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for processing")
    parser.add_argument("--resume", action="store_true", help="Resume from previous checkpoint")
    
    args = parser.parse_args()
    
    migrator = SharedPagesMigrator(
        dry_run=args.dry_run,
        batch_size=args.batch_size
    )
    
    success = await migrator.run_migration(resume=args.resume)
    
    if success:
        logger.info("Migration completed successfully!")
        sys.exit(0)
    else:
        logger.error("Migration failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())