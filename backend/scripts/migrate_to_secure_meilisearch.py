#!/usr/bin/env python3
"""
Migration Script: Migrate Existing Projects to Secure Meilisearch Multi-Tenancy

This script migrates existing projects from the legacy single-master-key system
to the new secure multi-tenant architecture with dedicated project keys.

Usage:
    python scripts/migrate_to_secure_meilisearch.py [--dry-run] [--batch-size=50]

Features:
- Generates dedicated search keys for existing projects
- Creates audit records for all new keys
- Provides rollback capabilities
- Supports dry-run mode for testing
- Batch processing for large datasets
- Comprehensive error handling and logging
"""

import asyncio
import logging
import argparse
import sys
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add the backend directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from sqlmodel import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.project import Project, ProjectStatus
from app.models.meilisearch_audit import MeilisearchKey, MeilisearchKeyType, MeilisearchSecurityEvent
from app.services.meilisearch_key_manager import meilisearch_key_manager
from app.core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MeilisearchMigrationStats:
    """Track migration statistics"""
    
    def __init__(self):
        self.total_projects = 0
        self.migrated_projects = 0
        self.skipped_projects = 0
        self.failed_projects = 0
        self.errors = []
        self.start_time = datetime.utcnow()
        self.end_time = None
        
    def add_error(self, project_id: int, error: str):
        """Add an error to the stats"""
        self.errors.append({
            'project_id': project_id,
            'error': error,
            'timestamp': datetime.utcnow()
        })
        
    def complete(self):
        """Mark migration as complete"""
        self.end_time = datetime.utcnow()
        
    @property
    def duration_seconds(self) -> float:
        """Calculate migration duration"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
        
    def summary(self) -> Dict[str, Any]:
        """Get migration summary"""
        return {
            'total_projects': self.total_projects,
            'migrated_projects': self.migrated_projects,
            'skipped_projects': self.skipped_projects,
            'failed_projects': self.failed_projects,
            'success_rate': (self.migrated_projects / self.total_projects * 100) if self.total_projects > 0 else 0,
            'duration_seconds': self.duration_seconds,
            'errors': self.errors
        }


async def get_projects_without_keys(db: AsyncSession) -> List[Project]:
    """
    Get all projects that don't have dedicated search keys yet
    
    Args:
        db: Database session
        
    Returns:
        List of projects needing migration
    """
    query = select(Project).where(
        and_(
            Project.process_documents == True,  # Only projects with search indexing
            or_(
                Project.index_search_key.is_(None),
                Project.index_search_key == ""
            )
        )
    )
    
    result = await db.execute(query)
    return result.scalars().all()


async def migrate_single_project(
    db: AsyncSession, 
    project: Project, 
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Migrate a single project to secure keys
    
    Args:
        db: Database session
        project: Project to migrate
        dry_run: If True, don't actually create keys
        
    Returns:
        Dict with migration result
    """
    migration_result = {
        'project_id': project.id,
        'project_name': project.name,
        'success': False,
        'skipped': False,
        'error': None,
        'key_created': False
    }
    
    try:
        # Check if project already has a key (shouldn't happen based on query)
        if project.index_search_key:
            migration_result['skipped'] = True
            migration_result['success'] = True
            logger.info(f"Project {project.id} already has a search key, skipping")
            return migration_result
        
        # Check if project has a valid Meilisearch index
        index_name = f"project_{project.id}"
        logger.info(f"Migrating project {project.id}: {project.name}")
        
        if not dry_run:
            # Create dedicated search key
            key_data = await meilisearch_key_manager.create_project_key(project)
            
            # Update project with new key information
            project.index_search_key = key_data['key']
            project.index_search_key_uid = key_data['uid']
            project.key_created_at = datetime.utcnow()
            project.status = ProjectStatus.INDEXED
            
            # Create audit record
            audit_record = MeilisearchKey(
                project_id=project.id,
                key_uid=key_data['uid'],
                key_type=MeilisearchKeyType.PROJECT_OWNER,
                key_name=f"project_owner_{project.id}_migrated",
                key_description=f"Migrated owner search key for project: {project.name}",
                actions=["search", "documents.get"],
                indexes=[index_name]
            )
            db.add(audit_record)
            
            # Create security event
            security_event = MeilisearchSecurityEvent(
                key_id=audit_record.id,
                event_type="key_migration",
                severity="info",
                description=f"Project {project.id} migrated to secure multi-tenancy",
                automated=True,
                event_metadata={
                    "project_id": project.id,
                    "migration_date": datetime.utcnow().isoformat(),
                    "migration_script": "migrate_to_secure_meilisearch.py"
                }
            )
            db.add(security_event)
            
            await db.commit()
            migration_result['key_created'] = True
            
        migration_result['success'] = True
        logger.info(f"Successfully migrated project {project.id}")
        
    except Exception as e:
        migration_result['error'] = str(e)
        logger.error(f"Failed to migrate project {project.id}: {e}")
        if not dry_run:
            await db.rollback()
    
    return migration_result


