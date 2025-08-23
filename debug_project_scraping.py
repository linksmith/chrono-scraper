#!/usr/bin/env python3
"""
Debug script for project creation and scraping flow.

This script helps identify why creating a project with default settings and prefix URLs
doesn't trigger CDX API calls or page scraping.
"""
import asyncio
import logging
import sys
import os
from datetime import datetime
from typing import Any, Dict, List

# Add the backend directory to the path
sys.path.append('/home/bizon/Development/chrono-scraper-fastapi-2/backend')

from app.core.database import get_db
from app.models.project import Project, Domain, MatchType, DomainStatus, ProjectStatus
from app.models.scraping import ScrapePage, ScrapePageStatus
from app.services.wayback_machine import CDXAPIClient
from app.services.intelligent_filter import get_intelligent_filter
from app.services.projects import ProjectService, DomainService
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def debug_project_scraping_flow(project_id: int = None, domain_name: str = None, url_prefix: str = None):
    """
    Debug the entire project scraping flow
    
    Args:
        project_id: Existing project ID to debug, or None to create a test project
        domain_name: Domain name to test (e.g., 'example.com')  
        url_prefix: Full URL prefix to test (e.g., 'https://example.com/blog/')
    """
    
    async with get_db().__anext__() as db:
        try:
            if project_id:
                # Debug existing project
                logger.info(f"=== DEBUGGING EXISTING PROJECT {project_id} ===")
                project = await db.get(Project, project_id)
                if not project:
                    logger.error(f"Project {project_id} not found!")
                    return
                    
                domains = await db.execute(select(Domain).where(Domain.project_id == project_id))
                domains_list = domains.scalars().all()
                
            else:
                # Create test project for debugging
                logger.info("=== CREATING TEST PROJECT FOR DEBUGGING ===")
                
                if not domain_name:
                    domain_name = "example.com"
                if not url_prefix:
                    url_prefix = f"https://{domain_name}/blog/"
                    
                # Create test project
                from app.models.project import ProjectCreate
                project_data = ProjectCreate(
                    name=f"Debug Test Project - {datetime.now().strftime('%Y%m%d_%H%M')}",
                    description="Test project for debugging scraping flow",
                    process_documents=True,
                    enable_attachment_download=False,
                    langextract_enabled=False
                )
                
                logger.info(f"Creating project: {project_data.name}")
                project = await ProjectService.create_project(db, project_data, user_id=1)
                logger.info(f"✅ Project created: ID={project.id}, Status={project.status}")
                
                # Create test domain with prefix match
                from app.models.project import DomainCreate
                domain_data = DomainCreate(
                    domain_name=domain_name,
                    match_type=MatchType.PREFIX,
                    url_path=url_prefix,
                    active=True,
                    max_pages=5  # Limit for testing
                )
                
                logger.info(f"Creating domain: {domain_name} with prefix: {url_prefix}")
                domain = await DomainService.create_domain(db, domain_data, project.id, user_id=1)
                logger.info(f"✅ Domain created: ID={domain.id}, Status={domain.status}")
                
                domains_list = [domain]
            
            # Debug each domain
            for domain in domains_list:
                await debug_domain_scraping(db, project, domain)
                
        except Exception as e:
            logger.error(f"Error in debug flow: {str(e)}", exc_info=True)

