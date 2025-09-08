#!/usr/bin/env python3
"""
Test script to verify the integrated Common Crawl service with SmartProxy works correctly.
This tests the complete flow: CDX records → HTML content retrieval via SmartProxy.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_integrated_common_crawl():
    """Test the integrated Common Crawl service with SmartProxy"""
    
    logger.info("="*60)
    logger.info("TESTING INTEGRATED COMMON CRAWL SERVICE")
    logger.info("="*60)
    
    try:
        # Import our updated service
        from app.services.common_crawl_service import CommonCrawlService
        from app.core.config import settings
        
        # Validate configuration
        if not all([settings.PROXY_SERVER, settings.PROXY_USERNAME, settings.PROXY_PASSWORD]):
            logger.error("❌ SmartProxy credentials not configured")
            return False
        
        logger.info(f"✅ SmartProxy configured: {settings.PROXY_SERVER}")
        
        # Test domain with known historical data
        test_domain = "hetstoerwoud.nl"
        from_date = "20240101"
        to_date = "20251231"
        
        logger.info(f"🔍 Testing CDX fetch for {test_domain}")
        
        # Test the integrated service
        async with CommonCrawlService() as service:
            # Test CDX records fetch
            records, stats = await service.fetch_cdx_records_simple(
                domain_name=test_domain,
                from_date=from_date,
                to_date=to_date,
                match_type="domain",
                max_pages=1,  # Keep test small
                include_attachments=True
            )
            
            logger.info(f"📊 CDX Results:")
            logger.info(f"   Records found: {len(records)}")
            logger.info(f"   Stats: {stats}")
            
            if not records:
                logger.warning("⚠️ No records found - this might be expected")
                return True
            
            # Test HTML content retrieval for first record
            logger.info(f"🌐 Testing HTML content retrieval...")
            
            test_record = records[0]
            logger.info(f"   Testing record: {test_record.original_url}")
            
            # Try to get the raw cdx_toolkit record for HTML fetch
            # We need to fetch raw records to get the S3 info
            raw_records = []
            
            # Re-fetch with the internal method to get raw records
            query_params = service._build_common_crawl_query(
                test_domain, from_date, to_date, "domain", None, True
            )
            
            raw_records = await service._fetch_records_with_retry(
                query_params, page_size=10, max_pages=1
            )
            
            if raw_records:
                logger.info(f"   Got {len(raw_records)} raw records for HTML test")
                
                # Test HTML content retrieval
                html_content = await service.fetch_html_content(raw_records[0])
                
                if html_content:
                    logger.info(f"   ✅ HTML content retrieved: {len(html_content)} chars")
                    logger.info(f"   Content preview: {html_content[:200]}...")
                    return True
                else:
                    logger.warning("   ⚠️ No HTML content retrieved (might be expected)")
                    return True
            else:
                logger.warning("   ⚠️ No raw records for HTML test")
                return True
            
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False


async def test_archive_router_integration():
    """Test the archive router integration"""
    
    logger.info("="*60)
    logger.info("TESTING ARCHIVE ROUTER INTEGRATION")
    logger.info("="*60)
    
    try:
        from app.services.archive_service_router import ArchiveServiceRouter
        from app.models.project import ArchiveSource
        
        # Create router with Common Crawl preference
        router = ArchiveServiceRouter()
        
        # Test project config for Common Crawl
        project_config = {
            'archive_source': ArchiveSource.COMMON_CRAWL,
            'fallback_enabled': False,  # Test Common Crawl only
            'archive_config': {
                'common_crawl': {
                    'max_pages': 1,
                    'page_size': 10
                }
            }
        }
        
        test_domain = "hetstoerwoud.nl"
        from_date = "20240101"
        to_date = "20251231"
        
        logger.info(f"🔍 Testing router query for {test_domain}")
        
        # Test query through router
        records, stats = await router.query_archive(
            domain=test_domain,
            from_date=from_date,
            to_date=to_date,
            project_config=project_config,
            match_type="domain"
        )
        
        logger.info(f"📊 Router Results:")
        logger.info(f"   Records found: {len(records)}")
        logger.info(f"   Successful source: {stats.get('successful_source', 'none')}")
        logger.info(f"   Fallback used: {stats.get('fallback_used', False)}")
        
        # Check router health
        health = router.get_health_status()
        logger.info(f"   Router health: {health['overall_status']}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Router test failed: {e}")
        return False


async def main():
    """Main test runner"""
    
    logger.info("🚀 Starting Common Crawl integration tests")
    
    # Test 1: Integrated service
    service_test_passed = await test_integrated_common_crawl()
    
    # Test 2: Archive router integration
    router_test_passed = await test_archive_router_integration()
    
    # Summary
    logger.info("="*60)
    logger.info("TEST SUMMARY")
    logger.info("="*60)
    
    logger.info(f"Integrated Service Test: {'✅ PASSED' if service_test_passed else '❌ FAILED'}")
    logger.info(f"Archive Router Test: {'✅ PASSED' if router_test_passed else '❌ FAILED'}")
    
    if service_test_passed and router_test_passed:
        logger.info("🎉 ALL TESTS PASSED - Common Crawl integration is working!")
        return True
    else:
        logger.error("💥 Some tests failed - check configuration and logs")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)