async def migrate_existing_projects(
    batch_size: int = 50,
    dry_run: bool = False
) -> MeilisearchMigrationStats:
    """
    Main migration function
    
    Args:
        batch_size: Number of projects to process in each batch
        dry_run: If True, don't actually create keys
        
    Returns:
        Migration statistics
    """
    stats = MeilisearchMigrationStats()
    
    logger.info(f"Starting Meilisearch security migration (dry_run={dry_run})")
    
    try:
        async for db in get_db():
            # Get projects that need migration
            projects_to_migrate = await get_projects_without_keys(db)
            stats.total_projects = len(projects_to_migrate)
            
            logger.info(f"Found {stats.total_projects} projects requiring migration")
            
            if stats.total_projects == 0:
                logger.info("No projects need migration")
                return stats
            
            # Process projects in batches
            for i in range(0, len(projects_to_migrate), batch_size):
                batch = projects_to_migrate[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(projects_to_migrate) + batch_size - 1) // batch_size
                
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} projects)")
                
                # Process each project in the batch
                for project in batch:
                    result = await migrate_single_project(db, project, dry_run)
                    
                    if result['success']:
                        if result['skipped']:
                            stats.skipped_projects += 1
                        else:
                            stats.migrated_projects += 1
                    else:
                        stats.failed_projects += 1
                        stats.add_error(result['project_id'], result['error'])
                
                # Log batch progress
                logger.info(
                    f"Batch {batch_num} complete. "
                    f"Migrated: {stats.migrated_projects}, "
                    f"Failed: {stats.failed_projects}, "
                    f"Skipped: {stats.skipped_projects}"
                )
            
            break  # Exit the async for loop
            
    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        stats.add_error(0, f"Global migration error: {str(e)}")
    
    finally:
        stats.complete()
    
    return stats


async def verify_migration() -> Dict[str, Any]:
    """
    Verify that all projects have proper key configuration
    
    Returns:
        Verification results
    """
    logger.info("Verifying migration results...")
    
    verification_result = {
        'total_projects': 0,
        'projects_with_keys': 0,
        'projects_without_keys': 0,
        'missing_projects': [],
        'invalid_keys': [],
        'verification_success': True
    }
    
    try:
        async for db in get_db():
            # Count all projects that should have keys
            all_projects_query = select(Project).where(Project.process_documents == True)
            all_projects_result = await db.execute(all_projects_query)
            all_projects = all_projects_result.scalars().all()
            
            verification_result['total_projects'] = len(all_projects)
            
            # Check each project
            for project in all_projects:
                if project.index_search_key and project.index_search_key_uid:
                    verification_result['projects_with_keys'] += 1
                    
                    # Verify key exists in Meilisearch
                    try:
                        key_status = await meilisearch_key_manager.get_key_status(project.index_search_key_uid)
                        if key_status.get('status') != 'active':
                            verification_result['invalid_keys'].append({
                                'project_id': project.id,
                                'key_uid': project.index_search_key_uid,
                                'status': key_status.get('status')
                            })
                    except Exception as e:
                        verification_result['invalid_keys'].append({
                            'project_id': project.id,
                            'key_uid': project.index_search_key_uid,
                            'error': str(e)
                        })
                else:
                    verification_result['projects_without_keys'] += 1
                    verification_result['missing_projects'].append({
                        'project_id': project.id,
                        'project_name': project.name
                    })
            
            break  # Exit the async for loop
            
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        verification_result['verification_success'] = False
        verification_result['error'] = str(e)
    
    # Determine overall success
    if verification_result['projects_without_keys'] > 0 or verification_result['invalid_keys']:
        verification_result['verification_success'] = False
    
    return verification_result


