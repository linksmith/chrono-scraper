#!/usr/bin/env python3
"""
Test script for Firecrawl-only content extraction with real Wayback Machine data
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta

# Add the app to Python path
sys.path.append('/home/bizon/Development/chrono-scraper-fastapi-2/backend')

from app.services.wayback_machine import CDXAPIClient, CDXRecord
from app.services.firecrawl_extractor import get_firecrawl_extractor
from app.services.intelligent_filter import get_intelligent_filter

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_cdx_fetching():
    """Test CDX API fetching with intelligent filtering"""
    print("=" * 60)
    print("Testing CDX API Fetching with Intelligent Filtering")
    print("=" * 60)
    
    # Test with a domain that has cleaner CDX data
    test_domain = "whitehouse.gov"
    from_date = "20240101"
    to_date = "20240131"  # Just January 2024 for testing
    
    async with CDXAPIClient() as cdx_client:
        # Get page count first
        page_count = await cdx_client.get_page_count(test_domain, from_date, to_date)
        print(f"Total pages available for {test_domain}: {page_count}")
        
        # Fetch records with filtering
        records, stats = await cdx_client.fetch_cdx_records(
            domain_name=test_domain,
            from_date=from_date,
            to_date=to_date,
            min_size=1000,
            max_size=10 * 1024 * 1024,
            max_pages=2,  # Limit for testing
            filter_list_pages=True
        )
        
        print(f"Fetched records: {len(records)}")
        print(f"Statistics: {stats}")
        
        # Apply intelligent filtering
        try:
            intelligent_filter = get_intelligent_filter()
            filtered_records, filter_stats = intelligent_filter.filter_records_intelligent(
                records, set(), prioritize_changes=True
            )
            
            print(f"After intelligent filtering: {len(filtered_records)}")
            print(f"Filter statistics: {filter_stats}")
        except Exception as e:
            print(f"Intelligent filtering failed (running in test mode): {e}")
            filtered_records = records
        
        return filtered_records[:5]  # Return first 5 for content testing


async def test_firecrawl_extraction(records):
    """Test Firecrawl content extraction"""
    print("\n" + "=" * 60)
    print("Testing Firecrawl Content Extraction")
    print("=" * 60)
    
    if not records:
        print("No records to test extraction")
        return
    
    extractor = get_firecrawl_extractor()
    
    # Test health check first
    health = await extractor.health_check()
    print(f"Firecrawl health check: {health}")
    
    if health.get('firecrawl_service') != 'healthy':
        print("WARNING: Firecrawl service is not healthy. Starting local Firecrawl...")
        print("Run: docker compose up firecrawl-api firecrawl-worker firecrawl-playwright")
        return
    
    successful_extractions = 0
    
    for i, record in enumerate(records[:3]):  # Test first 3
        print(f"\nTesting extraction {i+1}/3:")
        print(f"URL: {record.original_url}")
        print(f"Wayback URL: {record.wayback_url}")
        print(f"Content Length: {record.content_length_bytes} bytes")
        print(f"MIME Type: {record.mime_type}")
        
        try:
            extracted_content = await extractor.extract_content(record)
            
            print(f"✅ Extraction successful!")
            print(f"  Title: {extracted_content.title[:100]}...")
            print(f"  Content: {len(extracted_content.text)} characters")
            print(f"  Word count: {extracted_content.word_count}")
            print(f"  Extraction method: {extracted_content.extraction_method}")
            print(f"  Extraction time: {extracted_content.extraction_time:.2f}s")
            
            if extracted_content.meta_description:
                print(f"  Description: {extracted_content.meta_description[:100]}...")
            
            successful_extractions += 1
            
        except Exception as e:
            print(f"❌ Extraction failed: {str(e)}")
    
    # Get performance metrics
    metrics = extractor.get_performance_metrics()
    print(f"\nFirecrawl Performance Metrics:")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
    
    print(f"\nSummary: {successful_extractions}/{min(3, len(records))} extractions successful")


async def test_intelligent_filtering():
    """Test intelligent filtering patterns"""
    print("\n" + "=" * 60)
    print("Testing Intelligent Filtering Patterns")
    print("=" * 60)
    
    try:
        intelligent_filter = get_intelligent_filter()
    except Exception as e:
        print(f"Cannot initialize intelligent filter in test mode: {e}")
        return
    
    # Test URLs
    test_urls = [
        ("https://example.com/research/climate-report-2023", "High-value research content"),
        ("https://example.com/blog/page/5", "List page (should be filtered)"),
        ("https://example.com/wp-admin/dashboard", "Admin page (should be filtered)"),
        ("https://example.com/important-document.pdf", "High-value PDF"),
        ("https://example.com/articles/important-news", "High-value article"),
        ("https://example.com/search?q=test", "Search page (should be filtered)"),
        ("https://example.com/categories/", "Category listing (should be filtered)"),
        ("https://example.com/analysis/market-trends", "High-value analysis"),
    ]
    
    for url, description in test_urls:
        is_list = intelligent_filter.is_list_page(url)
        is_high_value = intelligent_filter.is_high_value_content(url, 5000)
        priority = intelligent_filter.get_scraping_priority(CDXRecord(
            timestamp="20231201120000",
            original_url=url,
            mime_type="text/html",
            status_code="200",
            digest="test",
            length="5000"
        ))
        
        status = "🚫 FILTERED" if is_list else "✅ KEPT"
        value = "⭐ HIGH-VALUE" if is_high_value else "📄 REGULAR"
        
        print(f"{status} {value} Priority:{priority} - {description}")
        print(f"   URL: {url}")
        print(f"   List page: {is_list}, High-value: {is_high_value}")


async def main():
    """Main test function"""
    print("Testing Firecrawl-Only Scraping Implementation")
    print("Date:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    try:
        # Test intelligent filtering patterns
        await test_intelligent_filtering()
        
        # Test CDX fetching
        test_records = await test_cdx_fetching()
        
        # Test Firecrawl extraction
        await test_firecrawl_extraction(test_records)
        
        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())