#!/usr/bin/env python3
"""
Reindex all projects with optimized document structure

This script will:
1. Reindex all project indexes with the new optimized document structure
2. Apply optimized index configuration
3. Report statistics and performance metrics

Usage:
    python scripts/reindex_optimized.py
    python scripts/reindex_optimized.py --project-id 123
    python scripts/reindex_optimized.py --configure-only
"""

import asyncio
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Add the backend directory to the path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.database import get_db
from app.core.config import settings
from app.models.project import Project
from app.services.meilisearch_service import MeilisearchService
from sqlalchemy import select

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def configure_project_index(ms: MeilisearchService, project: Project) -> dict:
    """Configure a single project index with optimized settings"""
    index_name = f"project_{project.id}"
    
    try:
        # Apply optimized configuration
        config_result = await ms.configure_optimized_index(index_name)
        logger.info(f"✅ Configured index for project {project.id} ({project.name})")
        return {"project_id": project.id, "status": "configured", "result": config_result}
    except Exception as e:
        logger.error(f"❌ Failed to configure index for project {project.id}: {str(e)}")
        return {"project_id": project.id, "status": "error", "error": str(e)}


async def reindex_project(ms: MeilisearchService, project: Project, batch_size: int = 1000) -> dict:
    """Reindex a single project with optimized document structure"""
    index_name = f"project_{project.id}"
    
    logger.info(f"🔄 Starting reindex for project {project.id} ({project.name})")
    start_time = datetime.utcnow()
    
    try:
        # Configure index first
        await ms.configure_optimized_index(index_name)
        
        # Reindex with optimization
        reindex_result = await ms.reindex_with_optimization(index_name, batch_size)
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"✅ Completed reindex for project {project.id} in {duration:.1f}s")
        logger.info(f"   📊 Pages: {reindex_result['indexed_pages']}/{reindex_result['total_pages']}")
        logger.info(f"   📦 Batches: {reindex_result['batches_processed']}")
        
        return {
            "project_id": project.id,
            "project_name": project.name,
            "status": "completed",
            "duration_seconds": duration,
            "result": reindex_result
        }
        
    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.error(f"❌ Failed to reindex project {project.id} after {duration:.1f}s: {str(e)}")
        return {
            "project_id": project.id,
            "project_name": project.name,
            "status": "error",
            "duration_seconds": duration,
            "error": str(e)
        }


async def main():
    """Main reindexing function"""
    parser = argparse.ArgumentParser(description='Reindex Meilisearch with optimized structure')
    parser.add_argument('--project-id', type=int, help='Reindex specific project only')
    parser.add_argument('--configure-only', action='store_true', help='Only apply configuration, no reindexing')
    parser.add_argument('--batch-size', type=int, default=1000, help='Batch size for reindexing')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without doing it')
    
    args = parser.parse_args()
    
    logger.info("🚀 Starting Meilisearch optimization")
    logger.info(f"   Settings: {settings.MEILISEARCH_HOST}")
    
    if args.dry_run:
        logger.info("   🧪 DRY RUN MODE - No actual changes will be made")
    
    overall_stats = {
        'start_time': datetime.utcnow(),
        'projects_processed': 0,
        'projects_successful': 0,
        'projects_failed': 0,
        'total_pages_indexed': 0,
        'errors': []
    }
    
    try:
        # Get database session
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            # Get projects to process
            if args.project_id:
                # Single project
                project_query = select(Project).where(Project.id == args.project_id)
                result = await db.execute(project_query)
                projects = [result.scalar_one_or_none()]
                
                if not projects[0]:
                    logger.error(f"❌ Project with ID {args.project_id} not found")
                    return
                    
                logger.info(f"📋 Processing single project: {projects[0].name}")
            else:
                # All projects
                project_query = select(Project)
                result = await db.execute(project_query)
                projects = list(result.scalars().all())
                logger.info(f"📋 Processing {len(projects)} projects")
            
            if args.dry_run:
                logger.info("   Projects to process:")
                for project in projects:
                    logger.info(f"     - {project.id}: {project.name}")
                return
            
            # Initialize Meilisearch service
            ms = MeilisearchService()
            await ms.connect()
            
            try:
                # Process each project
                for project in projects:
                    overall_stats['projects_processed'] += 1
                    
                    if args.configure_only:
                        # Only apply configuration
                        result = await configure_project_index(ms, project)
                    else:
                        # Full reindex
                        result = await reindex_project(ms, project, args.batch_size)
                        
                        if result['status'] == 'completed':
                            overall_stats['total_pages_indexed'] += result['result']['indexed_pages']
                    
                    if result['status'] == 'completed' or result['status'] == 'configured':
                        overall_stats['projects_successful'] += 1
                    else:
                        overall_stats['projects_failed'] += 1
                        overall_stats['errors'].append(result)
            
            finally:
                await ms.disconnect()
    
    except Exception as e:
        logger.error(f"❌ Fatal error: {str(e)}")
        overall_stats['errors'].append({"fatal_error": str(e)})
    
    finally:
        # Final statistics
        overall_stats['end_time'] = datetime.utcnow()
        overall_stats['total_duration_seconds'] = (
            overall_stats['end_time'] - overall_stats['start_time']
        ).total_seconds()
        
        logger.info("📊 OPTIMIZATION COMPLETE")
        logger.info(f"   ⏱️  Duration: {overall_stats['total_duration_seconds']:.1f}s")
        logger.info(f"   📦 Projects: {overall_stats['projects_successful']}/{overall_stats['projects_processed']} successful")
        
        if not args.configure_only:
            logger.info(f"   📄 Pages indexed: {overall_stats['total_pages_indexed']:,}")
        
        if overall_stats['projects_failed'] > 0:
            logger.warning(f"   ⚠️  Failed projects: {overall_stats['projects_failed']}")
            
        if overall_stats['errors']:
            logger.error("   ❌ Errors encountered:")
            for error in overall_stats['errors']:
                if 'project_id' in error:
                    logger.error(f"     Project {error['project_id']}: {error.get('error', 'Unknown error')}")
                else:
                    logger.error(f"     {error}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {str(e)}")
        sys.exit(1)