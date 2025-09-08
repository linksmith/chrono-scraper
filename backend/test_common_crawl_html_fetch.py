#!/usr/bin/env python3
"""
Focused test for Common Crawl HTML retrieval through proxy.
This test specifically verifies we can fetch actual HTML content from Common Crawl archives.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
import json

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_common_crawl_html_fetch():
    """Direct test of HTML fetching from Common Crawl using cdx_toolkit with proxy"""
    
    logger.info("\n" + "="*60)
    logger.info("TESTING COMMON CRAWL HTML FETCH WITH PROXY")
    logger.info("="*60)
    
    try:
        import cdx_toolkit
        import requests
        from app.core.config import settings
        
        # Setup proxy configuration
        proxy_url = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER.replace('http://', '')}"
        
        logger.info(f"Proxy: {settings.PROXY_SERVER}")
        logger.info(f"Username: {settings.PROXY_USERNAME}")
        
        # Create a session with proxy
        session = requests.Session()
        session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Test 1: Verify proxy works
        logger.info("\n[1] Testing proxy connectivity...")
        try:
            response = session.get('https://httpbin.org/ip', timeout=30)
            if response.status_code == 200:
                ip = response.json().get('origin')
                logger.info(f"✅ Proxy connected. IP: {ip}")
            else:
                logger.error(f"❌ Proxy test failed: HTTP {response.status_code}")
                return
        except Exception as e:
            logger.error(f"❌ Proxy connection failed: {e}")
            return
        
        # Test 2: Initialize cdx_toolkit with proxy
        logger.info("\n[2] Initializing cdx_toolkit with Common Crawl...")
        cdx = cdx_toolkit.CDXFetcher(source='cc')
        cdx.session = session  # Use our proxy session
        
        # Test 3: Fetch CDX records
        logger.info("\n[3] Fetching CDX records from Common Crawl...")
        domain = "example.com"
        from_date = "202401"
        to_date = "202401"
        
        logger.info(f"   Domain: {domain}")
        logger.info(f"   Date range: {from_date} - {to_date}")
        
        records = []
        try:
            count = 0
            for record in cdx.iter(url=f"*.{domain}/*", from_ts=from_date, to_ts=to_date, limit=5):
                records.append(record)
                count += 1
                logger.info(f"   Record {count}: {record['url']} [{record['timestamp']}]")
                if count >= 5:
                    break
        except Exception as e:
            logger.error(f"❌ CDX fetch failed: {e}")
            return
        
        if not records:
            logger.warning("⚠️ No CDX records found")
            return
        
        logger.info(f"✅ Found {len(records)} CDX records")
        
        # Test 4: Fetch actual HTML content
        logger.info("\n[4] Fetching HTML content from Common Crawl archives...")
        
        for i, record in enumerate(records[:3], 1):
            if record.get('mime', '').startswith('text/html'):
                logger.info(f"\n   Fetching HTML [{i}]:")
                logger.info(f"   URL: {record['url']}")
                logger.info(f"   Timestamp: {record['timestamp']}")
                logger.info(f"   Status: {record.get('status', 'N/A')}")
                
                try:
                    # Method 1: Try using cdx_toolkit's fetch
                    content = None
                    try:
                        # cdx_toolkit can fetch the actual content
                        obj = cdx_toolkit.CDXObject(record)
                        content = obj.fetch_warc_record()
                        
                        if content:
                            logger.info(f"   ✅ Fetched via cdx_toolkit")
                            logger.info(f"      Content size: {len(str(content))} bytes")
                            
                            # Try to extract HTML
                            if hasattr(content, 'content_stream'):
                                html = content.content_stream().read()
                                logger.info(f"      HTML size: {len(html)} bytes")
                                logger.info(f"      Sample: {html[:200].decode('utf-8', errors='ignore')}...")
                    except Exception as e:
                        logger.debug(f"   cdx_toolkit fetch failed: {e}")
                    
                    # Method 2: Direct Common Crawl S3 access
                    if not content and record.get('filename') and record.get('offset') and record.get('length'):
                        logger.info("   Attempting direct S3 fetch...")
                        
                        # Common Crawl data is in S3
                        filename = record['filename']
                        offset = int(record['offset'])
                        length = int(record['length'])
                        
                        # Construct S3 URL
                        s3_url = f"https://data.commoncrawl.org/{filename}"
                        
                        # Fetch with range header
                        headers = {
                            'Range': f'bytes={offset}-{offset+length-1}'
                        }
                        
                        response = session.get(s3_url, headers=headers, timeout=30)
                        if response.status_code in [200, 206]:
                            logger.info(f"   ✅ Fetched from S3")
                            logger.info(f"      Response size: {len(response.content)} bytes")
                            
                            # Parse WARC if needed
                            content_sample = response.content[:500].decode('utf-8', errors='ignore')
                            logger.info(f"      Sample: {content_sample[:200]}...")
                        else:
                            logger.warning(f"   ❌ S3 fetch failed: HTTP {response.status_code}")
                    
                except Exception as e:
                    logger.error(f"   ❌ Content fetch error: {e}")
        
        logger.info("\n" + "="*60)
        logger.info("TEST COMPLETE")
        logger.info("="*60)
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.error("Make sure to run this inside the Docker container")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)


async def test_with_smartproxy_service():
    """Test using the SmartproxyCommonCrawlService directly"""
    
    logger.info("\n" + "="*60)
    logger.info("TESTING WITH SMARTPROXY SERVICE")
    logger.info("="*60)
    
    try:
        from app.services.smartproxy_common_crawl_service import SmartproxyCommonCrawlService
        
        async with SmartproxyCommonCrawlService() as service:
            # Test fetching records
            records, stats = await service.fetch_cdx_records_simple(
                domain_name="example.com",
                from_date="20240101",
                to_date="20240131",
                match_type="domain",
                page_size=10,
                max_pages=1
            )
            
            logger.info(f"Fetched {len(records)} records")
            logger.info(f"Stats: {json.dumps(stats, indent=2)}")
            
            if records:
                # Display sample records
                for i, record in enumerate(records[:5], 1):
                    logger.info(f"\n[{i}] {record.original_url}")
                    logger.info(f"    Timestamp: {record.timestamp}")
                    logger.info(f"    Status: {record.status_code}")
                    logger.info(f"    MIME: {record.mimetype}")
                    
                    # For HTML records, we have the URL to fetch from
                    if record.mimetype and 'html' in record.mimetype:
                        logger.info(f"    → This is an HTML page that can be fetched")
            
            return records
            
    except Exception as e:
        logger.error(f"❌ Service test failed: {e}", exc_info=True)
        return []


async def main():
    """Run all tests"""
    
    # Test 1: Direct Common Crawl fetch
    await test_common_crawl_html_fetch()
    
    # Test 2: Using SmartProxy service
    await test_with_smartproxy_service()


if __name__ == "__main__":
    asyncio.run(main())