#!/usr/bin/env python3
"""
Debug script to simulate the exact frontend project creation flow and identify issues.

This script replicates what the frontend MultiStepProjectForm does:
1. Create project via POST /api/v1/projects  
2. Create domains via POST /api/v1/projects/{id}/domains
3. Auto-start scraping via POST /api/v1/projects/{id}/scrape

This helps identify exactly where the flow is failing.
"""
import asyncio
import logging
import sys
import json
from datetime import datetime
from typing import Dict, Any

# Add the backend directory to the path
sys.path.append('/home/bizon/Development/chrono-scraper-fastapi-2/backend')

from app.core.database import get_db
from app.models.project import ProjectCreate, DomainCreate, MatchType
from app.services.projects import ProjectService, DomainService, ScrapeSessionService
from app.models.user import User
from sqlmodel import select

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def simulate_frontend_project_creation():
    """
    Simulate the exact frontend project creation flow
    """
    
    logger.info("=== SIMULATING FRONTEND PROJECT CREATION FLOW ===")
    
    async with get_db().__anext__() as db:
        
        # Get or create a test user (simulate authenticated user)
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if not user:
            logger.error("❌ No user found in database. Please create a user first.")
            return
            
        logger.info(f"Using user: {user.email} (ID: {user.id})")
        
        # STEP 1: Create project (simulating POST /api/v1/projects)
        logger.info("\n--- STEP 1: Creating Project ---")
        
        project_data = ProjectCreate(
            name="Debug Test Project",
            description="Test project created by debug script", 
            process_documents=True,
            enable_attachment_download=False,
            langextract_enabled=False,
            langextract_provider="disabled",
            langextract_model=None,
            langextract_estimated_cost_per_1k=None
        )
        
        logger.info(f"Project data: {project_data.model_dump()}")
        
        try:
            project = await ProjectService.create_project(db, project_data, user.id)
            logger.info(f"✅ Project created successfully: ID={project.id}")
            logger.info(f"   Name: {project.name}")
            logger.info(f"   Status: {project.status}")
            logger.info(f"   Process Documents: {project.process_documents}")
            logger.info(f"   Index Name: {project.index_name}")
            
        except Exception as e:
            logger.error(f"❌ Project creation failed: {str(e)}")
            return
        
        # STEP 2: Create domains (simulating POST /api/v1/projects/{id}/domains)
        logger.info("\n--- STEP 2: Creating Domains ---")
        
        # Simulate creating multiple targets like the frontend does
        test_targets = [
            {
                "value": "example.com",
                "type": "domain",
                "from_date": "",
                "to_date": ""
            },
            {
                "value": "https://httpbin.org/html", 
                "type": "url",
                "from_date": "",
                "to_date": ""
            }
        ]
        
        created_domains = []
        
        for target in test_targets:
            logger.info(f"Creating domain for target: {target}")
            
            try:
                # Extract domain name and configure based on type
                if target["type"] == "domain":
                    domain_name = target["value"]
                    match_type = MatchType.DOMAIN
                    url_path = None
                else:  # url type
                    from urllib.parse import urlparse
                    parsed = urlparse(target["value"])
                    domain_name = parsed.hostname.lower()
                    match_type = MatchType.PREFIX
                    url_path = target["value"]
                
                domain_data = DomainCreate(
                    domain_name=domain_name,
                    match_type=match_type,
                    url_path=url_path,
                    from_date=target["from_date"] or None,
                    to_date=target["to_date"] or None,
                    max_pages=None,
                    active=True
                )
                
                logger.info(f"Domain data: {domain_data.model_dump()}")
                
                domain = await DomainService.create_domain(db, domain_data, project.id, user.id)
                
                if domain:
                    logger.info(f"✅ Domain created: ID={domain.id}")
                    logger.info(f"   Domain Name: {domain.domain_name}")
                    logger.info(f"   Match Type: {domain.match_type}")
                    logger.info(f"   URL Path: {domain.url_path}")
                    logger.info(f"   Status: {domain.status}")
                    created_domains.append(domain)
                else:
                    logger.error(f"❌ Domain creation returned None")
                    
            except Exception as e:
                logger.error(f"❌ Domain creation failed for {target}: {str(e)}")
        
        logger.info(f"Created {len(created_domains)} domains total")
        
        if not created_domains:
            logger.error("❌ No domains created, cannot proceed with scraping")
            return
        
        # STEP 3: Auto-start scraping (simulating POST /api/v1/projects/{id}/scrape)
        logger.info("\n--- STEP 3: Auto-Starting Scraping ---")
        
        try:
            # This simulates what the backend endpoint does
            session = await ScrapeSessionService.create_scrape_session(db, project.id, user.id)
            
            if not session:
                logger.error("❌ Failed to create scrape session")
                return
                
            logger.info(f"✅ Scrape session created: ID={session.id}")
            
            # Update project status to INDEXING (like the endpoint does)
            from app.models.project import ProjectStatus
            updated_project = await ProjectService.update_project_status(
                db, project.id, ProjectStatus.INDEXING, user.id
            )
            logger.info(f"✅ Project status updated to: {updated_project.status}")
            
            # Get domains and start scraping tasks
            domains = await DomainService.get_project_domains(db, project.id, user.id, skip=0, limit=1000)
            logger.info(f"Found {len(domains)} domains for scraping")
            
            # Import scraping task
            from app.tasks.firecrawl_scraping import scrape_domain_with_firecrawl
            from app.models.project import DomainStatus
            
            tasks_started = 0
            for domain in domains:
                if getattr(domain, "active", True) and domain.status == DomainStatus.ACTIVE:
                    logger.info(f"Starting scraping task for domain {domain.id}: {domain.domain_name}")
                    
                    # Queue the scraping task (like the endpoint does)
                    task_result = scrape_domain_with_firecrawl.delay(domain.id, session.id)
                    logger.info(f"✅ Scraping task queued: {task_result.id}")
                    tasks_started += 1
                else:
                    logger.warning(f"⏭️ Skipping inactive domain: {domain.domain_name} (active={getattr(domain, 'active', True)}, status={domain.status})")
            
            logger.info(f"✅ Started {tasks_started} scraping tasks")
            
            if tasks_started == 0:
                logger.warning("❌ No scraping tasks were started! This is likely the issue.")
                logger.info("Reasons scraping tasks might not start:")
                logger.info("- Domain status is not ACTIVE")
                logger.info("- Domain active flag is False") 
                logger.info("- No domains were created")
                
        except Exception as e:
            logger.error(f"❌ Auto-start scraping failed: {str(e)}")
            
        # STEP 4: Summary and next steps
        logger.info(f"\n=== SUMMARY ===")
        logger.info(f"Project ID: {project.id}")
        logger.info(f"Domains Created: {len(created_domains)}")
        logger.info(f"Scraping Tasks Started: {tasks_started}")
        
        if tasks_started > 0:
            logger.info("✅ Project creation flow completed successfully!")
            logger.info(f"You can monitor progress at: http://localhost:5173/projects/{project.id}")
            logger.info(f"Or check task status with: python debug_project_scraping.py debug {project.id}")
        else:
            logger.warning("⚠️ Project was created but scraping didn't start properly.")
            logger.info("Use the debug script to investigate further:")
            logger.info(f"  python debug_project_scraping.py debug {project.id}")

async def main():
    """Main function"""
    await simulate_frontend_project_creation()

if __name__ == "__main__":
    asyncio.run(main())