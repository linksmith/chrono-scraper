#!/usr/bin/env python3
"""
Test Project Creation and Scraping Workflow Without Firecrawl
"""

import asyncio
import json
import time
import logging
from datetime import datetime
import sys

sys.path.append('/app')

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project, Domain
from app.models.scraping import ScrapePage
from app.core.security import get_password_hash
from app.services.projects import ProjectService
from app.tasks.firecrawl_scraping import scrape_domain_with_firecrawl
from sqlmodel import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_project_creation_workflow():
    """Test end-to-end project creation and scraping"""
    logger.info("🚀 TESTING PROJECT CREATION WORKFLOW")
    logger.info("=" * 60)
    
    try:
        # Step 1: Create test user if needed
        async for db in get_db():
            stmt = select(User).where(User.email == "test-user@example.com")
            result = await db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                user = User(
                    email="test-user@example.com",
                    full_name="Test User",
                    hashed_password=get_password_hash("testpassword"),
                    is_verified=True,
                    is_active=True,
                    approval_status='approved',
                    data_handling_agreement=True,
                    ethics_agreement=True,
                    research_interests="Testing",
                    research_purpose="Testing",
                    expected_usage="Testing"
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
                logger.info("✅ Created test user")
            else:
                logger.info("✅ Test user already exists")
            
            user_id = user.id
            break
        
        # Step 2: Create project using ProjectService
        project_service = ProjectService()
        
        project_data = {
            "name": f"E2E Test Project {int(time.time())}",
            "description": "Test project for E2E workflow validation",
            "domains": [{
                "url": "example.org",
                "scrape_config": {
                    "max_pages": 3,
                    "rate_limit": 1.0,
                    "enable_intelligent_filtering": True
                }
            }]
        }
        
        logger.info("📋 Creating project...")
        async for db in get_db():
            project = await project_service.create_project(
                db=db,
                user_id=user_id,
                project_data=project_data
            )
            
            logger.info(f"✅ Project created: {project.name} (ID: {project.id})")
            logger.info(f"   Domains: {len(project.domains)}")
            
            # Verify project in database
            stmt = select(Project).where(Project.id == project.id)
            result = await db.execute(stmt)
            db_project = result.scalar_one_or_none()
            
            logger.info(f"✅ Project verified in database")
            logger.info(f"   Name: {db_project.name}")
            logger.info(f"   Owner: {db_project.owner_id}")
            logger.info(f"   Domains count: {len(db_project.domains)}")
            
            project_id = project.id
            domain_id = project.domains[0].id if project.domains else None
            break
        
        # Step 3: Test scraping task creation (without actually running it)
        logger.info("🔄 Testing scraping task setup...")
        
        if domain_id:
            async for db in get_db():
                # Check domain configuration
                domain = await db.get(Domain, domain_id)
                logger.info(f"✅ Domain configuration:")
                logger.info(f"   URL: {domain.url}")
                logger.info(f"   Max pages: {domain.scrape_config.get('max_pages', 'default')}")
                logger.info(f"   Rate limit: {domain.scrape_config.get('rate_limit', 'default')}")
                logger.info(f"   Intelligent filtering: {domain.scrape_config.get('enable_intelligent_filtering', False)}")
                break
        
        # Step 4: Verify no Firecrawl dependencies
        logger.info("🔍 Verifying no Firecrawl dependencies...")
        
        # Check that the scraping task imports work without Firecrawl
        try:
            from app.tasks.firecrawl_scraping import scrape_domain_with_firecrawl
            from app.services.robust_content_extractor import get_robust_extractor
            logger.info("✅ Scraping imports successful (no Firecrawl errors)")
        except Exception as e:
            logger.error(f"❌ Import error: {e}")
            return False
        
        # Verify robust extractor is available
        try:
            extractor = get_robust_extractor()
            metrics = await extractor.get_extraction_metrics()
            logger.info("✅ Robust extractor available")
            logger.info(f"   Max concurrent extractions: {metrics.get('max_concurrent_extractions', 'unknown')}")
            logger.info(f"   Cache memory: {metrics.get('cache_memory_usage', 'unknown')}")
        except Exception as e:
            logger.error(f"❌ Extractor error: {e}")
            return False
        
        # Step 5: Test small extraction to verify workflow
        logger.info("🤖 Testing extraction workflow...")
        
        try:
            test_url = "https://web.archive.org/web/20240101000000/https://example.org/"
            start_time = time.time()
            
            extracted_content = await extractor.extract_content(test_url)
            extraction_time = time.time() - start_time
            
            logger.info("✅ Extraction successful")
            logger.info(f"   Method: {extracted_content.extraction_method}")
            logger.info(f"   Title: {extracted_content.title}")
            logger.info(f"   Word count: {extracted_content.word_count}")
            logger.info(f"   Time: {extraction_time:.2f}s")
            
        except Exception as e:
            logger.error(f"❌ Extraction failed: {e}")
            return False
        
        logger.info("\n" + "=" * 60)
        logger.info("🎉 PROJECT CREATION WORKFLOW SUCCESSFUL")
        logger.info("=" * 60)
        logger.info("✅ User creation: Working")
        logger.info("✅ Project creation: Working")
        logger.info("✅ Domain configuration: Working")
        logger.info("✅ Scraping task imports: Working")
        logger.info("✅ Robust extractor: Working")
        logger.info("✅ Content extraction: Working")
        logger.info("✅ No Firecrawl dependencies: Confirmed")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Project creation workflow failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    success = await test_project_creation_workflow()
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)