async def debug_domain_scraping(db: AsyncSession, project: Project, domain: Domain):
    """Debug scraping for a specific domain"""
    
    logger.info(f"\n=== DEBUGGING DOMAIN: {domain.domain_name} ===")
    logger.info(f"Domain ID: {domain.id}")
    logger.info(f"Match Type: {domain.match_type}")
    logger.info(f"URL Path: {domain.url_path}")
    logger.info(f"Status: {domain.status}")
    logger.info(f"Active: {getattr(domain, 'active', True)}")
    logger.info(f"Max Pages: {domain.max_pages}")
    
    # Check date range
    from_date = domain.from_date.strftime("%Y%m%d") if domain.from_date else "20200101"
    to_date = domain.to_date.strftime("%Y%m%d") if domain.to_date else datetime.now().strftime("%Y%m%d")
    logger.info(f"Date Range: {from_date} to {to_date}")
    
    # Step 1: Test CDX API connectivity
    logger.info(f"\n--- STEP 1: CDX API Page Count Check ---")
    try:
        # Handle both enum and string cases for match_type
        if hasattr(domain.match_type, 'value'):
            match_type_str = domain.match_type.value
        elif isinstance(domain.match_type, str):
            match_type_str = domain.match_type
        else:
            match_type_str = str(domain.match_type)
            
        async with CDXAPIClient() as cdx_client:
            page_count = await cdx_client.get_page_count(
                domain_name=domain.domain_name,
                from_date=from_date,
                to_date=to_date,
                match_type=match_type_str,
                url_path=domain.url_path,
                min_size=0,  # Allow small files for prefix targets
                include_attachments=project.enable_attachment_download
            )
            
        logger.info(f"✅ CDX API Response: {page_count} pages available")
        
        if page_count == 0:
            logger.warning("❌ No CDX data found! This could be why scraping fails.")
            logger.info("Possible reasons:")
            logger.info("- Domain has no archived content for this date range")
            logger.info("- URL prefix doesn't match any archived URLs")
            logger.info("- CDX API is temporarily unavailable")
            
            # Test with domain match instead of prefix
            if match_type_str == "prefix":
                logger.info("\n--- TESTING WITH DOMAIN MATCH INSTEAD ---")
                domain_page_count = await cdx_client.get_page_count(
                    domain_name=domain.domain_name,
                    from_date=from_date,
                    to_date=to_date,
                    match_type="domain",
                    url_path=None,
                    min_size=1000,
                    include_attachments=project.enable_attachment_download
                )
                logger.info(f"Domain match result: {domain_page_count} pages")
                
            return
            
    except Exception as e:
        logger.error(f"❌ CDX API Error: {str(e)}")
        return
    
    # Step 2: Test CDX record fetching
    logger.info(f"\n--- STEP 2: CDX Record Fetching ---")
    try:
        intelligent_filter = get_intelligent_filter()
        existing_digests = await intelligent_filter.get_existing_digests(
            domain.domain_name,
            domain_id=domain.id,
            url_prefix=domain.url_path if match_type_str == "prefix" else None
        )
        logger.info(f"Existing digests: {len(existing_digests)}")
        
        async with CDXAPIClient() as cdx_client:
            raw_records, raw_stats = await cdx_client.fetch_cdx_records(
                domain_name=domain.domain_name,
                from_date=from_date,
                to_date=to_date,
                match_type=match_type_str,
                url_path=domain.url_path,
                min_size=0,  # Allow small files for prefix targets
                max_size=10 * 1024 * 1024,
                max_pages=min(domain.max_pages or 5, 5),  # Limit for testing
                existing_digests=existing_digests,
                filter_list_pages=True,
                include_attachments=project.enable_attachment_download
            )
            
        logger.info(f"✅ Raw CDX records: {len(raw_records)}")
        logger.info(f"Raw CDX stats: {raw_stats}")
        
        # Show sample records
        if raw_records:
            logger.info("Sample records:")
            for i, record in enumerate(raw_records[:3]):
                logger.info(f"  {i+1}. {record.original_url} ({record.timestamp}) - {record.content_length_bytes} bytes")
        
        # Step 3: Test intelligent filtering
        logger.info(f"\n--- STEP 3: Intelligent Filtering ---")
        filtered_records, filter_stats = intelligent_filter.filter_records_intelligent(
            raw_records, existing_digests, prioritize_changes=True, 
            include_attachments=project.enable_attachment_download
        )
        
        logger.info(f"✅ Filtered records: {len(filtered_records)}")
        logger.info(f"Filter stats: {filter_stats}")
        
        if filtered_records:
            logger.info("Sample filtered records:")
            for i, record in enumerate(filtered_records[:3]):
                priority = intelligent_filter.get_scraping_priority(record, project.enable_attachment_download)
                logger.info(f"  {i+1}. {record.original_url} (Priority: {priority})")
        else:
            logger.warning("❌ All records filtered out! This could be why scraping fails.")
            
    except Exception as e:
        logger.error(f"❌ Record fetching error: {str(e)}")
        return
    
    # Step 4: Check existing scrape pages
    logger.info(f"\n--- STEP 4: Existing Scrape Pages ---")
    try:
        scrape_pages = await db.execute(
            select(ScrapePage).where(ScrapePage.domain_id == domain.id)
        )
        scrape_pages_list = scrape_pages.scalars().all()
        
        logger.info(f"Existing scrape pages: {len(scrape_pages_list)}")
        if scrape_pages_list:
            status_counts = {}
            for page in scrape_pages_list:
                status = page.status.value if hasattr(page.status, 'value') else page.status
                status_counts[status] = status_counts.get(status, 0) + 1
            logger.info(f"Status breakdown: {status_counts}")
            
        # Check existing pages
        from app.models.project import Page
        pages = await db.execute(
            select(Page).where(Page.domain_id == domain.id)
        )
        pages_list = pages.scalars().all()
        logger.info(f"Existing final pages: {len(pages_list)}")
        
    except Exception as e:
        logger.error(f"❌ Database check error: {str(e)}")
    
    logger.info(f"\n=== DOMAIN DEBUG COMPLETE ===\n")

