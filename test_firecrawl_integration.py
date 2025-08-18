#!/usr/bin/env python3
"""
Test script to verify Firecrawl integration with our scraping system
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the backend app to the Python path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.firecrawl_extractor import FirecrawlExtractor
from app.models.scraping import ScrapeSession, ScrapePage
from app.core.database import get_db_session
from sqlmodel import select
import json

async def test_firecrawl_integration():
    """Test the complete Firecrawl integration"""
    print("🔥 Testing Firecrawl Integration")
    
    # Initialize extractor
    try:
        extractor = FirecrawlExtractor()
        print(f"✅ FirecrawlExtractor initialized")
        print(f"   API URL: {extractor.api_url}")
        print(f"   API Key configured: {'Yes' if extractor.api_key else 'No'}")
    except Exception as e:
        print(f"❌ Failed to initialize FirecrawlExtractor: {e}")
        return False
    
    # Test simple URL scraping
    test_url = "https://example.com"
    print(f"\n🌐 Testing scrape on: {test_url}")
    
    try:
        result = await extractor.extract_content(
            url=test_url,
            formats=['markdown', 'html']
        )
        
        if result.get('success'):
            print("✅ Scraping successful!")
            print(f"   Content length: {len(result.get('content', ''))} characters")
            print(f"   Title: {result.get('metadata', {}).get('title', 'No title')}")
            print(f"   Quality score: {result.get('quality_score', 'N/A')}")
            
            # Test metadata extraction
            if result.get('metadata'):
                metadata = result['metadata']
                print(f"   Metadata keys: {list(metadata.keys())}")
        else:
            error = result.get('error', 'Unknown error')
            print(f"❌ Scraping failed: {error}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during scraping: {e}")
        return False
    
    # Test Wayback Machine URL
    wayback_url = "https://web.archive.org/web/20240101120000/https://example.com"
    print(f"\n📅 Testing Wayback Machine URL: {wayback_url}")
    
    try:
        result = await extractor.extract_content(
            url=wayback_url,
            formats=['markdown']
        )
        
        if result.get('success'):
            print("✅ Wayback Machine scraping successful!")
            print(f"   Content length: {len(result.get('content', ''))} characters")
        else:
            print(f"⚠️ Wayback Machine scraping failed: {result.get('error')}")
            # This might be expected due to service issues
            
    except Exception as e:
        print(f"⚠️ Exception during Wayback scraping: {e}")
        # Continue - this might be expected
    
    # Test database integration
    print(f"\n💾 Testing database integration")
    
    try:
        async with get_db_session() as session:
            # Check for existing scrape sessions
            result = await session.exec(select(ScrapeSession).limit(5))
            sessions = result.fetchall()
            print(f"✅ Found {len(sessions)} scrape sessions in database")
            
            # Check for scrape pages
            result = await session.exec(select(ScrapePage).limit(5))  
            pages = result.fetchall()
            print(f"✅ Found {len(pages)} scrape pages in database")
            
            if sessions:
                latest_session = sessions[0]
                print(f"   Latest session ID: {latest_session.id}")
                print(f"   Status: {latest_session.status}")
                print(f"   Progress: {latest_session.processed_pages}/{latest_session.total_cdx_records}")
                
    except Exception as e:
        print(f"❌ Database integration test failed: {e}")
        return False
    
    print(f"\n🎉 Firecrawl integration test completed!")
    return True

if __name__ == "__main__":
    success = asyncio.run(test_firecrawl_integration())
    sys.exit(0 if success else 1)