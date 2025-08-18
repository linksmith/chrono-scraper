#!/usr/bin/env python3
"""
Test script to verify Meilisearch integration works properly
"""
import asyncio
import os
import sys
sys.path.append('backend')

from app.core.config import settings
from meilisearch_python_sdk import AsyncClient


async def test_meilisearch_connection():
    """Test basic Meilisearch connection and operations"""
    print("🔍 Testing Meilisearch integration...")
    
    try:
        # Initialize Meilisearch client
        client = AsyncClient(settings.MEILISEARCH_HOST, settings.MEILISEARCH_MASTER_KEY)
        
        # Test connection
        print(f"📡 Connecting to Meilisearch at {settings.MEILISEARCH_HOST}")
        health = await client.health()
        print(f"✅ Meilisearch health status: {health['status']}")
        
        # List existing indexes
        indexes = await client.get_indexes()
        print(f"📚 Found {len(indexes.results)} existing indexes:")
        for index in indexes.results:
            print(f"  - {index.uid} ({index.primary_key})")
        
        # Test creating a sample index for pages
        index_uid = "test_pages"
        print(f"🔧 Creating test index '{index_uid}'...")
        
        # Check if index exists and delete if it does
        try:
            await client.get_index(index_uid)
            await client.delete_index(index_uid)
            print(f"🗑️  Deleted existing test index")
        except:
            pass
        
        # Create new test index
        index = await client.create_index(index_uid, primary_key="id")
        print(f"✅ Created test index: {index.uid}")
        
        # Add sample documents
        sample_docs = [
            {
                "id": "1",
                "title": "Test Page 1",
                "url": "https://example.com/page1",
                "domain": "example.com",
                "content_preview": "This is a test page for OSINT investigation",
                "scraped_at": 1640995200,  # 2022-01-01
                "word_count": 250,
                "content_type": "text/html",
                "language": "en",
                "status_code": 200,
                "project_name": "Test Project"
            },
            {
                "id": "2", 
                "title": "Test Page 2",
                "url": "https://example.org/research",
                "domain": "example.org",
                "content_preview": "Research document with important findings for investigation",
                "scraped_at": 1640995800,  # 2022-01-01
                "word_count": 500,
                "content_type": "text/html", 
                "language": "en",
                "status_code": 200,
                "project_name": "OSINT Research"
            }
        ]
        
        print(f"📝 Adding {len(sample_docs)} test documents...")
        await client.index(index_uid).add_documents(sample_docs)
        
        # Wait for indexing to complete
        await asyncio.sleep(1)
        
        # Test search functionality
        print(f"🔍 Testing search functionality...")
        search_results = await client.index(index_uid).search("test investigation")
        print(f"✅ Search returned {search_results.hits_count} results")
        
        for hit in search_results.hits:
            print(f"  - {hit['title']}: {hit['content_preview'][:50]}...")
        
        # Test filtering
        print(f"🔍 Testing filtered search...")
        filtered_results = await client.index(index_uid).search(
            "research",
            filter="domain = example.org"
        )
        print(f"✅ Filtered search returned {filtered_results.hits_count} results")
        
        # Test faceted search
        print(f"🔍 Testing faceted search...")
        faceted_results = await client.index(index_uid).search(
            "",
            facets=["domain", "content_type", "language"]
        )
        print(f"✅ Faceted search found {len(faceted_results.facet_distribution or {})} facet categories")
        
        # Cleanup
        print(f"🗑️  Cleaning up test index...")
        await client.delete_index(index_uid)
        
        print("✅ Meilisearch integration test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Meilisearch integration test failed: {e}")
        return False


async def test_fastapi_integration():
    """Test meilisearch-fastapi integration"""
    print("🚀 Testing meilisearch-fastapi integration...")
    
    try:
        # Import meilisearch-fastapi components
        from meilisearch_fastapi import search_routes, index_routes
        print("✅ meilisearch-fastapi imports successful")
        
        # Test route creation (this verifies the package structure)
        router = search_routes.router
        print(f"✅ Search routes created with {len(router.routes)} endpoints")
        
        return True
        
    except Exception as e:
        print(f"❌ meilisearch-fastapi integration test failed: {e}")
        return False


async def main():
    """Run all integration tests"""
    print("🧪 Starting Meilisearch integration tests...\n")
    
    # Test basic Meilisearch connection
    meilisearch_ok = await test_meilisearch_connection()
    print()
    
    # Test FastAPI integration
    fastapi_ok = await test_fastapi_integration()
    print()
    
    if meilisearch_ok and fastapi_ok:
        print("🎉 All integration tests passed!")
        print("📋 Next steps:")
        print("  1. Navigate to http://localhost:5173/search to test the frontend")
        print("  2. Check the API docs at http://localhost:8000/docs for Meilisearch endpoints")
        print("  3. Start indexing your scraped pages data into Meilisearch")
        return 0
    else:
        print("❌ Some integration tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)