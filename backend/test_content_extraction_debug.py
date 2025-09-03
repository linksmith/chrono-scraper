#!/usr/bin/env python3
"""
Debug script to test content extraction with specific failing URL
"""
import asyncio
import logging
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

from app.services.content_extraction_service import get_content_extraction_service
from app.services.wayback_machine import CDXRecord
from app.core.config import settings

async def test_content_extraction():
    """Test content extraction with the specific failing URL"""
    
    # Set proxy configuration for testing
    settings.PROXY_SERVER = "gate.decodo.com:10001"
    settings.PROXY_USERNAME = "spe6jd38wb"
    settings.PROXY_PASSWORD = "fHhjxQFxf5z~3Lo5e1"
    
    print("=== Content Extraction Debug Test ===")
    print(f"Proxy Server: {settings.PROXY_SERVER}")
    print(f"Proxy Username: {settings.PROXY_USERNAME}")
    print(f"Proxy Password: {'***' if settings.PROXY_PASSWORD else None}")
    print()
    
    # Create test CDX record with the failing URL
    test_url = "https://web.archive.org/web/20240422163345if_/https://hetstoerwoud.nl/en/about-us/"
    cdx_record = CDXRecord(
        original_url="https://hetstoerwoud.nl/en/about-us/",
        timestamp="20240422163345",
        mime_type="text/html",
        status_code="200",
        digest="test-digest",
        length="1000"
    )
    
    print(f"Testing URL: {test_url}")
    print(f"Original URL: {cdx_record.original_url}")
    print()
    
    try:
        # Get the content extraction service
        extraction_service = get_content_extraction_service()
        
        # Test content extraction
        print("Starting content extraction...")
        result = await extraction_service.extract_content(cdx_record)
        
        print(f"\n=== Extraction Results ===")
        print(f"Title: {result.title}")
        print(f"Word Count: {result.word_count}")
        print(f"Extraction Method: {result.extraction_method}")
        print(f"Processing Time: {result.extraction_time:.3f}s")
        print(f"Error: {result.error}")
        
        if result.text:
            print(f"\n=== Content Preview (first 500 chars) ===")
            print(result.text[:500])
            print("...")
        else:
            print("\n=== No text content extracted ===")
        
        # Display service metrics
        metrics = extraction_service.get_metrics()
        print(f"\n=== Service Metrics ===")
        for key, value in metrics.items():
            print(f"{key}: {value}")
        
        return result.word_count > 50
        
    except Exception as e:
        print(f"\n=== Test Failed ===")
        print(f"Error: {e}")
        import traceback
        print(f"Stack trace:\n{traceback.format_exc()}")
        return False

async def test_direct_curl_comparison():
    """Test if we can replicate the curl command behavior"""
    import httpx
    
    print("\n=== Direct HTTP Test (Similar to curl) ===")
    
    # Proxy configuration for httpx
    proxy_url = f"http://spe6jd38wb:fHhjxQFxf5z~3Lo5e1@gate.decodo.com:10001"
    
    test_url = "https://web.archive.org/web/20240422163345if_/https://hetstoerwoud.nl/en/about-us/"
    
    client_kwargs = {
        "timeout": 60,
        "follow_redirects": True,
        "proxy": proxy_url,  # httpx uses "proxy" not "proxies"
        "headers": {
            "User-Agent": "Mozilla/5.0 (compatible; ChronoScraper/2.0; Debug Test)"
        }
    }
    
    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            print(f"Attempting direct fetch of: {test_url}")
            response = await client.get(test_url)
            
            print(f"Status Code: {response.status_code}")
            print(f"Content Length: {len(response.content)}")
            print(f"Content Type: {response.headers.get('content-type')}")
            print(f"Response Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                content = response.text
                print(f"HTML Content Length: {len(content)} characters")
                print(f"Content Preview (first 500 chars):\n{content[:500]}")
                return len(content) > 1000
            else:
                print(f"Request failed with status {response.status_code}")
                print(f"Response body: {response.text[:1000]}")
                return False
                
    except Exception as e:
        print(f"Direct HTTP test failed: {e}")
        import traceback
        print(f"Stack trace:\n{traceback.format_exc()}")
        return False

if __name__ == "__main__":
    print("Starting content extraction debug tests...")
    
    # First test direct HTTP fetch
    direct_success = asyncio.run(test_direct_curl_comparison())
    print(f"\nDirect HTTP Test Success: {direct_success}")
    
    # Then test full content extraction
    extraction_success = asyncio.run(test_content_extraction())
    print(f"\nContent Extraction Test Success: {extraction_success}")
    
    if direct_success and not extraction_success:
        print("\n=== Analysis ===")
        print("✓ Direct HTTP fetch works")
        print("✗ Content extraction fails")
        print("→ Issue is likely in the content extraction/parsing logic")
    elif not direct_success:
        print("\n=== Analysis ===")
        print("✗ Direct HTTP fetch fails")
        print("→ Issue is likely in proxy configuration or network connectivity")
    else:
        print("\n=== Analysis ===")
        print("✓ Both tests passed - extraction should be working!")