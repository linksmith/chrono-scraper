"""
Test suite for CDX deduplication service with comprehensive bulk operation testing
"""
import pytest
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import Session, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.cdx_deduplication_service import (
    EnhancedCDXService, CDXRecord, get_cdx_service
)
from app.models.shared_pages import (
    PageV2, ProjectPage, CDXPageRegistry,
    ScrapeStatus, PageReviewStatus, PagePriority, ProcessingStats
)
from app.models.project import Project, Domain
from app.models.user import User
from app.core.security import get_password_hash
from app.services.cache_service import PageCacheService


class TestCDXRecord:
    """Test CDXRecord data structure"""
    
    def test_cdx_record_creation(self):
        """Test CDXRecord initialization"""
        record = CDXRecord(
            url="https://example.com/test",
            timestamp=1234567890
        )
        
        assert record.url == "https://example.com/test"
        assert record.timestamp == 1234567890
        assert record.wayback_url == "https://web.archive.org/web/1234567890if_/https://example.com/test"
    
    def test_cdx_record_with_custom_wayback_url(self):
        """Test CDXRecord with custom wayback URL"""
        custom_url = "https://web.archive.org/web/20230101120000if_/https://example.com/test"
        record = CDXRecord(
            url="https://example.com/test",
            timestamp=1234567890,
            wayback_url=custom_url
        )
        
        assert record.wayback_url == custom_url


