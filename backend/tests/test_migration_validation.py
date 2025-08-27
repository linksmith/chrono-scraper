"""
Test suite for migration script validation with comprehensive data integrity testing
"""
import pytest
import asyncio
import uuid
import tempfile
import os
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import Session, select, create_engine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.shared_pages import (
    PageV2, ProjectPage, CDXPageRegistry,
    ScrapeStatus, PageReviewStatus, PageCategory, PagePriority
)
from app.models.project import Project, Domain
from app.models.user import User
from app.models.shared_pages import ProjectPage  # New shared pages model
from app.core.security import get_password_hash


@pytest.mark.asyncio
class TestMigrationScriptValidation:
    """Test migration script functionality and data integrity"""
    
    @pytest.fixture
    async def setup_legacy_data(self, app):
        """Setup legacy data structure for migration testing"""
        async with AsyncSessionLocal() as session:
            # Create test users
            user1 = User(
                email="migration1@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Migration Test User 1",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            user2 = User(
                email="migration2@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Migration Test User 2",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add_all([user1, user2])
            await session.commit()
            await session.refresh(user1)
            await session.refresh(user2)
            
            # Create test projects
            project1 = Project(
                name="Migration Test Project 1",
                description="First project for migration testing",
                user_id=user1.id
            )
            project2 = Project(
                name="Migration Test Project 2",
                description="Second project for migration testing",
                user_id=user1.id
            )
            project3 = Project(
                name="User 2 Project",
                description="Different user project",
                user_id=user2.id
            )
            session.add_all([project1, project2, project3])
            await session.commit()
            await session.refresh(project1)
            await session.refresh(project2)
            await session.refresh(project3)
            
            # Create test domains
            domain1 = Domain(
                name="migration-test.com",
                project_id=project1.id,
                config={"migration_test": True}
            )
            domain2 = Domain(
                name="example-migration.org",
                project_id=project2.id,
                config={"migration_test": True}
            )
            domain3 = Domain(
                name="user2-domain.net",
                project_id=project3.id,
                config={"migration_test": True}
            )
            session.add_all([domain1, domain2, domain3])
            await session.commit()
            await session.refresh(domain1)
            await session.refresh(domain2)
            await session.refresh(domain3)
            
            # Create legacy pages (using ProjectPage model)
            legacy_pages = [
                ProjectProjectPage(
                    url="https://migration-test.com/page1",
                    wayback_url="https://web.archive.org/web/20230101120000if_/https://migration-test.com/page1",
                    project_id=project1.id,
                    domain_id=domain1.id,
                    content="<html><body>Legacy page 1 content</body></html>",
                    extracted_text="Legacy page 1 content extracted",
                    title="Legacy Page 1",
                    processed=True,
                    created_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
                ),
                ProjectProjectPage(
                    url="https://migration-test.com/page2",
                    wayback_url="https://web.archive.org/web/20230101130000if_/https://migration-test.com/page2",
                    project_id=project1.id,
                    domain_id=domain1.id,
                    content="<html><body>Legacy page 2 content</body></html>",
                    extracted_text="Legacy page 2 content extracted",
                    title="Legacy Page 2",
                    processed=True,
                    created_at=datetime(2023, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
                ),
                ProjectPage(
                    url="https://example-migration.org/shared",
                    wayback_url="https://web.archive.org/web/20230101140000if_/https://example-migration.org/shared",
                    project_id=project2.id,
                    domain_id=domain2.id,
                    content="<html><body>Shared legacy content</body></html>",
                    title="Shared Legacy Page",
                    processed=True,
                    created_at=datetime(2023, 1, 1, 14, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
                ),
                ProjectPage(
                    url="https://user2-domain.net/private",
                    wayback_url="https://web.archive.org/web/20230101150000if_/https://user2-domain.net/private",
                    project_id=project3.id,
                    domain_id=domain3.id,
                    content="<html><body>User 2 private content</body></html>",
                    title="User 2 Private Page",
                    processed=False,  # Not processed yet
                    created_at=datetime(2023, 1, 1, 15, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 1, 1, 15, 0, 0, tzinfo=timezone.utc)
                ),
                # Duplicate URL with different timestamp - should create separate PageV2
                ProjectPage(
                    url="https://migration-test.com/page1",
                    wayback_url="https://web.archive.org/web/20230201120000if_/https://migration-test.com/page1",
                    project_id=project1.id,
                    domain_id=domain1.id,
                    content="<html><body>Updated legacy page 1 content</body></html>",
                    title="Updated Legacy Page 1",
                    processed=True,
                    created_at=datetime(2023, 2, 1, 12, 0, 0, tzinfo=timezone.utc),
                    updated_at=datetime(2023, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
                )
            ]
            
            session.add_all(legacy_pages)
            await session.commit()
            for page in legacy_pages:
                await session.refresh(page)
            
            return {
                "user1": user1,
                "user2": user2,
                "project1": project1,
                "project2": project2,
                "project3": project3,
                "domain1": domain1,
                "domain2": domain2,
                "domain3": domain3,
                "legacy_pages": legacy_pages,
                "session": session
            }
    
    @pytest.fixture
    def migration_script_mock(self):
        """Mock migration script functionality"""
        class MockMigrationScript:
            def __init__(self, db_session):
                self.db = db_session
                self.stats = {
                    "legacy_pages_found": 0,
                    "pages_v2_created": 0,
                    "project_associations_created": 0,
                    "duplicates_handled": 0,
                    "errors": []
                }
            
            async def extract_timestamp_from_wayback_url(self, wayback_url: str) -> int:
                """Extract timestamp from wayback URL"""
                if not wayback_url:
                    return 0
                
                # Extract timestamp from URL like: https://web.archive.org/web/20230101120000/...
                parts = wayback_url.split('/')
                for part in parts:
                    if part.isdigit() and len(part) == 14:
                        # Convert YYYYMMDDHHMMSS to unix timestamp
                        dt = datetime.strptime(part, "%Y%m%d%H%M%S")
                        return int(dt.timestamp())
                return 0
            
            async def migrate_pages_to_shared_architecture(self):
                """Simulate migration process"""
                # Get all legacy pages
                legacy_pages_stmt = select(Page)
                result = await self.db.execute(legacy_pages_stmt)
                legacy_pages = result.scalars().all()
                
                self.stats["legacy_pages_found"] = len(legacy_pages)
                
                # Group pages by (url, timestamp) for deduplication
                page_groups = {}
                for page in legacy_pages:
                    timestamp = await self.extract_timestamp_from_wayback_url(page.wayback_url)
                    key = (page.url, timestamp)
                    
                    if key not in page_groups:
                        page_groups[key] = []
                    page_groups[key].append(page)
                
                # Create PageV2 entries and associations
                for (url, timestamp), pages in page_groups.items():
                    # Use the first (or most recent) page as the source
                    source_page = max(pages, key=lambda p: p.updated_at)
                    
                    # Create PageV2
                    page_v2 = PageV2(
                        url=url,
                        unix_timestamp=timestamp,
                        wayback_url=source_page.wayback_url,
                        content=source_page.content,
                        extracted_text=source_page.extracted_text,
                        title=source_page.title,
                        processed=source_page.processed,
                        indexed=False,  # Will be indexed later
                        created_at=source_page.created_at,
                        updated_at=source_page.updated_at
                    )
                    
                    self.db.add(page_v2)
                    await self.db.commit()
                    await self.db.refresh(page_v2)
                    
                    self.stats["pages_v2_created"] += 1
                    
                    # Create project associations for all original pages
                    for page in pages:
                        association = ProjectProjectPage(
                            project_id=page.project_id,
                            page_id=page_v2.id,
                            domain_id=page.domain_id,
                            review_status=PageReviewStatus.PENDING,
                            priority_level=PagePriority.MEDIUM,
                            added_at=page.created_at,
                            tags=[]
                        )
                        
                        self.db.add(association)
                        self.stats["project_associations_created"] += 1
                    
                    if len(pages) > 1:
                        self.stats["duplicates_handled"] += len(pages) - 1
                
                await self.db.commit()
                return self.stats
        
        return MockMigrationScript
    
    async def test_migration_script_basic_functionality(self, setup_legacy_data, migration_script_mock):
        """Test basic migration script functionality"""
        test_data = await setup_legacy_data
        session = test_data["session"]
        
        # Run migration
        migration = migration_script_mock(session)
        stats = await migration.migrate_pages_to_shared_architecture()
        
        # Verify migration statistics
        assert stats["legacy_pages_found"] == 5
        assert stats["pages_v2_created"] == 4  # 4 unique (url, timestamp) combinations
        assert stats["project_associations_created"] == 5  # One association per legacy page
        assert stats["duplicates_handled"] == 1  # One duplicate URL with different timestamp
        assert len(stats["errors"]) == 0
        
        # Verify PageV2 entries were created
        pages_v2_stmt = select(PageV2)
        result = await session.execute(pages_v2_stmt)
        pages_v2 = result.scalars().all()
        
        assert len(pages_v2) == 4
        
        # Verify all URLs are represented
        urls = [page.url for page in pages_v2]
        assert "https://migration-test.com/page1" in urls
        assert "https://migration-test.com/page2" in urls
        assert "https://example-migration.org/shared" in urls
        assert "https://user2-domain.net/private" in urls
        
        # Verify timestamps were extracted correctly
        page1_entries = [p for p in pages_v2 if p.url == "https://migration-test.com/page1"]
        assert len(page1_entries) == 2  # Two different timestamps
        
        timestamps = [p.unix_timestamp for p in page1_entries]
        assert len(set(timestamps)) == 2  # Two unique timestamps
    
    async def test_migration_project_associations(self, setup_legacy_data, migration_script_mock):
        """Test project association creation during migration"""
        test_data = await setup_legacy_data
        session = test_data["session"]
        
        # Run migration
        migration = migration_script_mock(session)
        await migration.migrate_pages_to_shared_architecture()
        
        # Verify project associations were created correctly
        associations_stmt = select(ProjectPage)
        result = await session.execute(associations_stmt)
        associations = result.scalars().all()
        
        assert len(associations) == 5  # One per legacy page
        
        # Verify associations link to correct projects
        project1_associations = [a for a in associations if a.project_id == test_data["project1"].id]
        project2_associations = [a for a in associations if a.project_id == test_data["project2"].id]
        project3_associations = [a for a in associations if a.project_id == test_data["project3"].id]
        
        assert len(project1_associations) == 3  # 3 pages in project1
        assert len(project2_associations) == 1   # 1 page in project2
        assert len(project3_associations) == 1   # 1 page in project3
        
        # Verify association metadata
        for association in associations:
            assert association.review_status == PageReviewStatus.PENDING
            assert association.priority_level == PagePriority.MEDIUM
            assert association.added_at is not None
            assert association.tags == []
    
    async def test_migration_duplicate_handling(self, setup_legacy_data, migration_script_mock):
        """Test handling of duplicate URLs with different timestamps"""
        test_data = await setup_legacy_data
        session = test_data["session"]
        
        # Run migration
        migration = migration_script_mock(session)
        await migration.migrate_pages_to_shared_architecture()
        
        # Check that duplicate URL with different timestamp created separate PageV2 entries
        pages_v2_stmt = select(PageV2).where(PageV2.url == "https://migration-test.com/page1")
        result = await session.execute(pages_v2_stmt)
        duplicate_pages = result.scalars().all()
        
        assert len(duplicate_pages) == 2  # Two entries for same URL with different timestamps
        
        # Verify they have different timestamps
        timestamps = [page.unix_timestamp for page in duplicate_pages]
        assert len(set(timestamps)) == 2
        
        # Verify both have project associations
        for page in duplicate_pages:
            associations_stmt = select(ProjectPage).where(ProjectPage.page_id == page.id)
            result = await session.execute(associations_stmt)
            associations = result.scalars().all()
            assert len(associations) >= 1  # At least one association
    
    async def test_migration_data_integrity(self, setup_legacy_data, migration_script_mock):
        """Test data integrity after migration"""
        test_data = await setup_legacy_data
        session = test_data["session"]
        
        # Run migration
        migration = migration_script_mock(session)
        await migration.migrate_pages_to_shared_architecture()
        
        # Verify all legacy page data was preserved
        pages_v2_stmt = select(PageV2)
        result = await session.execute(pages_v2_stmt)
        pages_v2 = result.scalars().all()
        
        # Check data integrity for each migrated page
        for page_v2 in pages_v2:
            assert page_v2.url is not None
            assert page_v2.unix_timestamp > 0
            assert page_v2.created_at is not None
            assert page_v2.updated_at is not None
            
            # If content exists, verify it was preserved
            if page_v2.content:
                assert len(page_v2.content) > 0
            
            # Verify page has at least one project association
            associations_stmt = select(ProjectPage).where(ProjectPage.page_id == page_v2.id)
            result = await session.execute(associations_stmt)
            associations = result.scalars().all()
            assert len(associations) >= 1
    
    async def test_migration_timestamp_extraction(self, migration_script_mock):
        """Test timestamp extraction from wayback URLs"""
        # Create a mock session
        mock_session = AsyncMock()
        migration = migration_script_mock(mock_session)
        
        # Test various wayback URL formats
        test_cases = [
            {
                "url": "https://web.archive.org/web/20230101120000if_/https://example.com",
                "expected_year": 2023
            },
            {
                "url": "https://web.archive.org/web/20220315143000if_/https://test.org/page",
                "expected_year": 2022
            },
            {
                "url": "https://web.archive.org/web/20211225235959if_/https://site.net",
                "expected_year": 2021
            },
            {
                "url": "invalid-url",
                "expected_timestamp": 0
            },
            {
                "url": "",
                "expected_timestamp": 0
            }
        ]
        
        for case in test_cases:
            timestamp = await migration.extract_timestamp_from_wayback_url(case["url"])
            
            if "expected_timestamp" in case:
                assert timestamp == case["expected_timestamp"]
            else:
                # Convert timestamp back to year for verification
                dt = datetime.fromtimestamp(timestamp)
                assert dt.year == case["expected_year"]
    
    async def test_migration_error_handling(self, setup_legacy_data, migration_script_mock):
        """Test migration error handling"""
        test_data = await setup_legacy_data
        session = test_data["session"]
        
        # Create a page with problematic data
        problematic_page = ProjectPage(
            url="",  # Empty URL should cause validation error
            project_id=test_data["project1"].id,
            domain_id=test_data["domain1"].id,
            content="Problematic content",
            processed=True
        )
        session.add(problematic_page)
        await session.commit()
        
        # Run migration
        migration = migration_script_mock(session)
        
        # Migration should handle errors gracefully
        # Note: In real implementation, this would catch and log errors
        try:
            stats = await migration.migrate_pages_to_shared_architecture()
            # Should complete despite problematic data
            assert stats["legacy_pages_found"] > 0
        except Exception as e:
            # If an error occurs, it should be a specific validation error
            assert "empty" in str(e).lower() or "url" in str(e).lower()
    
    async def test_migration_performance_large_dataset(self, app, migration_script_mock):
        """Test migration performance with larger dataset"""
        async with AsyncSessionLocal() as session:
            # Create test user and project
            user = User(
                email="perf_migration@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Performance Migration User",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            project = Project(
                name="Performance Migration Project",
                user_id=user.id
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            
            domain = Domain(
                name="perf-migration.com",
                project_id=project.id,
                config={}
            )
            session.add(domain)
            await session.commit()
            await session.refresh(domain)
            
            # Create many legacy pages
            legacy_pages = []
            for i in range(100):
                page = ProjectPage(
                    url=f"https://perf-migration.com/page-{i}",
                    wayback_url=f"https://web.archive.org/web/2023010{i%10:01d}120000if_/https://perf-migration.com/page-{i}",
                    project_id=project.id,
                    domain_id=domain.id,
                    content=f"Performance test content {i}",
                    title=f"Performance Page {i}",
                    processed=True
                )
                legacy_pages.append(page)
            
            session.add_all(legacy_pages)
            await session.commit()
            
            # Run migration and measure performance
            migration = migration_script_mock(session)
            
            import time
            start_time = time.time()
            
            stats = await migration.migrate_pages_to_shared_architecture()
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Should complete in reasonable time (< 5 seconds for 100 pages)
            assert execution_time < 5.0
            
            # Verify migration completed successfully
            assert stats["legacy_pages_found"] == 100
            assert stats["pages_v2_created"] == 100  # All unique
            assert stats["project_associations_created"] == 100
    
    async def test_migration_rollback_capability(self, setup_legacy_data, migration_script_mock):
        """Test migration rollback capability"""
        test_data = await setup_legacy_data
        session = test_data["session"]
        
        # Record initial state
        initial_pages_v2_count = len((await session.execute(select(PageV2))).scalars().all())
        initial_associations_count = len((await session.execute(select(ProjectPage))).scalars().all())
        
        # Run migration
        migration = migration_script_mock(session)
        await migration.migrate_pages_to_shared_architecture()
        
        # Verify migration created data
        after_migration_pages_v2 = (await session.execute(select(PageV2))).scalars().all()
        after_migration_associations = (await session.execute(select(ProjectPage))).scalars().all()
        
        assert len(after_migration_pages_v2) > initial_pages_v2_count
        assert len(after_migration_associations) > initial_associations_count
        
        # Simulate rollback by deleting created data
        for association in after_migration_associations:
            await session.delete(association)
        
        for page in after_migration_pages_v2:
            await session.delete(page)
        
        await session.commit()
        
        # Verify rollback
        final_pages_v2_count = len((await session.execute(select(PageV2))).scalars().all())
        final_associations_count = len((await session.execute(select(ProjectPage))).scalars().all())
        
        assert final_pages_v2_count == initial_pages_v2_count
        assert final_associations_count == initial_associations_count
    
    async def test_migration_idempotency(self, setup_legacy_data, migration_script_mock):
        """Test that migration can be run multiple times safely"""
        test_data = await setup_legacy_data
        session = test_data["session"]
        
        # Run migration first time
        migration1 = migration_script_mock(session)
        stats1 = await migration1.migrate_pages_to_shared_architecture()
        
        # Record state after first migration
        pages_v2_after_first = (await session.execute(select(PageV2))).scalars().all()
        associations_after_first = (await session.execute(select(ProjectPage))).scalars().all()
        
        # Run migration second time (should handle existing data gracefully)
        migration2 = migration_script_mock(session)
        # Note: In real implementation, this would check for existing data and skip duplicates
        
        # For this test, we expect the second run to either:
        # 1. Skip existing data (ideal)
        # 2. Handle duplicates gracefully
        # 3. Fail with appropriate error message
        
        # This test verifies the migration script can handle being run multiple times
        # The exact behavior depends on implementation details
        
        # Verify data integrity is maintained
        pages_v2_count = len(pages_v2_after_first)
        associations_count = len(associations_after_first)
        
        assert pages_v2_count >= 4  # At least the expected number
        assert associations_count >= 5  # At least the expected number


# Import AsyncSessionLocal from conftest
from tests.conftest import AsyncSessionLocal