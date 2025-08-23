#!/usr/bin/env python3
"""
Test script to verify scraping trigger works correctly
"""

import asyncio
import logging
from sqlmodel import select
from app.core.database import get_db
from app.models.project import Project, Domain, ScrapeSession
from app.services.projects import ProjectService
from app.services.domains import DomainService
from app.services.scrape_session import ScrapeSessionService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_scraping_trigger():
    """Test if scraping can be triggered properly"""
    
    async for db in get_db():
        # Get the most recent project with a domain
        project_result = await db.execute(
            select(Project).order_by(Project.created_at.desc()).limit(1)
        )
        project = project_result.scalar_one_or_none()
        
        if not project:
            logger.error("No projects found in database")
            return
            
        logger.info(f"Testing with project: {project.name} (ID: {project.id})")
        
        # Get domains for this project
        domains_result = await db.execute(
            select(Domain).where(Domain.project_id == project.id)
        )
        domains = domains_result.scalars().all()
        
        logger.info(f"Found {len(domains)} domains for project")
        for d in domains:
            logger.info(f"  - {d.domain_name} (type: {d.match_type}, active: {d.active})")
        
        if not domains:
            logger.error("No domains found for project")
            return
            
        # Create a new scrape session
        session = await ScrapeSessionService.create_scrape_session(
            db, project.id, project.user_id
        )
        
        logger.info(f"Created scrape session: {session.id}")
        
        # Try to trigger scraping directly
        from app.tasks.firecrawl_scraping import scrape_domain_with_firecrawl
        
        tasks_queued = 0
        for domain in domains:
            if domain.active and domain.status == "active":
                try:
                    # Queue the task
                    task = scrape_domain_with_firecrawl.delay(domain.id, session.id)
                    logger.info(f"Queued task for domain {domain.id}: Task ID {task.id}")
                    tasks_queued += 1
                except Exception as e:
                    logger.error(f"Failed to queue task for domain {domain.id}: {e}")
        
        logger.info(f"Successfully queued {tasks_queued} tasks")
        
        # Check if tasks are in Redis
        import redis
        r = redis.Redis(host='redis', port=6379, db=0)
        queue_length = r.llen('celery')
        logger.info(f"Redis queue length: {queue_length}")
        
        break


if __name__ == "__main__":
    asyncio.run(test_scraping_trigger())