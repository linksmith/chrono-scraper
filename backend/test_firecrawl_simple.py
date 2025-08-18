#!/usr/bin/env python3
"""
Simple test script for Firecrawl integration
"""
import asyncio
import sys
import os

# Add the backend directory to Python path
sys.path.append('/home/bizon/Development/chrono-scraper-fastapi-2/backend')

async def test_firecrawl_extractor():
    """Test the Firecrawl extractor directly"""
    print("=== Testing Firecrawl Extractor ===")
    
    try:
        from app.services.firecrawl_extractor import get_firecrawl_extractor
        from app.services.wayback_machine import CDXRecord
        
        # Create a test CDX record
        test_record = CDXRecord(
            timestamp="20230601123000",
            original_url="https://example.com",
            mime_type="text/html",
            status_code="200",
            digest="ABCD1234",
            length="1024"
        )
        
        # Get the extractor
        extractor = get_firecrawl_extractor()
        print(f"✅ Extractor initialized: {extractor.config.firecrawl_url}")
        
        # Test health check
        health = await extractor.health_check()
        print(f"Health check: {health}")
        
        # Test content extraction
        print(f"Testing extraction of: {test_record.original_url}")
        result = await extractor.extract_content(test_record)
        
        print(f"✅ Extraction completed!")
        print(f"Title: {result.title}")
        print(f"Text length: {len(result.text) if result.text else 0}")
        print(f"Word count: {result.word_count}")
        print(f"Extraction method: {result.extraction_method}")
        
        if result.text:
            print(f"Content preview: {result.text[:200]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_basic_connection():
    """Test basic connection to Firecrawl"""
    print("\n=== Testing Basic Connection ===")
    
    try:
        import httpx
        
        async with httpx.AsyncClient(timeout=10) as client:
            # Test API root (from inside container, use service name)
            response = await client.get("http://firecrawl-api:3002/")
            print(f"API root status: {response.status_code}")
            print(f"Response: {response.text}")
            
            if "SCRAPERS-JS" in response.text:
                print("✅ Firecrawl API is responding")
                return True
            else:
                print("❌ Unexpected response")
                return False
                
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🚀 FIRECRAWL INTEGRATION TEST")
    print("=" * 40)
    
    results = {}
    results['connection'] = await test_basic_connection()
    results['extractor'] = await test_firecrawl_extractor()
    
    print("\n" + "=" * 40)
    print("📊 RESULTS")
    print("=" * 40)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name.upper()}: {status}")
    
    passed = sum(results.values())
    total = len(results)
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 Firecrawl integration is working!")
    else:
        print("🔧 Some issues found - check output above")

if __name__ == "__main__":
    asyncio.run(main())