async def rollback_migration(project_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """
    Rollback migration for specified projects or all projects
    
    Args:
        project_ids: List of project IDs to rollback, or None for all
        
    Returns:
        Rollback results
    """
    logger.warning("Starting migration rollback...")
    
    rollback_result = {
        'projects_rolled_back': 0,
        'projects_failed': 0,
        'errors': []
    }
    
    try:
        async for db in get_db():
            # Build query for projects to rollback
            if project_ids:
                query = select(Project).where(
                    and_(
                        Project.id.in_(project_ids),
                        Project.index_search_key.isnot(None)
                    )
                )
            else:
                query = select(Project).where(Project.index_search_key.isnot(None))
            
            result = await db.execute(query)
            projects_to_rollback = result.scalars().all()
            
            logger.info(f"Rolling back {len(projects_to_rollback)} projects")
            
            for project in projects_to_rollback:
                try:
                    # Revoke the key in Meilisearch
                    if project.index_search_key_uid:
                        await meilisearch_key_manager.revoke_project_key(project)
                    
                    # Clear key information from project
                    project.index_search_key = None
                    project.index_search_key_uid = None
                    project.key_created_at = None
                    project.key_last_rotated = None
                    
                    # Mark audit records as revoked
                    audit_query = select(MeilisearchKey).where(
                        and_(
                            MeilisearchKey.project_id == project.id,
                            MeilisearchKey.is_active == True
                        )
                    )
                    audit_result = await db.execute(audit_query)
                    audit_records = audit_result.scalars().all()
                    
                    for audit_record in audit_records:
                        audit_record.is_active = False
                        audit_record.revoked_at = datetime.utcnow()
                        audit_record.revoked_reason = "Migration rollback"
                    
                    await db.commit()
                    rollback_result['projects_rolled_back'] += 1
                    
                    logger.info(f"Rolled back project {project.id}")
                    
                except Exception as e:
                    rollback_result['projects_failed'] += 1
                    rollback_result['errors'].append({
                        'project_id': project.id,
                        'error': str(e)
                    })
                    logger.error(f"Failed to rollback project {project.id}: {e}")
                    await db.rollback()
            
            break  # Exit the async for loop
            
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        rollback_result['errors'].append({'global_error': str(e)})
    
    return rollback_result


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Migrate existing projects to secure Meilisearch multi-tenancy"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without actually creating keys'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=50,
        help='Number of projects to process in each batch (default: 50)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify migration results, don\'t migrate'
    )
    parser.add_argument(
        '--rollback',
        action='store_true',
        help='Rollback migration (removes all project keys)'
    )
    parser.add_argument(
        '--rollback-projects',
        type=str,
        help='Comma-separated list of project IDs to rollback'
    )
    
    args = parser.parse_args()
    
    async def run_migration():
        if args.rollback:
            project_ids = None
            if args.rollback_projects:
                try:
                    project_ids = [int(x.strip()) for x in args.rollback_projects.split(',')]
                except ValueError:
                    logger.error("Invalid project IDs provided for rollback")
                    return
            
            result = await rollback_migration(project_ids)
            logger.info(f"Rollback completed: {result}")
            
        elif args.verify_only:
            result = await verify_migration()
            logger.info(f"Verification completed: {result}")
            
            if not result['verification_success']:
                logger.error("Verification failed!")
                sys.exit(1)
                
        else:
            # Run migration
            stats = await migrate_existing_projects(
                batch_size=args.batch_size,
                dry_run=args.dry_run
            )
            
            summary = stats.summary()
            logger.info(f"Migration completed: {summary}")
            
            # Verify results if not dry run
            if not args.dry_run and stats.failed_projects == 0:
                verification = await verify_migration()
                if verification['verification_success']:
                    logger.info("Migration verification successful!")
                else:
                    logger.error(f"Migration verification failed: {verification}")
                    sys.exit(1)
            
            # Exit with error code if any projects failed
            if stats.failed_projects > 0:
                logger.error(f"{stats.failed_projects} projects failed migration")
                sys.exit(1)
    
    # Run the migration
    asyncio.run(run_migration())


if __name__ == "__main__":
    main()