@pytest.mark.asyncio
class TestEnhancedCDXService:
    """Test Enhanced CDX Service functionality"""
    
    @pytest.fixture
    async def setup_test_data(self, app):
        """Create test data for CDX service tests"""
        async with AsyncSessionLocal() as session:
            # Create test user
            user = User(
                email="cdx_test@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="CDX Test User",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            # Create test project
            project = Project(
                name="CDX Test Project",
                description="Test project for CDX service",
                user_id=user.id
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            
            # Create test domain
            domain = Domain(
                name="example.com",
                project_id=project.id,
                config={"test": True}
            )
            session.add(domain)
            await session.commit()
            await session.refresh(domain)
            
            return {
                "user": user,
                "project": project,
                "domain": domain,
                "session": session
            }
    
    @pytest.fixture
    def mock_cache_service(self):
        """Mock cache service for testing"""
        cache = AsyncMock(spec=PageCacheService)
        cache.bulk_check_pages.return_value = {}
        cache.set_page_exists.return_value = None
        return cache
    
    @pytest.fixture
    def cdx_service(self, app, mock_cache_service):
        """Create CDX service with mocked cache"""
        async def get_session():
            async with AsyncSessionLocal() as session:
                yield session
        
        session_gen = get_session()
        session = asyncio.get_event_loop().run_until_complete(session_gen.__anext__())
        
        return EnhancedCDXService(session, mock_cache_service)
    
    async def test_process_empty_cdx_results(self, cdx_service, setup_test_data):
        """Test processing empty CDX results"""
        test_data = await setup_test_data
        
        stats = await cdx_service.process_cdx_results(
            cdx_results=[],
            project_id=test_data["project"].id,
            domain_id=test_data["domain"].id
        )
        
        assert isinstance(stats, ProcessingStats)
        assert stats.total_processed == 0
        assert stats.pages_linked == 0
        assert stats.pages_to_scrape == 0
        assert stats.pages_already_processing == 0
    
    async def test_process_new_cdx_results(self, cdx_service, setup_test_data):
        """Test processing completely new CDX results"""
        test_data = await setup_test_data
        
        cdx_results = [
            CDXRecord("https://example.com/page1", 1234567890),
            CDXRecord("https://example.com/page2", 1234567891),
            CDXRecord("https://example.com/page3", 1234567892)
        ]
        
        with patch('app.services.cdx_deduplication_service.scrape_wayback_page_deduplicated') as mock_task:
            mock_task.delay.return_value = MagicMock()
            
            stats = await cdx_service.process_cdx_results(
                cdx_results=cdx_results,
                project_id=test_data["project"].id,
                domain_id=test_data["domain"].id
            )
        
        assert stats.total_processed == 3
        assert stats.pages_to_scrape == 3
        assert stats.pages_linked == 0
        assert stats.pages_already_processing == 0
        
        # Verify CDX registry entries were created
        session = test_data["session"]
        registry_entries = await session.execute(select(CDXPageRegistry))
        entries = registry_entries.scalars().all()
        assert len(entries) == 3
        
        # Verify all entries have correct status
        for entry in entries:
            assert entry.scrape_status == ScrapeStatus.PENDING
            assert entry.created_by_project_id == test_data["project"].id
    
    async def test_process_existing_pages(self, cdx_service, setup_test_data):
        """Test processing CDX results with existing pages"""
        test_data = await setup_test_data
        session = test_data["session"]
        
        # Create existing pages
        existing_page1 = PageV2(
            url="https://example.com/existing1",
            unix_timestamp=1234567890,
            content="Existing content 1",
            processed=True,
            indexed=True
        )
        existing_page2 = PageV2(
            url="https://example.com/existing2", 
            unix_timestamp=1234567891,
            content="Existing content 2",
            processed=True,
            indexed=True
        )
        
        session.add_all([existing_page1, existing_page2])
        await session.commit()
        await session.refresh(existing_page1)
        await session.refresh(existing_page2)
        
        # Create CDX results that include existing pages
        cdx_results = [
            CDXRecord("https://example.com/existing1", 1234567890),
            CDXRecord("https://example.com/existing2", 1234567891),
            CDXRecord("https://example.com/new1", 1234567892)
        ]
        
        with patch('app.services.cdx_deduplication_service.scrape_wayback_page_deduplicated') as mock_task:
            mock_task.delay.return_value = MagicMock()
            
            stats = await cdx_service.process_cdx_results(
                cdx_results=cdx_results,
                project_id=test_data["project"].id,
                domain_id=test_data["domain"].id
            )
        
        assert stats.total_processed == 3
        assert stats.pages_linked == 2  # Two existing pages linked
        assert stats.pages_to_scrape == 1  # One new page to scrape
        assert stats.pages_already_processing == 0
        
        # Verify project associations were created for existing pages
        associations = await session.execute(select(ProjectPage))
        assoc_list = associations.scalars().all()
        assert len(assoc_list) == 2
        
        # Verify associations link correct pages and project
        for assoc in assoc_list:
            assert assoc.project_id == test_data["project"].id
            assert assoc.page_id in [existing_page1.id, existing_page2.id]
            assert assoc.review_status == PageReviewStatus.PENDING
            assert assoc.priority_level == PagePriority.MEDIUM
    
    async def test_process_pages_in_progress(self, cdx_service, setup_test_data):
        """Test processing CDX results with pages already being processed"""
        test_data = await setup_test_data
        session = test_data["session"]
        
        # Create CDX registry entries for pages in progress
        registry1 = CDXPageRegistry(
            url="https://example.com/processing1",
            unix_timestamp=1234567890,
            scrape_status=ScrapeStatus.IN_PROGRESS,
            created_by_project_id=test_data["project"].id
        )
        registry2 = CDXPageRegistry(
            url="https://example.com/processing2",
            unix_timestamp=1234567891,
            scrape_status=ScrapeStatus.PENDING,
            created_by_project_id=test_data["project"].id
        )
        
        session.add_all([registry1, registry2])
        await session.commit()
        
        # Create CDX results that match processing pages
        cdx_results = [
            CDXRecord("https://example.com/processing1", 1234567890),
            CDXRecord("https://example.com/processing2", 1234567891),
            CDXRecord("https://example.com/new1", 1234567892)
        ]
        
        with patch('app.services.cdx_deduplication_service.scrape_wayback_page_deduplicated') as mock_task:
            mock_task.delay.return_value = MagicMock()
            
            stats = await cdx_service.process_cdx_results(
                cdx_results=cdx_results,
                project_id=test_data["project"].id,
                domain_id=test_data["domain"].id
            )
        
        assert stats.total_processed == 3
        assert stats.pages_linked == 0
        assert stats.pages_to_scrape == 1  # One new page
        assert stats.pages_already_processing == 2  # Two in progress
    
    async def test_bulk_check_existing_pages(self, cdx_service, setup_test_data):
        """Test bulk checking for existing pages"""
        test_data = await setup_test_data
        session = test_data["session"]
        
        # Create test pages
        page1 = PageV2(
            url="https://example.com/bulk1",
            unix_timestamp=1234567890
        )
        page2 = PageV2(
            url="https://example.com/bulk2",
            unix_timestamp=1234567891
        )
        
        session.add_all([page1, page2])
        await session.commit()
        await session.refresh(page1)
        await session.refresh(page2)
        
        # Test bulk check
        url_timestamp_pairs = [
            ("https://example.com/bulk1", 1234567890),
            ("https://example.com/bulk2", 1234567891),
            ("https://example.com/nonexistent", 1234567892)
        ]
        
        existing = await cdx_service._bulk_check_existing_pages(url_timestamp_pairs)
        
        assert len(existing) == 2
        assert ("https://example.com/bulk1", 1234567890) in existing
        assert ("https://example.com/bulk2", 1234567891) in existing
        assert ("https://example.com/nonexistent", 1234567892) not in existing
        
        assert existing[("https://example.com/bulk1", 1234567890)] == page1.id
        assert existing[("https://example.com/bulk2", 1234567891)] == page2.id
    
    async def test_bulk_link_pages_to_project(self, cdx_service, setup_test_data):
        """Test bulk linking of existing pages to project"""
        test_data = await setup_test_data
        session = test_data["session"]
        
        # Create test pages
        pages = []
        for i in range(5):
            page = PageV2(
                url=f"https://example.com/bulk-link-{i}",
                unix_timestamp=1234567890 + i,
                content=f"Bulk content {i}"
            )
            pages.append(page)
        
        session.add_all(pages)
        await session.commit()
        for page in pages:
            await session.refresh(page)
        
        # Create page-record pairs
        page_record_pairs = []
        for i, page in enumerate(pages):
            record = CDXRecord(
                url=f"https://example.com/bulk-link-{i}",
                timestamp=1234567890 + i
            )
            page_record_pairs.append((page.id, record))
        
        # Test bulk linking
        linked_count = await cdx_service._bulk_link_pages_to_project(
            page_record_pairs=page_record_pairs,
            project_id=test_data["project"].id,
            domain_id=test_data["domain"].id
        )
        
        assert linked_count == 5
        
        # Verify associations were created
        associations = await session.execute(select(ProjectPage))
        assoc_list = associations.scalars().all()
        assert len(assoc_list) == 5
        
        for assoc in assoc_list:
            assert assoc.project_id == test_data["project"].id
            assert assoc.domain_id == test_data["domain"].id
            assert assoc.added_by == test_data["user"].id
            assert assoc.review_status == PageReviewStatus.PENDING
    
    async def test_mark_page_completed(self, cdx_service, setup_test_data):
        """Test marking a page as completed in CDX registry"""
        test_data = await setup_test_data
        session = test_data["session"]
        
        # Create registry entry
        registry = CDXPageRegistry(
            url="https://example.com/complete-test",
            unix_timestamp=1234567890,
            scrape_status=ScrapeStatus.IN_PROGRESS
        )
        session.add(registry)
        await session.commit()
        
        # Create completed page
        page = PageV2(
            url="https://example.com/complete-test",
            unix_timestamp=1234567890,
            content="Completed content",
            processed=True
        )
        session.add(page)
        await session.commit()
        await session.refresh(page)
        
        # Mark as completed
        await cdx_service.mark_page_completed(
            url="https://example.com/complete-test",
            timestamp=1234567890,
            page_id=page.id,
            project_id=test_data["project"].id
        )
        
        # Verify registry was updated
        await session.refresh(registry)
        assert registry.scrape_status == ScrapeStatus.COMPLETED
        assert registry.page_id == page.id
    
    async def test_mark_page_failed(self, cdx_service, setup_test_data):
        """Test marking a page as failed in CDX registry"""
        test_data = await setup_test_data
        session = test_data["session"]
        
        # Create registry entry
        registry = CDXPageRegistry(
            url="https://example.com/failed-test",
            unix_timestamp=1234567890,
            scrape_status=ScrapeStatus.IN_PROGRESS
        )
        session.add(registry)
        await session.commit()
        
        # Mark as failed
        error_message = "Scraping failed due to timeout"
        await cdx_service.mark_page_failed(
            url="https://example.com/failed-test",
            timestamp=1234567890,
            error_message=error_message
        )
        
        # Verify registry was updated
        await session.refresh(registry)
        assert registry.scrape_status == ScrapeStatus.FAILED
    
    async def test_get_processing_statistics(self, cdx_service, setup_test_data):
        """Test getting CDX processing statistics"""
        test_data = await setup_test_data
        session = test_data["session"]
        
        # Create registry entries with different statuses
        registries = [
            CDXPageRegistry(
                url=f"https://example.com/stats-{i}",
                unix_timestamp=1234567890 + i,
                scrape_status=status,
                created_by_project_id=test_data["project"].id
            )
            for i, status in enumerate([
                ScrapeStatus.PENDING,
                ScrapeStatus.IN_PROGRESS,
                ScrapeStatus.COMPLETED,
                ScrapeStatus.FAILED,
                ScrapeStatus.PENDING
            ])
        ]
        
        session.add_all(registries)
        await session.commit()
        
        # Get statistics
        stats = await cdx_service.get_processing_statistics()
        
        assert stats["total"] == 5
        assert stats["pending"] == 2
        assert stats["in_progress"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 1
        assert test_data["project"].id in stats["by_project"]
        
        project_stats = stats["by_project"][test_data["project"].id]
        assert project_stats["pending"] == 2
        assert project_stats["in_progress"] == 1
        assert project_stats["completed"] == 1
        assert project_stats["failed"] == 1
    
    async def test_get_processing_statistics_filtered(self, cdx_service, setup_test_data):
        """Test getting CDX processing statistics filtered by project"""
        test_data = await setup_test_data
        session = test_data["session"]
        
        # Create another project
        user2 = User(
            email="cdx_test2@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="CDX Test User 2",
            is_active=True,
            is_verified=True,
            approval_status="approved"
        )
        session.add(user2)
        await session.commit()
        
        project2 = Project(
            name="CDX Test Project 2",
            user_id=user2.id
        )
        session.add(project2)
        await session.commit()
        await session.refresh(project2)
        
        # Create registry entries for both projects
        registries = [
            CDXPageRegistry(
                url="https://example.com/proj1-1",
                unix_timestamp=1234567890,
                scrape_status=ScrapeStatus.PENDING,
                created_by_project_id=test_data["project"].id
            ),
            CDXPageRegistry(
                url="https://example.com/proj1-2",
                unix_timestamp=1234567891,
                scrape_status=ScrapeStatus.COMPLETED,
                created_by_project_id=test_data["project"].id
            ),
            CDXPageRegistry(
                url="https://example.com/proj2-1",
                unix_timestamp=1234567892,
                scrape_status=ScrapeStatus.FAILED,
                created_by_project_id=project2.id
            )
        ]
        
        session.add_all(registries)
        await session.commit()
        
        # Get filtered statistics
        stats = await cdx_service.get_processing_statistics(
            project_id=test_data["project"].id
        )
        
        assert stats["total"] == 2  # Only project 1 entries
        assert stats["pending"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 0
    
    async def test_concurrent_cdx_processing(self, cdx_service, setup_test_data):
        """Test concurrent CDX processing with race condition handling"""
        test_data = await setup_test_data
        
        # Create overlapping CDX results
        cdx_results = [
            CDXRecord("https://example.com/concurrent", 1234567890),
            CDXRecord("https://example.com/concurrent", 1234567890)  # Duplicate
        ]
        
        with patch('app.services.cdx_deduplication_service.scrape_wayback_page_deduplicated') as mock_task:
            mock_task.delay.return_value = MagicMock()
            
            # Process the same CDX results twice concurrently
            tasks = [
                cdx_service.process_cdx_results(
                    cdx_results=cdx_results,
                    project_id=test_data["project"].id,
                    domain_id=test_data["domain"].id
                )
                for _ in range(2)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Both should succeed due to ON CONFLICT DO NOTHING
        for result in results:
            assert isinstance(result, ProcessingStats)
        
        # Verify only one registry entry was created
        session = test_data["session"]
        registry_entries = await session.execute(select(CDXPageRegistry))
        entries = registry_entries.scalars().all()
        assert len(entries) == 1
    
    async def test_cache_integration(self, setup_test_data):
        """Test cache service integration"""
        test_data = await setup_test_data
        
        # Create real cache service
        cache_service = PageCacheService()
        
        async def get_session():
            async with AsyncSessionLocal() as session:
                yield session
        
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        cdx_service = EnhancedCDXService(session, cache_service)
        
        # Create existing page
        page = PageV2(
            url="https://example.com/cache-test",
            unix_timestamp=1234567890,
            content="Cached content"
        )
        session.add(page)
        await session.commit()
        await session.refresh(page)
        
        # Cache the page
        await cache_service.set_page_exists(
            "https://example.com/cache-test", 1234567890, page.id
        )
        
        # Process CDX results - should use cache
        cdx_results = [
            CDXRecord("https://example.com/cache-test", 1234567890),
            CDXRecord("https://example.com/new-page", 1234567891)
        ]
        
        with patch('app.services.cdx_deduplication_service.scrape_wayback_page_deduplicated') as mock_task:
            mock_task.delay.return_value = MagicMock()
            
            stats = await cdx_service.process_cdx_results(
                cdx_results=cdx_results,
                project_id=test_data["project"].id,
                domain_id=test_data["domain"].id
            )
        
        assert stats.pages_linked == 1  # Cached page linked
        assert stats.pages_to_scrape == 1  # New page to scrape


@pytest.mark.asyncio
class TestCDXServiceDependencyInjection:
    """Test CDX service dependency injection"""
    
    async def test_get_cdx_service_dependency(self):
        """Test CDX service dependency injection"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        
        # Get service
        service = await get_cdx_service(mock_db)
        
        assert isinstance(service, EnhancedCDXService)
        assert service.db == mock_db
        assert isinstance(service.cache, PageCacheService)
    
    async def test_get_cdx_service_no_db(self):
        """Test CDX service creation without explicit DB"""
        with patch('app.services.cdx_deduplication_service.get_db') as mock_get_db:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_get_db.return_value = mock_session
            
            service = await get_cdx_service()
            
            assert isinstance(service, EnhancedCDXService)
            assert isinstance(service.cache, PageCacheService)


# Import AsyncSessionLocal from conftest
from tests.conftest import AsyncSessionLocal