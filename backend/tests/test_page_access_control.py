"""
Test suite for page access control security layer with comprehensive permission testing
"""
import pytest
import asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from sqlmodel import Session, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.page_access_control import (
    PageAccessControl, PageAccessControlMiddleware, get_page_access_control
)
from app.models.shared_pages import (
    PageV2, ProjectPage, CDXPageRegistry,
    ScrapeStatus, PageReviewStatus, PagePriority
)
from app.models.project import Project, Domain
from app.models.user import User
from app.core.security import get_password_hash
from app.services.cache_service import PageCacheService


@pytest.mark.asyncio
class TestPageAccessControl:
    """Test core page access control functionality"""
    
    @pytest.fixture
    async def setup_access_control_test(self, app):
        """Setup test data for access control tests"""
        async with AsyncSessionLocal() as session:
            # Create test users
            user1 = User(
                email="access1@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Access Test User 1",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            user2 = User(
                email="access2@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Access Test User 2",
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
                name="Access Test Project 1",
                description="User 1's project",
                user_id=user1.id
            )
            project2 = Project(
                name="Access Test Project 2",
                description="User 2's project",
                user_id=user2.id
            )
            project3 = Project(
                name="Shared Access Project",
                description="User 1's shared project",
                user_id=user1.id
            )
            session.add_all([project1, project2, project3])
            await session.commit()
            await session.refresh(project1)
            await session.refresh(project2)
            await session.refresh(project3)
            
            # Create test pages
            page1 = PageV2(
                url="https://example.com/access-page1",
                unix_timestamp=1234567890,
                content="Access test content 1",
                processed=True,
                indexed=True
            )
            page2 = PageV2(
                url="https://example.com/access-page2",
                unix_timestamp=1234567891,
                content="Access test content 2",
                processed=True,
                indexed=True
            )
            page3 = PageV2(
                url="https://example.com/shared-page",
                unix_timestamp=1234567892,
                content="Shared page content",
                processed=True,
                indexed=True
            )
            session.add_all([page1, page2, page3])
            await session.commit()
            await session.refresh(page1)
            await session.refresh(page2)
            await session.refresh(page3)
            
            # Create project-page associations
            associations = [
                ProjectPage(
                    project_id=project1.id,
                    page_id=page1.id,
                    added_by=user1.id,
                    review_status=PageReviewStatus.RELEVANT
                ),
                ProjectPage(
                    project_id=project2.id,
                    page_id=page2.id,
                    added_by=user2.id,
                    review_status=PageReviewStatus.PENDING
                ),
                # Shared page - appears in both projects
                ProjectPage(
                    project_id=project1.id,
                    page_id=page3.id,
                    added_by=user1.id,
                    review_status=PageReviewStatus.RELEVANT
                ),
                ProjectPage(
                    project_id=project3.id,
                    page_id=page3.id,
                    added_by=user1.id,
                    review_status=PageReviewStatus.NEEDS_REVIEW
                )
            ]
            session.add_all(associations)
            await session.commit()
            
            return {
                "user1": user1,
                "user2": user2,
                "project1": project1,
                "project2": project2,
                "project3": project3,
                "page1": page1,
                "page2": page2,
                "page3": page3,
                "session": session
            }
    
    @pytest.fixture
    def mock_cache_service(self):
        """Mock cache service for access control tests"""
        cache = AsyncMock(spec=PageCacheService)
        cache.get_user_accessible_pages.return_value = None
        cache.cache_user_accessible_pages.return_value = None
        cache.get_project_pages.return_value = None
        cache.cache_project_pages.return_value = None
        cache.invalidate_user_cache.return_value = None
        cache.invalidate_project_cache.return_value = None
        return cache
    
    @pytest.fixture
    def access_control(self, app, mock_cache_service):
        """Create PageAccessControl with mocked cache"""
        async def get_session():
            async with AsyncSessionLocal() as session:
                yield session
        
        session_gen = get_session()
        session = asyncio.get_event_loop().run_until_complete(session_gen.__anext__())
        
        return PageAccessControl(session, mock_cache_service)
    
    async def test_get_user_accessible_pages_no_filter(self, access_control, setup_access_control_test):
        """Test getting all accessible pages for a user"""
        test_data = await setup_access_control_test
        
        accessible_pages = await access_control.get_user_accessible_pages(
            test_data["user1"].id
        )
        
        # User1 should have access to page1 and page3 (shared)
        assert len(accessible_pages) == 2
        assert test_data["page1"].id in accessible_pages
        assert test_data["page3"].id in accessible_pages
        assert test_data["page2"].id not in accessible_pages
    
    async def test_get_user_accessible_pages_with_project_filter(self, access_control, setup_access_control_test):
        """Test getting accessible pages filtered by project"""
        test_data = await setup_access_control_test
        
        # Test project1 filter
        accessible_pages = await access_control.get_user_accessible_pages(
            test_data["user1"].id,
            project_id=test_data["project1"].id
        )
        
        assert len(accessible_pages) == 2  # page1 and page3
        assert test_data["page1"].id in accessible_pages
        assert test_data["page3"].id in accessible_pages
        
        # Test project3 filter (only page3)
        accessible_pages = await access_control.get_user_accessible_pages(
            test_data["user1"].id,
            project_id=test_data["project3"].id
        )
        
        assert len(accessible_pages) == 1
        assert test_data["page3"].id in accessible_pages
    
    async def test_get_user_accessible_pages_no_access(self, access_control, setup_access_control_test):
        """Test user with no accessible pages"""
        test_data = await setup_access_control_test
        
        # User2 trying to access User1's project
        accessible_pages = await access_control.get_user_accessible_pages(
            test_data["user2"].id,
            project_id=test_data["project1"].id
        )
        
        assert len(accessible_pages) == 0
    
    async def test_check_page_access_valid(self, access_control, setup_access_control_test):
        """Test valid page access check"""
        test_data = await setup_access_control_test
        
        # User1 accessing page1 - should succeed
        has_access = await access_control.check_page_access(
            test_data["user1"].id,
            test_data["page1"].id
        )
        
        assert has_access is True
        
        # User1 accessing shared page3 - should succeed
        has_access = await access_control.check_page_access(
            test_data["user1"].id,
            test_data["page3"].id
        )
        
        assert has_access is True
    
    async def test_check_page_access_invalid(self, access_control, setup_access_control_test):
        """Test invalid page access check"""
        test_data = await setup_access_control_test
        
        # User1 trying to access User2's page2 - should fail
        has_access = await access_control.check_page_access(
            test_data["user1"].id,
            test_data["page2"].id
        )
        
        assert has_access is False
        
        # User2 trying to access User1's page1 - should fail
        has_access = await access_control.check_page_access(
            test_data["user2"].id,
            test_data["page1"].id
        )
        
        assert has_access is False
    
    async def test_check_page_access_nonexistent(self, access_control, setup_access_control_test):
        """Test access check for nonexistent page"""
        test_data = await setup_access_control_test
        
        nonexistent_id = uuid.uuid4()
        has_access = await access_control.check_page_access(
            test_data["user1"].id,
            nonexistent_id
        )
        
        assert has_access is False
    
    async def test_get_project_pages_for_user(self, access_control, setup_access_control_test):
        """Test getting pages for a specific project"""
        test_data = await setup_access_control_test
        
        # User1 accessing their own project1
        page_ids = await access_control.get_project_pages_for_user(
            test_data["user1"].id,
            test_data["project1"].id,
            limit=100,
            offset=0
        )
        
        assert len(page_ids) == 2  # page1 and page3
        assert test_data["page1"].id in page_ids
        assert test_data["page3"].id in page_ids
    
    async def test_get_project_pages_unauthorized(self, access_control, setup_access_control_test):
        """Test getting pages for unauthorized project"""
        test_data = await setup_access_control_test
        
        # User2 trying to access User1's project
        page_ids = await access_control.get_project_pages_for_user(
            test_data["user2"].id,
            test_data["project1"].id,
            limit=100,
            offset=0
        )
        
        assert len(page_ids) == 0
    
    async def test_get_user_page_associations(self, access_control, setup_access_control_test):
        """Test getting user's page associations"""
        test_data = await setup_access_control_test
        
        # Get associations for page3 (shared page)
        associations = await access_control.get_user_page_associations(
            test_data["user1"].id,
            [test_data["page3"].id]
        )
        
        # User1 should have 2 associations for page3 (project1 and project3)
        assert len(associations) == 2
        
        project_ids = [assoc.project_id for assoc in associations]
        assert test_data["project1"].id in project_ids
        assert test_data["project3"].id in project_ids
    
    async def test_get_shared_pages_statistics(self, access_control, setup_access_control_test):
        """Test getting shared pages statistics"""
        test_data = await setup_access_control_test
        
        stats = await access_control.get_shared_pages_statistics(test_data["user1"].id)
        
        assert "total_pages" in stats
        assert "total_projects" in stats
        assert "shared_pages" in stats
        assert "review_status_breakdown" in stats
        
        assert stats["total_pages"] == 2  # page1 and page3
        assert stats["total_projects"] == 2  # project1 and project3
        assert stats["shared_pages"] == 1  # page3 is shared
    
    async def test_bulk_check_page_access(self, access_control, setup_access_control_test):
        """Test bulk page access checking"""
        test_data = await setup_access_control_test
        
        page_ids = [
            test_data["page1"].id,
            test_data["page2"].id,
            test_data["page3"].id
        ]
        
        # User1 bulk check
        accessible_pages = await access_control.bulk_check_page_access(
            test_data["user1"].id,
            page_ids
        )
        
        assert len(accessible_pages) == 2  # page1 and page3
        assert test_data["page1"].id in accessible_pages
        assert test_data["page3"].id in accessible_pages
        assert test_data["page2"].id not in accessible_pages
        
        # User2 bulk check
        accessible_pages = await access_control.bulk_check_page_access(
            test_data["user2"].id,
            page_ids
        )
        
        assert len(accessible_pages) == 1  # only page2
        assert test_data["page2"].id in accessible_pages
    
    async def test_cache_integration(self, setup_access_control_test):
        """Test cache integration in access control"""
        test_data = await setup_access_control_test
        
        # Create real cache service
        cache_service = PageCacheService()
        
        async def get_session():
            async with AsyncSessionLocal() as session:
                yield session
        
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        access_control = PageAccessControl(session, cache_service)
        
        # First call - should hit database and cache result
        accessible_pages = await access_control.get_user_accessible_pages(
            test_data["user1"].id
        )
        
        assert len(accessible_pages) == 2
        
        # Second call - should use cache
        with patch.object(session, 'execute') as mock_execute:
            accessible_pages_cached = await access_control.get_user_accessible_pages(
                test_data["user1"].id
            )
            
            # Should not hit database on second call (cached)
            # Note: This test may need adjustment based on cache implementation
            assert accessible_pages_cached == accessible_pages


@pytest.mark.asyncio
class TestPageAccessControlMiddleware:
    """Test PageAccessControlMiddleware functionality"""
    
    @pytest.fixture
    async def setup_middleware_test(self, app):
        """Setup test data for middleware tests"""
        async with AsyncSessionLocal() as session:
            # Create test user
            user = User(
                email="middleware@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Middleware Test User",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            # Create test project
            project = Project(
                name="Middleware Test Project",
                user_id=user.id
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            
            # Create test pages
            accessible_page = PageV2(
                url="https://example.com/accessible",
                unix_timestamp=1234567890,
                content="Accessible content"
            )
            inaccessible_page = PageV2(
                url="https://example.com/inaccessible",
                unix_timestamp=1234567891,
                content="Inaccessible content"
            )
            session.add_all([accessible_page, inaccessible_page])
            await session.commit()
            await session.refresh(accessible_page)
            await session.refresh(inaccessible_page)
            
            # Create association only for accessible page
            association = ProjectPage(
                project_id=project.id,
                page_id=accessible_page.id,
                added_by=user.id
            )
            session.add(association)
            await session.commit()
            
            return {
                "user": user,
                "project": project,
                "accessible_page": accessible_page,
                "inaccessible_page": inaccessible_page,
                "session": session
            }
    
    @pytest.fixture
    def middleware(self, app):
        """Create PageAccessControlMiddleware"""
        async def get_session():
            async with AsyncSessionLocal() as session:
                yield session
        
        session_gen = get_session()
        session = asyncio.get_event_loop().run_until_complete(session_gen.__anext__())
        
        cache_service = PageCacheService()
        access_control = PageAccessControl(session, cache_service)
        
        return PageAccessControlMiddleware(access_control)
    
    async def test_validate_page_access_success(self, middleware, setup_middleware_test):
        """Test successful page access validation"""
        test_data = await setup_middleware_test
        
        # Should not raise exception
        await middleware.validate_page_access(
            test_data["user"].id,
            test_data["accessible_page"].id,
            "read"
        )
    
    async def test_validate_page_access_failure(self, middleware, setup_middleware_test):
        """Test failed page access validation"""
        test_data = await setup_middleware_test
        
        from fastapi import HTTPException
        
        # Should raise HTTP 403 Forbidden
        with pytest.raises(HTTPException) as exc_info:
            await middleware.validate_page_access(
                test_data["user"].id,
                test_data["inaccessible_page"].id,
                "read"
            )
        
        assert exc_info.value.status_code == 403
        assert "access denied" in exc_info.value.detail.lower()
    
    async def test_validate_page_access_nonexistent(self, middleware, setup_middleware_test):
        """Test page access validation for nonexistent page"""
        test_data = await setup_middleware_test
        
        from fastapi import HTTPException
        
        nonexistent_id = uuid.uuid4()
        
        # Should raise HTTP 404 Not Found
        with pytest.raises(HTTPException) as exc_info:
            await middleware.validate_page_access(
                test_data["user"].id,
                nonexistent_id,
                "read"
            )
        
        assert exc_info.value.status_code == 403  # Access denied (not 404 for security)
    
    async def test_validate_bulk_page_access(self, middleware, setup_middleware_test):
        """Test bulk page access validation"""
        test_data = await setup_middleware_test
        
        page_ids = [
            test_data["accessible_page"].id,
            test_data["inaccessible_page"].id,
            uuid.uuid4()  # Nonexistent page
        ]
        
        accessible_pages = await middleware.validate_bulk_page_access(
            test_data["user"].id,
            page_ids,
            "read"
        )
        
        # Should only return accessible page
        assert len(accessible_pages) == 1
        assert test_data["accessible_page"].id in accessible_pages
    
    async def test_validate_bulk_page_access_empty_result(self, middleware, setup_middleware_test):
        """Test bulk page access validation with no accessible pages"""
        test_data = await setup_middleware_test
        
        page_ids = [
            test_data["inaccessible_page"].id,
            uuid.uuid4()  # Nonexistent page
        ]
        
        accessible_pages = await middleware.validate_bulk_page_access(
            test_data["user"].id,
            page_ids,
            "read"
        )
        
        # Should return empty list
        assert len(accessible_pages) == 0
    
    async def test_validate_project_ownership_success(self, middleware, setup_middleware_test):
        """Test successful project ownership validation"""
        test_data = await setup_middleware_test
        
        # Should not raise exception
        await middleware.validate_project_ownership(
            test_data["user"].id,
            test_data["project"].id
        )
    
    async def test_validate_project_ownership_failure(self, middleware, setup_middleware_test):
        """Test failed project ownership validation"""
        test_data = await setup_middleware_test
        
        from fastapi import HTTPException
        
        # Create another user
        other_user = User(
            email="other@example.com",
            hashed_password=get_password_hash("testpass"),
            full_name="Other User",
            is_active=True,
            is_verified=True,
            approval_status="approved"
        )
        session = test_data["session"]
        session.add(other_user)
        await session.commit()
        await session.refresh(other_user)
        
        # Other user trying to access the project
        with pytest.raises(HTTPException) as exc_info:
            await middleware.validate_project_ownership(
                other_user.id,
                test_data["project"].id
            )
        
        assert exc_info.value.status_code == 403
        assert "access denied" in exc_info.value.detail.lower()
    
    async def test_validate_project_ownership_nonexistent(self, middleware, setup_middleware_test):
        """Test project ownership validation for nonexistent project"""
        test_data = await setup_middleware_test
        
        from fastapi import HTTPException
        
        nonexistent_project_id = 99999
        
        with pytest.raises(HTTPException) as exc_info:
            await middleware.validate_project_ownership(
                test_data["user"].id,
                nonexistent_project_id
            )
        
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()


@pytest.mark.asyncio
class TestPageAccessControlDependency:
    """Test page access control dependency injection"""
    
    async def test_get_page_access_control_dependency(self):
        """Test page access control dependency injection"""
        # Mock database session
        mock_db = AsyncMock(spec=AsyncSession)
        
        # Get access control
        access_control = await get_page_access_control(mock_db)
        
        assert isinstance(access_control, PageAccessControl)
        assert access_control.db == mock_db
        assert isinstance(access_control.cache, PageCacheService)


@pytest.mark.asyncio
class TestPageAccessControlPerformance:
    """Test performance aspects of page access control"""
    
    async def test_bulk_access_check_performance(self, app):
        """Test performance of bulk access checking with large datasets"""
        async with AsyncSessionLocal() as session:
            # Create test user
            user = User(
                email="perf@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Performance Test User",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            # Create test project
            project = Project(
                name="Performance Test Project",
                user_id=user.id
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            
            # Create many test pages
            pages = []
            for i in range(100):
                page = PageV2(
                    url=f"https://example.com/perf-page-{i}",
                    unix_timestamp=1234567890 + i,
                    content=f"Performance test content {i}"
                )
                pages.append(page)
            
            session.add_all(pages)
            await session.commit()
            for page in pages:
                await session.refresh(page)
            
            # Create associations for half the pages
            associations = []
            for i in range(0, 50):
                association = ProjectPage(
                    project_id=project.id,
                    page_id=pages[i].id,
                    added_by=user.id
                )
                associations.append(association)
            
            session.add_all(associations)
            await session.commit()
            
            # Test bulk access check
            cache_service = PageCacheService()
            access_control = PageAccessControl(session, cache_service)
            
            page_ids = [page.id for page in pages]
            
            import time
            start_time = time.time()
            
            accessible_pages = await access_control.bulk_check_page_access(
                user.id,
                page_ids
            )
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            # Should complete in reasonable time (< 1 second for 100 pages)
            assert execution_time < 1.0
            
            # Should return correct number of accessible pages
            assert len(accessible_pages) == 50
    
    async def test_cached_access_check_performance(self, app):
        """Test performance improvement from caching"""
        async with AsyncSessionLocal() as session:
            # Create test data
            user = User(
                email="cache_perf@example.com",
                hashed_password=get_password_hash("testpass"),
                full_name="Cache Performance Test User",
                is_active=True,
                is_verified=True,
                approval_status="approved"
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            
            project = Project(
                name="Cache Performance Test Project",
                user_id=user.id
            )
            session.add(project)
            await session.commit()
            await session.refresh(project)
            
            # Create access control with real cache
            cache_service = PageCacheService()
            access_control = PageAccessControl(session, cache_service)
            
            import time
            
            # First call - should hit database
            start_time = time.time()
            accessible_pages1 = await access_control.get_user_accessible_pages(user.id)
            first_call_time = time.time() - start_time
            
            # Second call - should use cache (if implemented)
            start_time = time.time()
            accessible_pages2 = await access_control.get_user_accessible_pages(user.id)
            second_call_time = time.time() - start_time
            
            # Results should be the same
            assert accessible_pages1 == accessible_pages2
            
            # Note: Cache performance test depends on cache implementation
            # This test mainly verifies that caching doesn't break functionality


# Import AsyncSessionLocal from conftest
from tests.conftest import AsyncSessionLocal