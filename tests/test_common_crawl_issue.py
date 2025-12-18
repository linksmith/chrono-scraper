#!/usr/bin/env python3
"""
Test script to reproduce and diagnose Common Crawl project issues.

This script creates a Common Crawl project and attempts to trigger scraping
to identify what's not working.
"""
import asyncio
import logging
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from sqlmodel import Session, select
from app.core.database import SyncSessionLocal
from app.models.project import Project, Domain, ArchiveSource
from app.models.user import User
from app.services.archive_service_router import query_archive_unified, create_routing_config_from_project

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_user(db: Session) -> User:
    """Create or get test user"""
    stmt = select(User).where(User.email == "test@commoncrawl.com")
    user = db.exec(stmt).first()
    
    if not user:
        from app.core.security import get_password_hash
        user = User(
            email="test@commoncrawl.com",
            full_name="Common Crawl Test User",
            hashed_password=get_password_hash("testpassword"),
            is_verified=True,
            is_active=True,
            approval_status="approved"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Created test user: {user.email}")
    else:
        logger.info(f"Using existing test user: {user.email}")
    
    return user

def create_common_crawl_project(db: Session, user: User) -> Project:
    """Create a test project with Common Crawl archive source"""
    project = Project(
        name="Common Crawl Test Project",
        description="Test project for Common Crawl debugging",
        user_id=user.id,
        archive_source=ArchiveSource.COMMON_CRAWL,
        fallback_enabled=False,  # Disable fallback to force Common Crawl only
        process_documents=True
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    
    logger.info(f"Created Common Crawl project: {project.name} (ID: {project.id})")
    logger.info(f"Archive source: {project.archive_source}")
    logger.info(f"Fallback enabled: {project.fallback_enabled}")
    
    return project

def create_test_domain(db: Session, project: Project) -> Domain:
    """Create a test domain for the project"""
    domain = Domain(
        project_id=project.id,
        domain_name="example.com",
        match_type="domain",
        from_date=datetime.strptime("2024-01-01", "%Y-%m-%d"),
        to_date=datetime.strptime("2024-02-01", "%Y-%m-%d"),
        active=True
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)
    
    logger.info(f"Created test domain: {domain.domain_name} (ID: {domain.id})")
    
    return domain

async def test_common_crawl_archive_query(project: Project, domain: Domain):
    """Test the archive query directly"""
    logger.info("Testing Common Crawl archive query...")
    
    try:
        project_config = {
            'archive_source': project.archive_source.value,
            'fallback_enabled': project.fallback_enabled,
            'archive_config': project.archive_config or {}
        }
        
        logger.info(f"Project config: {project_config}")
        
        records, stats = await query_archive_unified(
            domain=domain.domain_name,
            from_date="20240101",
            to_date="20240201",
            project_config=project_config,
            match_type="domain"
        )
        
        logger.info(f"Archive query completed!")
        logger.info(f"Records found: {len(records)}")
        logger.info(f"Query stats: {stats}")
        
        return records, stats
        
    except Exception as e:
        logger.error(f"Archive query failed: {e}")
        logger.exception("Full traceback:")
        return None, None

async def test_scraping_task(project: Project, domain: Domain):
    """Test the actual scraping task"""
    logger.info("Testing scraping task...")
    
    try:
        from app.models.project import ScrapeSession, ScrapeSessionStatus
        from app.tasks.firecrawl_scraping import scrape_domain_with_intelligent_extraction
        
        # Create a scrape session
        db = SyncSessionLocal()
        scrape_session = ScrapeSession(
            project_id=project.id,
            status=ScrapeSessionStatus.PENDING,
            session_name="Common Crawl Test Session"
        )
        db.add(scrape_session)
        db.commit()
        db.refresh(scrape_session)
        
        logger.info(f"Created scrape session: {scrape_session.id}")
        
        # Trigger scraping task
        logger.info("Triggering scraping task...")
        result = scrape_domain_with_intelligent_extraction(
            domain_id=domain.id,
            scrape_session_id=scrape_session.id,
            incremental_mode=False
        )
        
        logger.info(f"Scraping task completed!")
        logger.info(f"Task result: {result}")
        
        return result
        
    except Exception as e:
        logger.error(f"Scraping task failed: {e}")
        logger.exception("Full traceback:")
        return None

async def main():
    """Main test function"""
    logger.info("=" * 60)
    logger.info("COMMON CRAWL PROJECT DEBUGGING TEST")
    logger.info("=" * 60)
    
    # Create database session
    db = SyncSessionLocal()
    
    try:
        # Step 1: Create test user
        logger.info("Step 1: Creating test user...")
        user = create_test_user(db)
        
        # Step 2: Create Common Crawl project
        logger.info("Step 2: Creating Common Crawl project...")
        project = create_common_crawl_project(db, user)
        
        # Step 3: Create test domain
        logger.info("Step 3: Creating test domain...")
        from datetime import datetime
        domain = create_test_domain(db, project)
        
        # Step 4: Test archive query directly
        logger.info("Step 4: Testing archive query...")
        records, stats = await test_common_crawl_archive_query(project, domain)
        
        if records is not None:
            logger.info("✓ Archive query successful!")
        else:
            logger.error("✗ Archive query failed!")
            
        # Step 5: Test scraping task
        logger.info("Step 5: Testing scraping task...")
        result = await test_scraping_task(project, domain)
        
        if result is not None:
            logger.info("✓ Scraping task completed!")
        else:
            logger.error("✗ Scraping task failed!")
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
        logger.exception("Full traceback:")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())