"""
Test suite for shared pages API endpoints with comprehensive security and functionality testing
"""
import pytest
import asyncio
import uuid
from unittest.mock import patch
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import select

from app.models.shared_pages import (
    PageV2, ProjectPage, PageReviewStatus, PageCategory, PagePriority
)
from app.models.project import Project, Domain
from app.models.user import User
from app.core.security import get_password_hash


@pytest.mark.asyncio
class TestSharedPagesEndpoints:
    """Test shared pages API endpoints"""
    
    @pytest.fixture
    async def setup_endpoint_test_data(self, client: TestClient, auth_headers):
        """Setup comprehensive test data for endpoint testing"""
        # Get authenticated user from auth_headers fixture
        # Note: auth_headers fixture creates user "tester@example.com"
        
        async with AsyncSessionLocal() as session:
            # Get the authenticated user
            from sqlmodel import select
            user_stmt = select(User).where(User.email == "tester@example.com")
            result = await session.execute(user_stmt)
            user = result.scalar_one()
            
            # Create test projects
            project1 = Project(
                name="Endpoint Test Project 1",
                description="Primary test project",
                user_id=user.id
            )
            project2 = Project(
                name="Endpoint Test Project 2", 
                description="Secondary test project",
                user_id=user.id
            )
            session.add_all([project1, project2])
            await session.commit()
            await session.refresh(project1)
            await session.refresh(project2)
            
            # Create test domains
            domain1 = Domain(
                name="example.com",
                project_id=project1.id,
                config={"test": True}
            )
            domain2 = Domain(
                name="test.org",
                project_id=project2.id,
                config={"test": True}
            )
            session.add_all([domain1, domain2])
            await session.commit()
            await session.refresh(domain1)
            await session.refresh(domain2)
            
            # Create test pages
            page1 = PageV2(
                url="https://example.com/endpoint-test-1",
                unix_timestamp=1234567890,
                content="<html><body>Endpoint test content 1</body></html>",
                markdown_content="# Endpoint Test 1\n\nTest content 1",
                title="Endpoint Test Page 1",
                extracted_title="Endpoint Test Page 1 Extracted",
                extracted_text="Endpoint test content 1 extracted",
                quality_score=0.85,
                word_count=150,
                character_count=750,
                processed=True,
                indexed=True
            )
            page2 = PageV2(
                url="https://example.com/endpoint-test-2",
                unix_timestamp=1234567891,
                content="<html><body>Endpoint test content 2</body></html>",
                title="Endpoint Test Page 2",
                quality_score=0.90,
                processed=True,
                indexed=True
            )
            page3 = PageV2(
                url="https://test.org/shared-page",
                unix_timestamp=1234567892,
                content="<html><body>Shared endpoint test content</body></html>",
                title="Shared Endpoint Test Page",
                quality_score=0.75,
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
                    domain_id=domain1.id,
                    added_by=user.id,
                    review_status=PageReviewStatus.RELEVANT,
                    page_category=PageCategory.RESEARCH,
                    priority_level=PagePriority.HIGH,
                    tags=["test", "research", "important"],
                    notes="Test page 1 notes",
                    is_starred=True
                ),
                ProjectPage(
                    project_id=project1.id,
                    page_id=page2.id,
                    domain_id=domain1.id,
                    added_by=user.id,
                    review_status=PageReviewStatus.PENDING,
                    priority_level=PagePriority.MEDIUM,
                    tags=["test"]
                ),
                # Shared page - appears in both projects
                ProjectPage(
                    project_id=project1.id,
                    page_id=page3.id,
                    domain_id=domain1.id,
                    added_by=user.id,
                    review_status=PageReviewStatus.RELEVANT,
                    page_category=PageCategory.GOVERNMENT,
                    priority_level=PagePriority.CRITICAL,
                    tags=["shared", "important"]
                ),
                ProjectPage(
                    project_id=project2.id,
                    page_id=page3.id,
                    domain_id=domain2.id,
                    added_by=user.id,
                    review_status=PageReviewStatus.NEEDS_REVIEW,
                    page_category=PageCategory.GOVERNMENT,
                    priority_level=PagePriority.HIGH,
                    tags=["shared", "review"]
                )
            ]
            session.add_all(associations)
            await session.commit()
            
            return {
                "user": user,
                "project1": project1,
                "project2": project2,
                "domain1": domain1,
                "domain2": domain2,
                "page1": page1,
                "page2": page2,
                "page3": page3,
                "session": session
            }
    
    def test_get_shared_page_success(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test successful retrieval of shared page with associations"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        response = client.get(
            f"/api/v1/shared-pages/{test_data['page1'].id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["id"] == str(test_data["page1"].id)
        assert data["url"] == "https://example.com/endpoint-test-1"
        assert data["title"] == "Endpoint Test Page 1"
        assert data["quality_score"] == 0.85
        assert data["processed"] is True
        assert data["indexed"] is True
        
        # Check project associations
        assert "project_associations" in data
        assert len(data["project_associations"]) == 1
        
        association = data["project_associations"][0]
        assert association["project_id"] == test_data["project1"].id
        assert association["review_status"] == "relevant"
        assert association["page_category"] == "research"
        assert association["priority_level"] == "high"
        assert association["tags"] == ["test", "research", "important"]
        assert association["is_starred"] is True
    
    def test_get_shared_page_shared_across_projects(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test retrieval of page shared across multiple projects"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        response = client.get(
            f"/api/v1/shared-pages/{test_data['page3'].id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["id"] == str(test_data["page3"].id)
        assert data["url"] == "https://test.org/shared-page"
        
        # Should have associations from both projects
        assert len(data["project_associations"]) == 2
        
        project_ids = [assoc["project_id"] for assoc in data["project_associations"]]
        assert test_data["project1"].id in project_ids
        assert test_data["project2"].id in project_ids
    
    def test_get_shared_page_not_found(self, client: TestClient, auth_headers):
        """Test retrieval of nonexistent page"""
        nonexistent_id = str(uuid.uuid4())
        
        response = client.get(
            f"/api/v1/shared-pages/{nonexistent_id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_shared_page_access_denied(self, client: TestClient, setup_endpoint_test_data):
        """Test access denied for unauthorized user"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        # Create another user
        async def create_other_user():
            async with AsyncSessionLocal() as session:
                other_user = User(
                    email="other@example.com",
                    hashed_password=get_password_hash("testpass"),
                    full_name="Other User",
                    is_active=True,
                    is_verified=True,
                    approval_status="approved"
                )
                session.add(other_user)
                await session.commit()
                return other_user
        
        asyncio.get_event_loop().run_until_complete(create_other_user())
        
        # Register and login as other user
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com",
                "password": "TestPass123!",
                "full_name": "Other User"
            }
        )
        assert response.status_code in (200, 201)
        
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "other@example.com", "password": "TestPass123!"}
        )
        assert response.status_code == 200
        
        # Try to access page belonging to first user
        response = client.get(
            f"/api/v1/shared-pages/{test_data['page1'].id}"
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_list_user_pages(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test listing user's accessible pages"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        response = client.get(
            "/api/v1/shared-pages",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) == 3  # page1, page2, page3
        
        # Check that all pages belong to the user
        page_ids = [page["id"] for page in data]
        assert str(test_data["page1"].id) in page_ids
        assert str(test_data["page2"].id) in page_ids
        assert str(test_data["page3"].id) in page_ids
    
    def test_list_user_pages_with_project_filter(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test listing pages filtered by project"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        response = client.get(
            f"/api/v1/shared-pages?project_id={test_data['project1'].id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert len(data) == 3  # page1, page2, page3 (all in project1)
    
    def test_list_user_pages_with_pagination(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test listing pages with pagination"""
        asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        response = client.get(
            "/api/v1/shared-pages?limit=2&offset=0",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert len(data) == 2
        
        # Test second page
        response = client.get(
            "/api/v1/shared-pages?limit=2&offset=2",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert len(data) == 1  # Remaining page
    
    def test_get_project_pages(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test getting pages for specific project"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        response = client.get(
            f"/api/v1/shared-pages/projects/{test_data['project1'].id}/pages",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert len(data) == 3  # page1, page2, page3
        
        page_ids = [page["id"] for page in data]
        assert str(test_data["page1"].id) in page_ids
        assert str(test_data["page2"].id) in page_ids
        assert str(test_data["page3"].id) in page_ids
    
    def test_get_project_pages_unauthorized(self, client: TestClient, setup_endpoint_test_data):
        """Test getting pages for unauthorized project"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        # Register and login as different user
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "unauthorized@example.com",
                "password": "TestPass123!",
                "full_name": "Unauthorized User"
            }
        )
        assert response.status_code in (200, 201)
        
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "unauthorized@example.com", "password": "TestPass123!"}
        )
        assert response.status_code == 200
        
        # Try to access other user's project
        response = client.get(
            f"/api/v1/shared-pages/projects/{test_data['project1'].id}/pages"
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_search_shared_pages(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test searching shared pages"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        search_request = {
            "query": "endpoint test",
            "limit": 10,
            "offset": 0,
            "filters": {
                "review_status": ["relevant", "pending"]
            }
        }
        
        with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.search_user_pages') as mock_search:
            mock_search.return_value = {
                "hits": [
                    {
                        "id": str(test_data["page1"].id),
                        "url": "https://example.com/endpoint-test-1",
                        "title": "Endpoint Test Page 1",
                        "review_status": "relevant"
                    }
                ],
                "totalHits": 1,
                "processingTimeMs": 5
            }
            
            response = client.post(
                "/api/v1/shared-pages/search",
                headers=auth_headers,
                json=search_request
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert data["query"] == "endpoint test"
        assert "data" in data
        assert data["data"]["totalHits"] == 1
    
    def test_search_shared_pages_with_project_filter(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test searching shared pages with project filter"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        search_request = {
            "query": "test",
            "project_id": test_data["project1"].id,
            "limit": 10
        }
        
        with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.search_user_pages') as mock_search:
            mock_search.return_value = {
                "hits": [],
                "totalHits": 0,
                "processingTimeMs": 3
            }
            
            response = client.post(
                "/api/v1/shared-pages/search",
                headers=auth_headers,
                json=search_request
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["project_id"] == test_data["project1"].id
    
    def test_update_page_project_association(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test updating project-page association metadata"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        update_data = {
            "review_status": "irrelevant",
            "page_category": "commercial",
            "priority_level": "low",
            "tags": ["updated", "test", "irrelevant"],
            "notes": "Updated notes",
            "quick_notes": "Quick update",
            "is_starred": False
        }
        
        with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.index_page'):
            response = client.put(
                f"/api/v1/shared-pages/{test_data['page1'].id}/associations/{test_data['project1'].id}",
                headers=auth_headers,
                json=update_data
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert data["page_id"] == str(test_data["page1"].id)
        assert data["project_id"] == test_data["project1"].id
        assert "updated_fields" in data
        
        # Verify the association was updated in database
        async def verify_update():
            async with AsyncSessionLocal() as session:
                stmt = select(ProjectPage).where(
                    ProjectPage.project_id == test_data["project1"].id,
                    ProjectPage.page_id == test_data["page1"].id
                )
                result = await session.execute(stmt)
                association = result.scalar_one()
                
                assert association.review_status == PageReviewStatus.IRRELEVANT
                assert association.page_category == PageCategory.COMMERCIAL
                assert association.priority_level == PagePriority.LOW
                assert association.tags == ["updated", "test", "irrelevant"]
                assert association.notes == "Updated notes"
                assert association.quick_notes == "Quick update"
                assert association.is_starred is False
                assert association.reviewed_by == test_data["user"].id
                assert association.reviewed_at is not None
        
        asyncio.get_event_loop().run_until_complete(verify_update())
    
    def test_update_association_unauthorized(self, client: TestClient, setup_endpoint_test_data):
        """Test updating association without proper authorization"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        # Register and login as different user
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "unauthorized2@example.com",
                "password": "TestPass123!",
                "full_name": "Unauthorized User 2"
            }
        )
        assert response.status_code in (200, 201)
        
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "unauthorized2@example.com", "password": "TestPass123!"}
        )
        assert response.status_code == 200
        
        update_data = {"review_status": "relevant"}
        
        response = client.put(
            f"/api/v1/shared-pages/{test_data['page1'].id}/associations/{test_data['project1'].id}",
            json=update_data
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_bulk_page_actions_update_review_status(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test bulk update of review status"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        bulk_request = {
            "page_ids": [str(test_data["page1"].id), str(test_data["page2"].id)],
            "action": "update_review_status",
            "project_id": test_data["project1"].id,
            "data": {
                "review_status": "relevant"
            }
        }
        
        with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.bulk_index_pages'):
            response = client.post(
                "/api/v1/shared-pages/bulk-actions",
                headers=auth_headers,
                json=bulk_request
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert data["action"] == "update_review_status"
        assert data["updated_count"] == 2
        assert data["failed_count"] == 0
    
    def test_bulk_page_actions_add_tags(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test bulk addition of tags"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        bulk_request = {
            "page_ids": [str(test_data["page1"].id), str(test_data["page3"].id)],
            "action": "add_tags",
            "project_id": test_data["project1"].id,
            "data": {
                "tags": ["bulk-added", "test-tag"]
            }
        }
        
        with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.bulk_index_pages'):
            response = client.post(
                "/api/v1/shared-pages/bulk-actions",
                headers=auth_headers,
                json=bulk_request
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert data["action"] == "add_tags"
        assert data["updated_count"] == 2
    
    def test_bulk_page_actions_set_priority(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test bulk setting of priority level"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        bulk_request = {
            "page_ids": [str(test_data["page2"].id)],
            "action": "set_priority",
            "project_id": test_data["project1"].id,
            "data": {
                "priority_level": "critical"
            }
        }
        
        with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.bulk_index_pages'):
            response = client.post(
                "/api/v1/shared-pages/bulk-actions",
                headers=auth_headers,
                json=bulk_request
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert data["action"] == "set_priority"
        assert data["updated_count"] == 1
    
    def test_bulk_page_actions_invalid_action(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test bulk action with invalid action type"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        bulk_request = {
            "page_ids": [str(test_data["page1"].id)],
            "action": "invalid_action",
            "project_id": test_data["project1"].id,
            "data": {}
        }
        
        response = client.post(
            "/api/v1/shared-pages/bulk-actions",
            headers=auth_headers,
            json=bulk_request
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_get_sharing_statistics(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test getting sharing statistics"""
        asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        with patch('app.services.page_access_control.PageAccessControl.get_shared_pages_statistics') as mock_sharing_stats:
            with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.get_search_statistics') as mock_search_stats:
                mock_sharing_stats.return_value = {
                    "total_pages": 3,
                    "total_projects": 2,
                    "shared_pages": 1,
                    "review_status_breakdown": {
                        "relevant": 2,
                        "pending": 1,
                        "needs_review": 1
                    }
                }
                mock_search_stats.return_value = {
                    "indexed_pages": 3,
                    "search_queries_count": 0
                }
                
                response = client.get(
                    "/api/v1/shared-pages/statistics/sharing",
                    headers=auth_headers
                )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert "data" in data
        assert "sharing" in data["data"]
        assert "search" in data["data"]
        assert data["data"]["sharing"]["total_pages"] == 3
        assert data["data"]["sharing"]["shared_pages"] == 1
    
    def test_process_cdx_for_project(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test manual CDX processing for project"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        cdx_request = {
            "domain_id": test_data["domain1"].id,
            "cdx_records": [
                {
                    "url": "https://example.com/cdx-test-1",
                    "timestamp": 1234567893,
                    "wayback_url": "https://web.archive.org/web/1234567893if_/https://example.com/cdx-test-1"
                },
                {
                    "url": "https://example.com/cdx-test-2",
                    "timestamp": 1234567894
                }
            ]
        }
        
        with patch('app.services.cdx_deduplication_service.EnhancedCDXService.process_cdx_results') as mock_process:
            from app.models.shared_pages import ProcessingStats
            mock_process.return_value = ProcessingStats(
                pages_linked=0,
                pages_to_scrape=2,
                pages_already_processing=0,
                pages_failed=0,
                total_processed=2
            )
            
            response = client.post(
                f"/api/v1/shared-pages/projects/{test_data['project1'].id}/process-cdx",
                headers=auth_headers,
                json=cdx_request
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert data["project_id"] == test_data["project1"].id
        assert data["domain_id"] == test_data["domain1"].id
        assert data["records_processed"] == 2
        assert "stats" in data
    
    def test_process_cdx_unauthorized_project(self, client: TestClient, setup_endpoint_test_data):
        """Test CDX processing for unauthorized project"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        # Register and login as different user
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "cdx_unauthorized@example.com",
                "password": "TestPass123!",
                "full_name": "CDX Unauthorized User"
            }
        )
        assert response.status_code in (200, 201)
        
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "cdx_unauthorized@example.com", "password": "TestPass123!"}
        )
        assert response.status_code == 200
        
        cdx_request = {
            "domain_id": test_data["domain1"].id,
            "cdx_records": [
                {"url": "https://example.com/unauthorized", "timestamp": 1234567895}
            ]
        }
        
        response = client.post(
            f"/api/v1/shared-pages/projects/{test_data['project1'].id}/process-cdx",
            json=cdx_request
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_remove_page_from_project(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test removing page association from project"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.update_page_project_association'):
            response = client.delete(
                f"/api/v1/shared-pages/{test_data['page2'].id}/associations/{test_data['project1'].id}",
                headers=auth_headers
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert data["page_id"] == str(test_data["page2"].id)
        assert data["project_id"] == test_data["project1"].id
        assert data["page_deleted"] is False  # Should not delete page, other associations exist
    
    def test_remove_page_from_project_delete_orphaned(self, client: TestClient, auth_headers, setup_endpoint_test_data):
        """Test removing page that becomes orphaned (deleted entirely)"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        # Remove the only association for page1
        with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService'):
            response = client.delete(
                f"/api/v1/shared-pages/{test_data['page1'].id}/associations/{test_data['project1'].id}",
                headers=auth_headers
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["page_deleted"] is True  # Page should be deleted as it has no other associations
        assert data["remaining_associations"] == 0
    
    def test_remove_association_unauthorized(self, client: TestClient, setup_endpoint_test_data):
        """Test removing association without authorization"""
        test_data = asyncio.get_event_loop().run_until_complete(setup_endpoint_test_data)
        
        # Register and login as different user
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "remove_unauthorized@example.com",
                "password": "TestPass123!",
                "full_name": "Remove Unauthorized User"
            }
        )
        assert response.status_code in (200, 201)
        
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "remove_unauthorized@example.com", "password": "TestPass123!"}
        )
        assert response.status_code == 200
        
        response = client.delete(
            f"/api/v1/shared-pages/{test_data['page1'].id}/associations/{test_data['project1'].id}"
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


# Import AsyncSessionLocal from conftest
from tests.conftest import AsyncSessionLocal