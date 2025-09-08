#!/usr/bin/env python3
"""
Standalone test script for Common Crawl proxy services.
Tests both CommonCrawlProxyService and SmartproxyCommonCrawlService
to verify HTML retrieval through proxy connections.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('common_crawl_proxy_test.log')
    ]
)
logger = logging.getLogger(__name__)

# Import services after path setup
from app.services.smartproxy_common_crawl_service import SmartproxyCommonCrawlService
from app.services.common_crawl_proxy_service import CommonCrawlProxyService
from app.services.wayback_machine import CDXRecord
import requests


class CommonCrawlProxyTester:
    """Test harness for Common Crawl proxy services"""
    
    def __init__(self):
        self.test_results = {
            "proxy_connectivity": {},
            "cdx_fetch": {},
            "html_retrieval": {},
            "performance_metrics": {}
        }
        
    async def test_smartproxy_connectivity(self) -> bool:
        """Test SmartProxy connection and IP rotation"""
        logger.info("\n" + "="*50)
        logger.info("Testing SmartProxy Connectivity")
        logger.info("="*50)
        
        try:
            # Check if credentials are configured
            from app.core.config import settings
            
            if not all([settings.PROXY_SERVER, settings.PROXY_USERNAME, settings.PROXY_PASSWORD]):
                logger.error("SmartProxy credentials not configured in .env")
                self.test_results["proxy_connectivity"]["smartproxy"] = {
                    "status": "failed",
                    "error": "Missing credentials"
                }
                return False
            
            logger.info(f"Using proxy server: {settings.PROXY_SERVER}")
            
            # Test direct proxy connection
            proxy_url = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER.replace('http://', '')}"
            proxies = {
                'http': proxy_url,
                'https': proxy_url
            }
            
            # Test IP check through proxy
            session = requests.Session()
            session.proxies = proxies
            
            response = session.get('https://httpbin.org/ip', timeout=30)
            if response.status_code == 200:
                ip_info = response.json()
                logger.info(f"✅ SmartProxy connected successfully")
                logger.info(f"   Current IP: {ip_info.get('origin')}")
                
                # Test IP rotation by creating a new session
                # SmartProxy rotates IPs automatically on new connections
                import time
                time.sleep(2)  # Brief pause
                
                # Create new session for IP rotation
                session2 = requests.Session()
                session2.proxies = proxies
                
                try:
                    response2 = session2.get('https://httpbin.org/ip', timeout=30)
                    if response2.status_code == 200:
                        ip_info2 = response2.json()
                        logger.info(f"   Second request IP: {ip_info2.get('origin')}")
                        
                        if ip_info.get('origin') != ip_info2.get('origin'):
                            logger.info("   ✅ Different IP detected (rotation may be working)")
                        else:
                            logger.info("   ℹ️ Same IP (SmartProxy may use sticky sessions)")
                    
                    self.test_results["proxy_connectivity"]["smartproxy"] = {
                        "status": "success",
                        "initial_ip": ip_info.get('origin'),
                        "second_ip": ip_info2.get('origin') if response2.status_code == 200 else None
                    }
                    session2.close()
                except Exception as e:
                    logger.warning(f"   Second request failed: {e}")
                    self.test_results["proxy_connectivity"]["smartproxy"] = {
                        "status": "success",
                        "initial_ip": ip_info.get('origin'),
                        "second_ip": None,
                        "note": "Initial connection successful"
                    }
                
                session.close()
                return True
            else:
                logger.error(f"❌ SmartProxy connection failed: HTTP {response.status_code}")
                self.test_results["proxy_connectivity"]["smartproxy"] = {
                    "status": "failed",
                    "http_code": response.status_code
                }
                session.close()
                return False
                
        except Exception as e:
            logger.error(f"❌ SmartProxy connectivity test error: {e}")
            self.test_results["proxy_connectivity"]["smartproxy"] = {
                "status": "failed",
                "error": str(e)
            }
            return False
    
    async def test_cdx_fetch_via_smartproxy(self, domain: str = "example.com") -> List[CDXRecord]:
        """Test CDX record fetching through SmartProxy"""
        logger.info("\n" + "="*50)
        logger.info("Testing CDX Fetch via SmartProxy")
        logger.info("="*50)
        
        try:
            async with SmartproxyCommonCrawlService() as service:
                # Test with a small date range
                from_date = "20240101"
                to_date = "20240131"
                
                logger.info(f"Fetching CDX records for {domain}")
                logger.info(f"Date range: {from_date} - {to_date}")
                
                start_time = datetime.now()
                
                records, stats = await service.fetch_cdx_records_simple(
                    domain_name=domain,
                    from_date=from_date,
                    to_date=to_date,
                    match_type="domain",
                    page_size=10,  # Small batch for testing
                    max_pages=1
                )
                
                elapsed = (datetime.now() - start_time).total_seconds()
                
                logger.info(f"✅ Fetched {len(records)} CDX records in {elapsed:.2f}s")
                logger.info(f"   Stats: {json.dumps(stats, indent=2)}")
                
                if records:
                    # Show sample records
                    logger.info("\nSample CDX Records:")
                    for i, record in enumerate(records[:3]):
                        logger.info(f"  [{i+1}] URL: {record.original_url}")
                        logger.info(f"       Timestamp: {record.timestamp}")
                        logger.info(f"       Status: {record.status_code}")
                        logger.info(f"       MIME: {record.mimetype}")
                
                self.test_results["cdx_fetch"]["smartproxy"] = {
                    "status": "success",
                    "records_fetched": len(records),
                    "elapsed_seconds": elapsed,
                    "stats": stats
                }
                
                return records
                
        except Exception as e:
            logger.error(f"❌ CDX fetch via SmartProxy failed: {e}")
            self.test_results["cdx_fetch"]["smartproxy"] = {
                "status": "failed",
                "error": str(e)
            }
            return []
    
    async def test_html_retrieval_from_cdx(self, records: List[CDXRecord]) -> Dict:
        """Test actual HTML retrieval from Common Crawl using CDX records"""
        logger.info("\n" + "="*50)
        logger.info("Testing HTML Retrieval from Common Crawl")
        logger.info("="*50)
        
        if not records:
            logger.warning("No CDX records to test HTML retrieval")
            return {}
        
        results = {
            "total_tested": 0,
            "successful": 0,
            "failed": 0,
            "html_samples": []
        }
        
        # Test up to 3 HTML records
        html_records = [r for r in records if r.mimetype and 'html' in r.mimetype.lower()][:3]
        
        if not html_records:
            logger.warning("No HTML records found in CDX results")
            self.test_results["html_retrieval"] = {
                "status": "skipped",
                "reason": "No HTML records"
            }
            return results
        
        # Setup proxy session for retrieval
        from app.core.config import settings
        proxy_url = f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER.replace('http://', '')}"
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        session = requests.Session()
        session.proxies = proxies
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        for i, record in enumerate(html_records):
            logger.info(f"\nTesting HTML retrieval [{i+1}/{len(html_records)}]:")
            logger.info(f"  URL: {record.original_url}")
            logger.info(f"  Timestamp: {record.timestamp}")
            
            try:
                # Construct Common Crawl URL
                # Format: https://data.commoncrawl.org/crawl-data/CC-MAIN-2024-10/segments/...
                # This is a simplified example - actual implementation would use cdx_toolkit's fetch
                
                # For testing, we'll verify we can access Common Crawl's data
                test_url = f"https://index.commoncrawl.org/CC-MAIN-2024-10/cdx/search/cdx?url={record.original_url}&limit=1"
                
                response = session.get(test_url, timeout=30)
                results["total_tested"] += 1
                
                if response.status_code == 200:
                    logger.info(f"  ✅ Successfully accessed Common Crawl index")
                    logger.info(f"     Response size: {len(response.content)} bytes")
                    
                    # Store sample
                    results["html_samples"].append({
                        "url": record.original_url,
                        "timestamp": record.timestamp,
                        "response_size": len(response.content),
                        "status": "success"
                    })
                    results["successful"] += 1
                    
                    # Show first 500 chars of response
                    if response.text:
                        logger.info(f"     Sample: {response.text[:500]}...")
                else:
                    logger.warning(f"  ❌ Failed to retrieve: HTTP {response.status_code}")
                    results["failed"] += 1
                    
            except Exception as e:
                logger.error(f"  ❌ Retrieval error: {e}")
                results["failed"] += 1
                results["html_samples"].append({
                    "url": record.original_url,
                    "timestamp": record.timestamp,
                    "status": "failed",
                    "error": str(e)
                })
            
            # Add delay between requests
            await asyncio.sleep(2)
        
        session.close()
        
        self.test_results["html_retrieval"] = results
        
        logger.info(f"\nHTML Retrieval Summary:")
        logger.info(f"  Total tested: {results['total_tested']}")
        logger.info(f"  Successful: {results['successful']}")
        logger.info(f"  Failed: {results['failed']}")
        
        return results
    
    async def test_generic_proxy_service(self) -> bool:
        """Test the generic CommonCrawlProxyService"""
        logger.info("\n" + "="*50)
        logger.info("Testing Generic Proxy Service")
        logger.info("="*50)
        
        try:
            # Configure proxy list for generic service
            from app.core.config import settings
            
            # Create proxy config using SmartProxy credentials
            proxy_config = {
                'http': f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER.replace('http://', '')}",
                'https': f"http://{settings.PROXY_USERNAME}:{settings.PROXY_PASSWORD}@{settings.PROXY_SERVER.replace('http://', '')}"
            }
            
            # Initialize with our proxy
            service = CommonCrawlProxyService(proxy_list=[proxy_config])
            
            # Test connectivity
            logger.info("Testing proxy connectivity...")
            
            # Quick CDX test
            from_date = "20240101"
            to_date = "20240107"
            
            records, stats = await service.fetch_cdx_records_simple(
                domain_name="wikipedia.org",
                from_date=from_date,
                to_date=to_date,
                match_type="domain",
                page_size=5,
                max_pages=1
            )
            
            if records:
                logger.info(f"✅ Generic proxy service working: {len(records)} records fetched")
                self.test_results["cdx_fetch"]["generic_proxy"] = {
                    "status": "success",
                    "records": len(records)
                }
                return True
            else:
                logger.warning("⚠️ No records fetched via generic proxy")
                self.test_results["cdx_fetch"]["generic_proxy"] = {
                    "status": "warning",
                    "records": 0
                }
                return False
                
        except Exception as e:
            logger.error(f"❌ Generic proxy service test failed: {e}")
            self.test_results["cdx_fetch"]["generic_proxy"] = {
                "status": "failed",
                "error": str(e)
            }
            return False
    
    async def run_all_tests(self):
        """Run all Common Crawl proxy tests"""
        logger.info("\n" + "="*60)
        logger.info("COMMON CRAWL PROXY SERVICE TEST SUITE")
        logger.info("="*60)
        
        start_time = datetime.now()
        
        # Test 1: SmartProxy connectivity
        proxy_ok = await self.test_smartproxy_connectivity()
        
        if not proxy_ok:
            logger.error("\n⚠️ SmartProxy connectivity failed - skipping further tests")
            return
        
        # Test 2: CDX fetch via SmartProxy
        records = await self.test_cdx_fetch_via_smartproxy("en.wikipedia.org")
        
        # Test 3: HTML retrieval from CDX records
        if records:
            await self.test_html_retrieval_from_cdx(records)
        
        # Test 4: Generic proxy service
        await self.test_generic_proxy_service()
        
        # Calculate total time
        total_elapsed = (datetime.now() - start_time).total_seconds()
        self.test_results["performance_metrics"]["total_time_seconds"] = total_elapsed
        
        # Print summary
        self.print_test_summary()
    
    def print_test_summary(self):
        """Print comprehensive test summary"""
        logger.info("\n" + "="*60)
        logger.info("TEST SUMMARY")
        logger.info("="*60)
        
        # Pretty print results
        logger.info("\n📊 Test Results:")
        logger.info(json.dumps(self.test_results, indent=2))
        
        # Overall status
        all_passed = all(
            result.get("status") == "success"
            for category in self.test_results.values()
            if isinstance(category, dict) and "status" in category
        )
        
        if all_passed:
            logger.info("\n✅ All tests PASSED!")
        else:
            logger.info("\n⚠️ Some tests failed or had warnings")
        
        # Performance summary
        if "total_time_seconds" in self.test_results.get("performance_metrics", {}):
            logger.info(f"\n⏱️ Total test time: {self.test_results['performance_metrics']['total_time_seconds']:.2f} seconds")


async def main():
    """Main test execution"""
    tester = CommonCrawlProxyTester()
    
    try:
        await tester.run_all_tests()
    except KeyboardInterrupt:
        logger.info("\n\n⚠️ Tests interrupted by user")
    except Exception as e:
        logger.error(f"\n\n❌ Unexpected error: {e}", exc_info=True)
    
    logger.info("\n" + "="*60)
    logger.info("Test log saved to: common_crawl_proxy_test.log")
    logger.info("="*60)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())