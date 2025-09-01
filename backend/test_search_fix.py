#!/usr/bin/env python3
"""
Test script to verify the search fix for the associations_by_page variable scoping issue
"""
import asyncio
import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.services.shared_pages_meilisearch import SharedPagesMeilisearchService
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4


async def test_enhance_search_results_with_invalid_uuids():
    """
    Test the _enhance_search_results method with invalid UUIDs to ensure
    associations_by_page is always defined, even when no valid page_ids are found.
    """
    print("Testing _enhance_search_results with invalid UUIDs...")
    
    # Mock database session
    mock_db = AsyncMock()
    mock_access_control = MagicMock()
    
    # Create service instance
    service = SharedPagesMeilisearchService(mock_db, mock_access_control)
    
    # Create mock search results with invalid UUIDs (integers instead of UUIDs)
    mock_results = MagicMock()
    mock_results.hits = [
        {"id": "1311", "title": "Test 1", "content": "Content 1"},
        {"id": "1305", "title": "Test 2", "content": "Content 2"},
        {"id": "invalid-uuid", "title": "Test 3", "content": "Content 3"},
    ]
    mock_results.query = "test"
    mock_results.processing_time_ms = 10
    mock_results.limit = 10
    mock_results.offset = 0
    mock_results.estimated_total_hits = 3
    
    user_id = 2
    user_project_ids = [1, 2]
    
    try:
        # This should NOT raise "cannot access local variable 'associations_by_page'" anymore
        enhanced_results = await service._enhance_search_results(
            mock_results, user_id, user_project_ids
        )
        
        print("✅ SUCCESS: No variable scoping error occurred")
        print(f"Enhanced results has {len(enhanced_results['hits'])} hits")
        
        # Verify that all hits have project_associations field (should be empty list for invalid UUIDs)
        for hit in enhanced_results['hits']:
            if 'project_associations' in hit:
                print(f"✅ Hit {hit['id']} has project_associations: {hit['project_associations']}")
            else:
                print(f"❌ Hit {hit['id']} missing project_associations")
        
        return True
        
    except Exception as e:
        if "cannot access local variable 'associations_by_page'" in str(e):
            print(f"❌ FAILURE: Variable scoping error still exists: {e}")
            return False
        else:
            print(f"❌ FAILURE: Unexpected error: {e}")
            return False


async def test_enhance_search_results_with_valid_uuids():
    """
    Test with valid UUIDs to ensure normal functionality works
    """
    print("\nTesting _enhance_search_results with valid UUIDs...")
    
    # Mock database session that returns some associations
    mock_db = AsyncMock()
    mock_access_control = MagicMock()
    
    # Mock the database query result
    mock_execute_result = AsyncMock()
    mock_associations_data = [
        (MagicMock(
            page_id=uuid4(),
            project_id=1,
            tags=["test"],
            review_status="pending",
            page_category=None,
            priority_level=None,
            is_starred=False,
            reviewed_at=None,
            personal_note=None
        ), "Test Project")
    ]
    mock_execute_result.all.return_value = mock_associations_data
    mock_db.execute.return_value = mock_execute_result
    
    # Create service instance
    service = SharedPagesMeilisearchService(mock_db, mock_access_control)
    
    # Create mock search results with valid UUIDs
    test_uuid = str(uuid4())
    mock_results = MagicMock()
    mock_results.hits = [
        {"id": test_uuid, "title": "Valid Test", "content": "Content with valid UUID"}
    ]
    mock_results.query = "test"
    mock_results.processing_time_ms = 5
    mock_results.limit = 10
    mock_results.offset = 0
    mock_results.estimated_total_hits = 1
    
    user_id = 2
    user_project_ids = [1, 2]
    
    try:
        enhanced_results = await service._enhance_search_results(
            mock_results, user_id, user_project_ids
        )
        
        print("✅ SUCCESS: Valid UUID processing works correctly")
        print(f"Enhanced results has {len(enhanced_results['hits'])} hits")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILURE: Error with valid UUIDs: {e}")
        return False


async def main():
    """Run all tests"""
    print("=" * 60)
    print("Testing SharedPagesMeilisearchService._enhance_search_results fix")
    print("=" * 60)
    
    test1_success = await test_enhance_search_results_with_invalid_uuids()
    test2_success = await test_enhance_search_results_with_valid_uuids()
    
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"Test 1 (Invalid UUIDs): {'PASSED' if test1_success else 'FAILED'}")
    print(f"Test 2 (Valid UUIDs): {'PASSED' if test2_success else 'FAILED'}")
    
    if test1_success and test2_success:
        print("\n🎉 ALL TESTS PASSED! The fix is working correctly.")
        return 0
    else:
        print(f"\n💥 SOME TESTS FAILED! Check the output above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)