async def test_manual_scraping_trigger(project_id: int):
    """Test manual scraping trigger for a project"""
    
    logger.info(f"\n=== TESTING MANUAL SCRAPING TRIGGER ===")
    
    async with get_db().__anext__() as db:
        # Import here to avoid circular imports
        from app.services.projects import ScrapeSessionService
        from app.tasks.firecrawl_scraping import scrape_domain_with_firecrawl
        
        # Create scrape session
        session = await ScrapeSessionService.create_scrape_session(db, project_id, user_id=1)
        if not session:
            logger.error("❌ Failed to create scrape session")
            return
            
        logger.info(f"✅ Scrape session created: {session.id}")
        
        # Get domains to scrape
        domains = await db.execute(select(Domain).where(Domain.project_id == project_id))
        domains_list = domains.scalars().all()
        
        logger.info(f"Found {len(domains_list)} domains to scrape")
        
        # Queue scraping tasks
        tasks_queued = 0
        for domain in domains_list:
            if domain.status == DomainStatus.ACTIVE and getattr(domain, "active", True):
                logger.info(f"Queuing scraping task for domain {domain.id}: {domain.domain_name}")
                
                # Queue the task (don't wait for it in debug mode)
                result = scrape_domain_with_firecrawl.delay(domain.id, session.id)
                logger.info(f"✅ Task queued with ID: {result.id}")
                tasks_queued += 1
            else:
                logger.warning(f"⏭️ Skipping inactive domain {domain.id}: {domain.domain_name}")
        
        logger.info(f"Queued {tasks_queued} scraping tasks")

async def main():
    """Main debug function"""
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python debug_project_scraping.py create <domain_name> <url_prefix>")
        print("  python debug_project_scraping.py debug <project_id>")
        print("  python debug_project_scraping.py trigger <project_id>")
        print("")
        print("Examples:")
        print("  python debug_project_scraping.py create example.com https://example.com/blog/")
        print("  python debug_project_scraping.py debug 123")
        print("  python debug_project_scraping.py trigger 123")
        return
        
    command = sys.argv[1].lower()
    
    if command == "create":
        domain_name = sys.argv[2] if len(sys.argv) > 2 else "example.com"
        url_prefix = sys.argv[3] if len(sys.argv) > 3 else f"https://{domain_name}/blog/"
        await debug_project_scraping_flow(domain_name=domain_name, url_prefix=url_prefix)
        
    elif command == "debug":
        if len(sys.argv) < 3:
            print("Error: project_id required for debug command")
            return
        project_id = int(sys.argv[2])
        await debug_project_scraping_flow(project_id=project_id)
        
    elif command == "trigger":
        if len(sys.argv) < 3:
            print("Error: project_id required for trigger command")
            return
        project_id = int(sys.argv[2])
        await test_manual_scraping_trigger(project_id)
        
    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    asyncio.run(main())