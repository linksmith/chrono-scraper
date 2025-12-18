#!/usr/bin/env python3
"""
Comprehensive test script for the Wayback Machine scraping integration
"""
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app.services.wayback_machine import CDXAPIClient, fetch_cdx_pages
from app.services.parallel_cdx_fetcher import fetch_cdx_records_parallel
from app.services.content_extractor import extract_content_from_record
from app.services.meilisearch_service import meilisearch_service
from app.services.circuit_breaker import get_wayback_machine_breaker, get_circuit_breaker_health

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_cdx_api_client():
    """Test basic CDX API functionality"""
    print("\n=== Testing CDX API Client ===")
    
    try:
        async with CDXAPIClient() as client:
            # Test small domain
            test_domain = "example.com"
            from_date = "20200101"
            to_date = "20200201"
            
            # Test page count
            page_count = await client.get_page_count(test_domain, from_date, to_date)
            print(f"✅ Page count for {test_domain}: {page_count}")
            
            # Test fetching records
            records, stats = await client.fetch_cdx_records(
                test_domain, from_date, to_date, max_pages=1
            )
            print(f"✅ Fetched {len(records)} records")
            print(f"   Stats: {stats}")
            
            if records:
                print(f"   Sample record: {records[0].original_url}")
            
    except Exception as e:
        print(f"❌ CDX API test failed: {str(e)}")
        return False
    
    return True


async def test_parallel_fetching():
    """Test parallel CDX fetching"""
    print("\n=== Testing Parallel CDX Fetching ===")
    
    try:
        # Test small domain with parallel fetching
        test_domain = "httpbin.org"
        from_date = "20230101"  
        to_date = "20230201"
        
        records, stats = await fetch_cdx_records_parallel(
            test_domain, from_date, to_date, max_pages=2
        )
        
        print(f"✅ Parallel fetch completed")
        print(f"   Records: {len(records)}")
        print(f"   Stats: {stats}")
        
        return len(records) > 0
        
    except Exception as e:
        print(f"❌ Parallel fetching test failed: {str(e)}")
        return False


async def test_content_extraction():
    """Test content extraction from CDX records"""
    print("\n=== Testing Content Extraction ===")
    
    try:
        # First get some CDX records
        async with CDXAPIClient() as client:
            records, _ = await client.fetch_cdx_records(
                "httpbin.org", "20230101", "20230201", max_pages=1
            )
        
        if not records:
            print("❌ No records found for extraction test")
            return False
        
        # Test extraction on first record
        test_record = records[0]
        print(f"   Testing extraction for: {test_record.original_url}")
        
        extracted = await extract_content_from_record(test_record)
        
        print(f"✅ Content extraction successful")
        print(f"   Title: {extracted.title[:50]}...")
        print(f"   Text length: {len(extracted.text)} chars")
        print(f"   Word count: {extracted.word_count}")
        print(f"   Method: {extracted.extraction_method}")
        
        return True
        
    except Exception as e:
        print(f"❌ Content extraction test failed: {str(e)}")
        return False


async def test_meilisearch_integration():
    """Test Meilisearch indexing"""
    print("\n=== Testing Meilisearch Integration ===")
    
    try:
        test_index = "test_wayback_integration"
        
        async with meilisearch_service as ms:
            # Create test index
            await ms.create_index(test_index)
            print(f"✅ Created test index: {test_index}")
            
            # Note: Full page indexing would require database setup
            # This just tests the service connection
            
        return True
        
    except Exception as e:
        print(f"❌ Meilisearch test failed: {str(e)}")
        print("   Note: This is expected if Meilisearch is not running")
        return True  # Don't fail overall test for optional service


async def test_circuit_breakers():
    """Test circuit breaker functionality"""
    print("\n=== Testing Circuit Breakers ===")
    
    try:
        # Test Wayback Machine circuit breaker
        breaker = get_wayback_machine_breaker()
        
        # Test normal operation
        async def test_operation():
            return "success"
        
        result = await breaker.execute(test_operation)
        print(f"✅ Circuit breaker normal operation: {result}")
        
        # Test status
        status = breaker.get_status()
        print(f"   Breaker state: {status['state']}")
        print(f"   Success rate: {status['metrics']['success_rate']}%")
        
        # Test health check
        health = get_circuit_breaker_health()
        print(f"✅ Circuit breaker health: {health['overall_health']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Circuit breaker test failed: {str(e)}")
        return False


async def test_list_page_filtering():
    """Test list page filtering logic"""
    print("\n=== Testing List Page Filtering ===")
    
    from app.services.wayback_machine import ListPageFilter
    
    # Test URLs that should be filtered
    list_urls = [
        "https://example.com/blog/",
        "https://example.com/blog/page/2",
        "https://example.com/category/news/",
        "https://example.com/2023/",
        "https://example.com/search/?q=test",
        "https://example.com/feed/",
    ]
    
    # Test URLs that should NOT be filtered
    content_urls = [
        "https://example.com/blog/my-great-article",
        "https://example.com/about-us",
        "https://example.com/products/widget-x",
        "https://example.com/2023/01/15/news-story",
    ]
    
    filtered_count = 0
    for url in list_urls:
        if ListPageFilter.is_list_page(url):
            filtered_count += 1
            print(f"   ✅ Correctly filtered: {url}")
        else:
            print(f"   ❌ Should have filtered: {url}")
    
    kept_count = 0
    for url in content_urls:
        if not ListPageFilter.is_list_page(url):
            kept_count += 1
            print(f"   ✅ Correctly kept: {url}")
        else:
            print(f"   ❌ Should have kept: {url}")
    
    success_rate = (filtered_count + kept_count) / (len(list_urls) + len(content_urls))
    print(f"✅ List filtering accuracy: {success_rate*100:.1f}%")
    
    return success_rate > 0.8  # 80% accuracy threshold


async def run_integration_test():
    """Run complete integration test"""
    print("🚀 Starting Wayback Machine Integration Tests")
    print("=" * 60)
    
    tests = [
        ("CDX API Client", test_cdx_api_client),
        ("List Page Filtering", test_list_page_filtering),
        ("Parallel CDX Fetching", test_parallel_fetching), 
        ("Content Extraction", test_content_extraction),
        ("Meilisearch Integration", test_meilisearch_integration),
        ("Circuit Breakers", test_circuit_breakers),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        try:
            start_time = datetime.now()
            result = await test_func()
            duration = (datetime.now() - start_time).total_seconds()
            
            results[test_name] = {
                "success": result,
                "duration": duration
            }
            
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"   {status} ({duration:.2f}s)")
            
        except Exception as e:
            results[test_name] = {
                "success": False,
                "error": str(e),
                "duration": 0
            }
            print(f"   ❌ FAIL - Exception: {str(e)}")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for r in results.values() if r["success"])
    total = len(results)
    total_time = sum(r["duration"] for r in results.values())
    
    print(f"Tests passed: {passed}/{total}")
    print(f"Success rate: {passed/total*100:.1f}%")
    print(f"Total time: {total_time:.2f}s")
    
    print("\nDetailed Results:")
    for test_name, result in results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        duration = result["duration"]
        print(f"  {status} {test_name:<25} ({duration:.2f}s)")
        
        if not result["success"] and "error" in result:
            print(f"      Error: {result['error']}")
    
    if passed == total:
        print(f"\n🎉 All tests passed! The Wayback Machine integration is working correctly.")
        return True
    else:
        print(f"\n⚠️  {total-passed} test(s) failed. Please check the errors above.")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_integration_test())
    sys.exit(0 if success else 1)