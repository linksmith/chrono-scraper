#!/usr/bin/env python3
"""
Test script to verify intelligent extraction performance improvements
"""
import asyncio
import time
import logging
from typing import List

from app.services.firecrawl_extractor import get_firecrawl_extractor
from app.services.wayback_machine import CDXRecord

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test URLs from Archive.org
TEST_URLS = [
    "https://web.archive.org/web/20240101120000/https://www.bbc.com/news",
    "https://web.archive.org/web/20240101120000/https://www.cnn.com/",
    "https://web.archive.org/web/20240101120000/https://www.reuters.com/",
    "https://web.archive.org/web/20240101120000/https://www.theguardian.com/",
    "https://web.archive.org/web/20240101120000/https://www.nytimes.com/"
]

def create_test_cdx_record(content_url: str, original_url: str) -> CDXRecord:
    """Create a test CDX record"""
    return CDXRecord(
        timestamp="20240101120000",
        original_url=original_url,
        mime_type="text/html",
        status_code="200",
        digest="ABCDEF123456",
        length="50000"
    )

async def test_extraction_performance():
    """Test intelligent extraction performance"""
    print("\n🚀 Testing Intelligent Extraction Performance")
    print("=" * 60)
    
    # Create test CDX records
    test_records = []
    for url in TEST_URLS:
        original_url = url.split('/web/')[1].split('/')[1] if '/web/' in url else url
        test_records.append(create_test_cdx_record(url, original_url))
    
    # Get extractor instance
    extractor = get_firecrawl_extractor()
    
    # Test extraction performance
    start_time = time.time()
    successful_extractions = 0
    failed_extractions = 0
    total_word_count = 0
    extraction_methods = []
    
    print(f"📊 Processing {len(test_records)} test URLs...")
    print()
    
    for i, record in enumerate(test_records, 1):
        try:
            print(f"[{i}/{len(test_records)}] Processing: {record.original_url}")
            
            extraction_start = time.time()
            result = await extractor.extract_content(record)
            extraction_time = time.time() - extraction_start
            
            if result.text and result.word_count > 50:
                successful_extractions += 1
                total_word_count += result.word_count
                extraction_methods.append(result.extraction_method)
                
                print(f"  ✅ Success: {result.word_count:,} words in {extraction_time:.3f}s")
                print(f"     Method: {result.extraction_method}")
                print(f"     Title: {result.title[:50]}..." if result.title else "     No title")
                if result.language:
                    print(f"     Language: {result.language}")
            else:
                failed_extractions += 1
                print(f"  ❌ Failed: Insufficient content ({result.word_count} words)")
                
        except Exception as e:
            failed_extractions += 1
            print(f"  ❌ Error: {str(e)}")
        
        print()
    
    total_time = time.time() - start_time
    
    # Performance metrics
    print("📈 Performance Results")
    print("=" * 60)
    print(f"Total Processing Time: {total_time:.2f} seconds")
    print(f"Average Time per URL: {total_time/len(test_records):.3f} seconds")
    print(f"Processing Rate: {len(test_records)/total_time:.1f} URLs/second")
    print()
    print(f"Successful Extractions: {successful_extractions}")
    print(f"Failed Extractions: {failed_extractions}")
    print(f"Success Rate: {(successful_extractions/len(test_records)*100):.1f}%")
    print()
    print(f"Total Words Extracted: {total_word_count:,}")
    print(f"Average Words per Page: {total_word_count/max(successful_extractions, 1):,.0f}")
    
    # Extraction methods used
    if extraction_methods:
        method_counts = {}
        for method in extraction_methods:
            method_counts[method] = method_counts.get(method, 0) + 1
        
        print("\n🔧 Extraction Methods Used:")
        for method, count in method_counts.items():
            print(f"  {method}: {count} pages ({count/len(extraction_methods)*100:.1f}%)")
    
    # Performance comparison with historical Firecrawl
    print("\n⚡ Performance Comparison:")
    print("  Intelligent Extraction (Current):")
    print(f"    - Average: {total_time/len(test_records):.3f}s per page")
    print(f"    - Rate: {len(test_records)/total_time:.1f} pages/sec")
    print(f"    - Success: {(successful_extractions/len(test_records)*100):.1f}%")
    print("  ")
    print("  Historical Firecrawl Performance:")
    print("    - Average: ~15.25s per page")
    print("    - Rate: ~0.1 pages/sec")
    print("    - Success: ~70%")
    print()
    
    if total_time > 0:
        speed_improvement = (15.25 / (total_time/len(test_records)))
        print(f"🏆 Speed Improvement: {speed_improvement:.1f}x faster!")
        
        if successful_extractions > 0:
            success_improvement = ((successful_extractions/len(test_records)) / 0.70)
            print(f"🎯 Success Rate Improvement: {success_improvement:.1f}x better!")

if __name__ == "__main__":
    print("🧪 Chrono Scraper - Intelligent Extraction Performance Test")
    
    try:
        asyncio.run(test_extraction_performance())
        print("\n✅ Test completed successfully!")
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()