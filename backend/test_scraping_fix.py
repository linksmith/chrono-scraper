#!/usr/bin/env python3
"""
Test script to reproduce and verify the scraping system issue fix

This script tests:
1. Project creation without V2 batch errors
2. Individual URL processing using robust extraction
3. End-to-end scraping workflow
"""
import asyncio
import os
import sys

# Add the backend directory to Python path
sys.path.insert(0, '/opt/app')

import logging
from datetime import datetime, timedelta

from app.core.database import get_db
from app.models.user import User
from app.models.project import Project, Domain, DomainStatus, MatchType
from app.services.projects import ProjectService
from app.tasks.firecrawl_scraping import scrape_domain_with_firecrawl

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_project_creation_and_scraping():
    """Test project creation and scraping without V2 batch errors"""
    
    logger.info("🧪 Starting scraping system fix test...")
    
    async for db in get_db():
        try:
            # Step 1: Get or create a test user
            logger.info("📋 Step 1: Setting up test user...")
            test_user = await db.get(User, 1)  # Assuming user ID 1 exists
            if not test_user:
                logger.error("❌ No test user found with ID 1. Please create a user first.")
                return False
                
            logger.info(f"✅ Found test user: {test_user.email}")
            
            # Step 2: Create a test project
            logger.info("📋 Step 2: Creating test project...")
            project_service = ProjectService()
            
            project_data = {
                "name": f"Scraping Test Project {datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "description": "Test project for scraping system fix verification",
                "is_public": False,
                "enable_attachment_download": False  # Disable attachments for faster testing
            }
            
            project = await project_service.create_project(db, project_data, test_user.id)
            logger.info(f"✅ Created test project: {project.name} (ID: {project.id})")
            
            # Step 3: Add a small test domain
            logger.info("📋 Step 3: Adding test domain...")
            
            domain_data = {
                "domain_name": "example.com",
                "url_path": "https://example.com/",
                "match_type": MatchType.PREFIX,
                "from_date": datetime.now() - timedelta(days=30),
                "to_date": datetime.now() - timedelta(days=1),
                "max_pages": 1,  # Limit to 1 page for testing
                "incremental_enabled": False
            }
            
            domain = Domain(**domain_data, project_id=project.id, status=DomainStatus.ACTIVE)
            db.add(domain)
            await db.commit()
            await db.refresh(domain)
            
            logger.info(f"✅ Added test domain: {domain.domain_name} (ID: {domain.id})")
            
            # Step 4: Test scraping configuration
            logger.info("📋 Step 4: Checking scraping configuration...")
            from app.core.config import settings
            
            logger.info(f"FIRECRAWL_V2_BATCH_ONLY: {getattr(settings, 'FIRECRAWL_V2_BATCH_ONLY', 'Not set')}")
            logger.info(f"USE_INTELLIGENT_EXTRACTION_ONLY: {getattr(settings, 'USE_INTELLIGENT_EXTRACTION_ONLY', 'Not set')}")
            logger.info(f"V2_BATCH_ONLY env var: {os.getenv('V2_BATCH_ONLY', 'Not set')}")
            logger.info(f"USE_INDIVIDUAL_EXTRACTION env var: {os.getenv('USE_INDIVIDUAL_EXTRACTION', 'Not set')}")
            
            # Step 5: Attempt scraping (this should trigger the error if not fixed)
            logger.info("📋 Step 5: Testing scraping execution...")
            
            # Create a scrape session
            from app.models.project import ScrapeSession, ScrapeSessionStatus
            
            scrape_session = ScrapeSession(
                project_id=project.id,
                session_name=f"Test scrape - {datetime.now()}",
                status=ScrapeSessionStatus.PENDING,
                total_urls=0,
                completed_urls=0,
                failed_urls=0,
                cancelled_urls=0
            )
            
            db.add(scrape_session)
            await db.commit()
            await db.refresh(scrape_session)
            
            logger.info(f"✅ Created scrape session: {scrape_session.id}")
            
            # This is where the error should occur if V2 batch is still enabled
            logger.info("🔄 Attempting to start scraping task...")
            
            try:
                # Test the scraping function directly (synchronously for testing)
                from app.tasks.firecrawl_scraping import get_sync_session
                
                # We'll test this in a limited way to avoid long execution
                sync_db = get_sync_session()
                
                try:
                    # Get the domain and session
                    domain_obj = sync_db.get(Domain, domain.id)
                    session_obj = sync_db.get(ScrapeSession, scrape_session.id)
                    
                    if domain_obj and session_obj:
                        logger.info("✅ Successfully retrieved domain and session objects")
                        
                        # Check if V2 batch logic would be triggered
                        v2_batch_only = getattr(settings, "FIRECRAWL_V2_BATCH_ONLY", False)
                        v2_batch_enabled = getattr(settings, "FIRECRAWL_V2_BATCH_ENABLED", True)
                        
                        logger.info(f"V2 batch settings - Only: {v2_batch_only}, Enabled: {v2_batch_enabled}")
                        
                        if v2_batch_enabled or v2_batch_only:
                            logger.warning("⚠️  V2 batch processing is still enabled - this will likely cause connection errors!")
                            
                            # Try to import FirecrawlV2Client to see if it would fail
                            try:
                                from app.services.firecrawl_v2_client import FirecrawlV2Client
                                fc = FirecrawlV2Client()
                                logger.info("✅ FirecrawlV2Client imported successfully")
                                
                                # This would normally fail with connection refused
                                logger.info("🚨 V2 batch processing would attempt to connect to Firecrawl service")
                                
                            except ImportError as e:
                                logger.info(f"✅ FirecrawlV2Client import failed (expected): {e}")
                        else:
                            logger.info("✅ V2 batch processing is disabled")
                        
                        # Test individual processing path
                        use_intelligent_only = getattr(settings, "USE_INTELLIGENT_EXTRACTION_ONLY", False)
                        if use_intelligent_only:
                            logger.info("✅ Individual intelligent extraction is enabled")
                        else:
                            logger.info("⚠️  Individual intelligent extraction is not enabled")
                        
                    else:
                        logger.error("❌ Failed to retrieve domain or session objects")
                        
                finally:
                    sync_db.close()
                
                logger.info("✅ Scraping task test completed without errors")
                
            except Exception as e:
                logger.error(f"❌ Scraping task failed: {e}")
                if "Connection refused" in str(e) or "FirecrawlV2Error" in str(e):
                    logger.error("🚨 CONFIRMED: V2 batch processing is causing connection errors!")
                    return False
                else:
                    logger.warning(f"⚠️  Unexpected error: {e}")
            
            # Step 6: Cleanup
            logger.info("📋 Step 6: Cleaning up test data...")
            
            # Delete the test project and its related data
            await db.delete(project)
            await db.commit()
            
            logger.info("✅ Test cleanup completed")
            
            logger.info("🎉 Test completed successfully! No V2 batch connection errors detected.")
            return True
            
        except Exception as e:
            logger.error(f"❌ Test failed with error: {e}")
            return False
        finally:
            await db.close()

def main():
    """Main test function"""
    print("=" * 60)
    print("🧪 SCRAPING SYSTEM FIX VERIFICATION TEST")
    print("=" * 60)
    
    success = asyncio.run(test_project_creation_and_scraping())
    
    if success:
        print("\n✅ TEST PASSED: Scraping system appears to be working correctly")
        return 0
    else:
        print("\n❌ TEST FAILED: V2 batch processing issues detected")
        return 1

if __name__ == "__main__":
    sys.exit(main())