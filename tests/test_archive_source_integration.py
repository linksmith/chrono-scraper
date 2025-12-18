#!/usr/bin/env python3
"""
Integration test for archive source fix.
This script tests the complete flow manually by creating test projects.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent / 'backend'
sys.path.insert(0, str(backend_path))

async def test_archive_source_integration():
    """Test archive source integration with database."""
    print("🧪 Testing Archive Source Integration")
    print("=" * 50)
    
    try:
        from app.core.database import get_db
        from app.models.project import Project, ArchiveSource
        from app.models.user import User
        from app.schemas.project import ProjectCreate
        from sqlmodel import select
        
        # Test data for different archive sources
        test_cases = [
            {
                'name': 'Test Wayback Project',
                'archive_source': ArchiveSource.WAYBACK_MACHINE,
                'description': 'Testing Wayback Machine'
            },
            {
                'name': 'Test CommonCrawl Project', 
                'archive_source': ArchiveSource.COMMON_CRAWL,
                'description': 'Testing Common Crawl'
            },
            {
                'name': 'Test Hybrid Project',
                'archive_source': ArchiveSource.HYBRID,
                'description': 'Testing Hybrid Mode'
            }
        ]
        
        async for db in get_db():
            # Get test user
            stmt = select(User).where(User.email == 'playwright@test.com')
            result = await db.execute(stmt)
            test_user = result.scalar_one_or_none()
            
            if not test_user:
                print("❌ Test user not found")
                return False
                
            print(f"✅ Found test user: {test_user.email}")
            
            # Test each archive source
            created_projects = []
            
            for test_case in test_cases:
                print(f"\n🔧 Testing {test_case['archive_source'].value}...")
                
                # Create project
                project = Project(
                    name=test_case['name'],
                    description=test_case['description'],
                    archive_source=test_case['archive_source'],
                    user_id=test_user.id
                )
                
                db.add(project)
                await db.commit()
                await db.refresh(project)
                created_projects.append(project)
                
                # Verify database persistence
                db_project = await db.get(Project, project.id)
                if db_project.archive_source == test_case['archive_source']:
                    print(f"✅ Database persistence: {db_project.archive_source.value}")
                else:
                    print(f"❌ Database mismatch: expected {test_case['archive_source'].value}, got {db_project.archive_source.value}")
                    return False
                
                # Verify serialization
                serialized = db_project.model_dump()
                if serialized['archive_source'] == test_case['archive_source'].value:
                    print(f"✅ Serialization: {serialized['archive_source']}")
                else:
                    print(f"❌ Serialization error: expected {test_case['archive_source'].value}, got {serialized['archive_source']}")
                    return False
                    
            print(f"\n🎉 Successfully created and verified {len(created_projects)} projects")
            
            # Clean up test projects
            for project in created_projects:
                await db.delete(project)
            await db.commit()
            print("✅ Cleaned up test projects")
            
            break
            
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enum_string_validation():
    """Test enum validation with string inputs."""
    print("\n🧪 Testing Enum String Validation")
    print("=" * 40)
    
    try:
        from app.models.project import ArchiveSource
        
        # Test valid string conversions
        test_strings = [
            ('wayback', ArchiveSource.WAYBACK_MACHINE),
            ('commoncrawl', ArchiveSource.COMMON_CRAWL),
            ('hybrid', ArchiveSource.HYBRID)
        ]
        
        for string_val, expected_enum in test_strings:
            try:
                result = ArchiveSource(string_val)
                if result == expected_enum:
                    print(f"✅ String '{string_val}' -> {result.value}")
                else:
                    print(f"❌ String '{string_val}' conversion failed")
                    return False
            except ValueError as e:
                print(f"❌ String '{string_val}' validation failed: {e}")
                return False
        
        # Test invalid string
        try:
            invalid_result = ArchiveSource('invalid_source')
            print(f"❌ Should have failed for invalid source, got: {invalid_result}")
            return False
        except ValueError:
            print("✅ Correctly rejected invalid archive source")
            
        return True
        
    except Exception as e:
        print(f"❌ Enum validation test failed: {e}")
        return False

async def main():
    """Run all integration tests."""
    print("🚀 Archive Source Integration Testing")
    print("=" * 60)
    
    all_passed = True
    
    # Test enum validation
    if not test_enum_string_validation():
        all_passed = False
    
    # Test database integration
    if not await test_archive_source_integration():
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 SUCCESS: All integration tests passed!")
        print("✅ Archive source fix is working correctly")
        return 0
    else:
        print("❌ FAILURE: Some integration tests failed")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)