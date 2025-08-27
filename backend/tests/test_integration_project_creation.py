"""
Integration test suite for project creation with deduplication functionality
"""
import pytest
import asyncio
import uuid
import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shared_pages import (
    PageV2, ProjectPage, CDXPageRegistry,
    ScrapeStatus, PageReviewStatus, PageCategory, PagePriority
)
from app.models.project import Project, Domain
from app.models.user import User
from app.core.security import get_password_hash
from app.services.cdx_deduplication_service import CDXRecord, EnhancedCDXService


@pytest.mark.asyncio
class TestProjectCreationIntegration:
    """Integration tests for project creation with deduplication"""
    
    @pytest.fixture
    async def setup_integration_test(self, client: TestClient, auth_headers):
        """Setup integration test environment with authenticated user"""
        # Get authenticated user from auth_headers fixture
        async with AsyncSessionLocal() as session:
            # Get the authenticated user
            user_stmt = select(User).where(User.email == "tester@example.com")
            result = await session.execute(user_stmt)
            user = result.scalar_one()
            
            # Create some existing pages for deduplication testing
            existing_pages = [
                PageV2(
                    url="https://existing.com/page1",
                    unix_timestamp=1234567890,
                    content="<html><body>Existing page 1</body></html>",
                    title="Existing Page 1",
                    quality_score=0.8,
                    processed=True,
                    indexed=True
                ),
                PageV2(
                    url="https://existing.com/page2",
                    unix_timestamp=1234567891,
                    content="<html><body>Existing page 2</body></html>",
                    title="Existing Page 2",
                    quality_score=0.75,
                    processed=True,
                    indexed=True
                ),
                PageV2(
                    url="https://shared.com/common",
                    unix_timestamp=1234567892,
                    content="<html><body>Shared page content</body></html>",
                    title="Shared Page",
                    quality_score=0.9,
                    processed=True,
                    indexed=True
                )
            ]
            
            session.add_all(existing_pages)
            await session.commit()
            for page in existing_pages:
                await session.refresh(page)
            
            # Create existing project with some pages
            existing_project = Project(
                name="Existing Project",
                description="Project with existing pages",
                user_id=user.id
            )
            session.add(existing_project)
            await session.commit()
            await session.refresh(existing_project)
            
            existing_domain = Domain(
                name="existing.com",
                project_id=existing_project.id,
                config={"existing": True}
            )
            session.add(existing_domain)
            await session.commit()
            await session.refresh(existing_domain)
            
            # Create associations for existing project
            associations = [
                ProjectPage(
                    project_id=existing_project.id,
                    page_id=existing_pages[0].id,
                    domain_id=existing_domain.id,
                    added_by=user.id,
                    review_status=PageReviewStatus.RELEVANT,
                    page_category=PageCategory.RESEARCH,
                    priority_level=PagePriority.HIGH
                ),
                ProjectPage(
                    project_id=existing_project.id,
                    page_id=existing_pages[2].id,  # Shared page
                    domain_id=existing_domain.id,
                    added_by=user.id,
                    review_status=PageReviewStatus.RELEVANT,
                    page_category=PageCategory.RESEARCH,
                    priority_level=PagePriority.MEDIUM
                )
            ]
            session.add_all(associations)
            await session.commit()
            
            return {
                "user": user,
                "existing_project": existing_project,
                "existing_domain": existing_domain,
                "existing_pages": existing_pages,
                "session": session
            }
    
    def test_create_project_basic(self, client: TestClient, auth_headers):
        """Test basic project creation"""
        project_data = {
            "name": "Integration Test Project",
            "description": "Test project for integration testing",
            "config": {"test": True}
        }
        
        response = client.post(
            "/api/v1/projects/",
            headers=auth_headers,
            json=project_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        
        assert data["name"] == "Integration Test Project"
        assert data["description"] == "Test project for integration testing"
        assert data["config"]["test"] is True
        assert "id" in data
        assert "user_id" in data
        assert "created_at" in data
    
    def test_create_project_with_domains(self, client: TestClient, auth_headers):
        """Test project creation with domain configuration"""
        project_data = {
            "name": "Project with Domains",
            "description": "Test project with domain setup",
            "domains": [
                {
                    "name": "integration-test.com",
                    "config": {
                        "scraping_enabled": True,
                        "max_pages": 1000
                    }
                },
                {
                    "name": "secondary.org",
                    "config": {
                        "scraping_enabled": True,
                        "max_pages": 500
                    }
                }
            ]
        }
        
        response = client.post(
            "/api/v1/projects/",
            headers=auth_headers,
            json=project_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        
        project_id = data["id"]
        
        # Verify domains were created
        response = client.get(
            f"/api/v1/projects/{project_id}/domains",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        domains = response.json()
        
        assert len(domains) == 2
        domain_names = [domain["name"] for domain in domains]
        assert "integration-test.com" in domain_names
        assert "secondary.org" in domain_names
    
    async def test_project_creation_with_cdx_processing(self, client: TestClient, auth_headers, setup_integration_test):
        """Test project creation followed by CDX processing with deduplication"""
        test_data = await setup_integration_test
        
        # Create new project
        project_data = {
            "name": "CDX Integration Project",
            "description": "Project for CDX integration testing"
        }
        
        response = client.post(
            "/api/v1/projects/",
            headers=auth_headers,
            json=project_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        project = response.json()
        project_id = project["id"]
        
        # Add domain to project
        domain_data = {
            "name": "cdx-integration.com",
            "config": {
                "scraping_enabled": True,
                "intelligent_filtering": True
            }
        }
        
        response = client.post(
            f"/api/v1/projects/{project_id}/domains",
            headers=auth_headers,
            json=domain_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        domain = response.json()
        domain_id = domain["id"]
        
        # Simulate CDX processing with mix of new and existing pages
        cdx_request = {
            "domain_id": domain_id,
            "cdx_records": [
                # Existing page - should be linked
                {
                    "url": "https://existing.com/page1",
                    "timestamp": 1234567890,
                    "wayback_url": "https://web.archive.org/web/1234567890if_/https://existing.com/page1"
                },
                # Shared page - should be linked to both projects
                {
                    "url": "https://shared.com/common",
                    "timestamp": 1234567892,
                    "wayback_url": "https://web.archive.org/web/1234567892if_/https://shared.com/common"
                },
                # New page - should be queued for scraping
                {
                    "url": "https://cdx-integration.com/new-page",
                    "timestamp": 1234567893,
                    "wayback_url": "https://web.archive.org/web/1234567893if_/https://cdx-integration.com/new-page"
                }
            ]
        }
        
        with patch('app.services.cdx_deduplication_service.scrape_wayback_page_deduplicated') as mock_scraping_task:
            mock_scraping_task.delay.return_value = MagicMock()
            
            response = client.post(
                f"/api/v1/shared-pages/projects/{project_id}/process-cdx",
                headers=auth_headers,
                json=cdx_request
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert data["project_id"] == project_id
        assert data["domain_id"] == domain_id
        assert data["records_processed"] == 3
        
        stats = data["stats"]
        assert stats["pages_linked"] == 2  # Two existing pages linked
        assert stats["pages_to_scrape"] == 1  # One new page to scrape
        assert stats["total_processed"] == 3
        
        # Verify project pages were created
        response = client.get(
            f"/api/v1/shared-pages/projects/{project_id}/pages",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        pages = response.json()
        
        assert len(pages) == 2  # Two linked pages (existing and shared)
        
        # Verify shared page appears in both projects
        async with AsyncSessionLocal() as session:
            shared_page_id = test_data["existing_pages"][2].id  # Shared page
            
            associations_stmt = select(ProjectPage).where(ProjectPage.page_id == shared_page_id)
            result = await session.execute(associations_stmt)
            associations = result.scalars().all()
            
            assert len(associations) == 2  # Should be in both projects
            project_ids = [assoc.project_id for assoc in associations]
            assert test_data["existing_project"].id in project_ids
            assert project_id in project_ids
    
    async def test_project_deletion_with_shared_pages(self, client: TestClient, auth_headers, setup_integration_test):
        """Test project deletion preserves shared pages"""
        test_data = await setup_integration_test
        
        # Create second project that shares pages
        project_data = {
            "name": "Second Sharing Project",
            "description": "Project that shares pages with existing project"
        }
        
        response = client.post(
            "/api/v1/projects/",
            headers=auth_headers,
            json=project_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        second_project = response.json()
        second_project_id = second_project["id"]
        
        # Add shared page to second project
        shared_page_id = test_data["existing_pages"][2].id
        
        async with AsyncSessionLocal() as session:
            # Create association manually for testing
            association = ProjectPage(
                project_id=second_project_id,
                page_id=shared_page_id,
                added_by=test_data["user"].id,
                review_status=PageReviewStatus.PENDING,
                priority_level=PagePriority.MEDIUM
            )
            session.add(association)
            await session.commit()
        
        # Verify page is shared between projects
        response = client.get(
            f"/api/v1/shared-pages/{shared_page_id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        page_data = response.json()
        
        assert len(page_data["project_associations"]) == 2
        
        # Delete second project
        response = client.delete(
            f"/api/v1/projects/{second_project_id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify shared page still exists and accessible from first project
        response = client.get(
            f"/api/v1/shared-pages/{shared_page_id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        page_data = response.json()
        
        # Should only have one association now (from existing project)
        assert len(page_data["project_associations"]) == 1
        assert page_data["project_associations"][0]["project_id"] == test_data["existing_project"].id
    
    async def test_bulk_page_operations_across_projects(self, client: TestClient, auth_headers, setup_integration_test):
        """Test bulk operations on pages shared across projects"""
        test_data = await setup_integration_test
        
        # Create second project
        project_data = {
            "name": "Bulk Operations Project",
            "description": "Project for testing bulk operations"
        }
        
        response = client.post(
            "/api/v1/projects/",
            headers=auth_headers,
            json=project_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        bulk_project = response.json()
        bulk_project_id = bulk_project["id"]
        
        # Share existing pages with new project
        shared_page_ids = [test_data["existing_pages"][0].id, test_data["existing_pages"][2].id]
        
        async with AsyncSessionLocal() as session:
            associations = []
            for page_id in shared_page_ids:
                association = ProjectPage(
                    project_id=bulk_project_id,
                    page_id=page_id,
                    added_by=test_data["user"].id,
                    review_status=PageReviewStatus.PENDING,
                    priority_level=PagePriority.LOW
                )
                associations.append(association)
            
            session.add_all(associations)
            await session.commit()
        
        # Perform bulk update on new project
        bulk_request = {
            "page_ids": [str(page_id) for page_id in shared_page_ids],
            "action": "update_review_status",
            "project_id": bulk_project_id,
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
        assert data["updated_count"] == 2
        
        # Verify updates only affected the specified project
        async with AsyncSessionLocal() as session:
            # Check bulk project associations
            bulk_associations_stmt = select(ProjectPage).where(
                ProjectPage.project_id == bulk_project_id,
                ProjectPage.page_id.in_(shared_page_ids)
            )
            result = await session.execute(bulk_associations_stmt)
            bulk_associations = result.scalars().all()
            
            for assoc in bulk_associations:
                assert assoc.review_status == PageReviewStatus.RELEVANT
            
            # Check original project associations (should be unchanged)
            original_associations_stmt = select(ProjectPage).where(
                ProjectPage.project_id == test_data["existing_project"].id,
                ProjectPage.page_id.in_(shared_page_ids)
            )
            result = await session.execute(original_associations_stmt)
            original_associations = result.scalars().all()
            
            for assoc in original_associations:
                assert assoc.review_status == PageReviewStatus.RELEVANT  # Was already relevant
    
    async def test_search_across_multiple_projects(self, client: TestClient, auth_headers, setup_integration_test):
        """Test searching pages across multiple projects"""
        test_data = await setup_integration_test
        
        # Create search-focused project
        project_data = {
            "name": "Search Test Project",
            "description": "Project for testing search functionality"
        }
        
        response = client.post(
            "/api/v1/projects/",
            headers=auth_headers,
            json=project_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        search_project = response.json()
        search_project_id = search_project["id"]
        
        # Add pages to search project
        async with AsyncSessionLocal() as session:
            # Add all existing pages to search project with different metadata
            associations = []
            for i, page in enumerate(test_data["existing_pages"]):
                association = ProjectPage(
                    project_id=search_project_id,
                    page_id=page.id,
                    added_by=test_data["user"].id,
                    review_status=PageReviewStatus.RELEVANT,
                    page_category=PageCategory.NEWS,
                    priority_level=PagePriority.HIGH,
                    tags=[f"search-tag-{i}", "searchable"]
                )
                associations.append(association)
            
            session.add_all(associations)
            await session.commit()
        
        # Test search across all projects
        search_request = {
            "query": "existing",
            "limit": 10,
            "offset": 0,
            "filters": {
                "tags": ["searchable"]
            }
        }
        
        with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.search_user_pages') as mock_search:
            mock_search.return_value = {
                "hits": [
                    {
                        "id": str(test_data["existing_pages"][0].id),
                        "url": "https://existing.com/page1",
                        "title": "Existing Page 1",
                        "project_ids": [test_data["existing_project"].id, search_project_id],
                        "tags": ["search-tag-0", "searchable"],
                        "review_statuses": ["relevant"]
                    }
                ],
                "totalHits": 1,
                "processingTimeMs": 8
            }
            
            response = client.post(
                "/api/v1/shared-pages/search",
                headers=auth_headers,
                json=search_request
            )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert data["data"]["totalHits"] == 1
        
        # Verify search included user's accessible projects
        mock_search.assert_called_once()
        call_args = mock_search.call_args[1]
        assert call_args["user_id"] == test_data["user"].id
        assert call_args["query"] == "existing"
    
    async def test_project_statistics_with_shared_pages(self, client: TestClient, auth_headers, setup_integration_test):
        """Test project statistics calculation with shared pages"""
        test_data = await setup_integration_test
        
        # Get sharing statistics
        response = client.get(
            "/api/v1/shared-pages/statistics/sharing",
            headers=auth_headers
        )
        
        with patch('app.services.page_access_control.PageAccessControl.get_shared_pages_statistics') as mock_stats:
            with patch('app.services.shared_pages_meilisearch.SharedPagesMeilisearchService.get_search_statistics') as mock_search_stats:
                mock_stats.return_value = {
                    "total_pages": 3,
                    "total_projects": 1,
                    "shared_pages": 1,  # One page is shared
                    "review_status_breakdown": {
                        "relevant": 2,
                        "pending": 0,
                        "needs_review": 0,
                        "irrelevant": 0
                    },
                    "category_breakdown": {
                        "research": 2,
                        "government": 0,
                        "news": 0
                    },
                    "priority_breakdown": {
                        "high": 1,
                        "medium": 1,
                        "low": 0,
                        "critical": 0
                    }
                }
                
                mock_search_stats.return_value = {
                    "indexed_pages": 3,
                    "search_queries_count": 0,
                    "index_status": "ready"
                }
                
                response = client.get(
                    "/api/v1/shared-pages/statistics/sharing",
                    headers=auth_headers
                )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["success"] is True
        assert "data" in data
        
        sharing_stats = data["data"]["sharing"]
        assert sharing_stats["total_pages"] == 3
        assert sharing_stats["shared_pages"] == 1
        assert sharing_stats["review_status_breakdown"]["relevant"] == 2
    
    async def test_concurrent_project_operations(self, client: TestClient, auth_headers, setup_integration_test):
        """Test concurrent operations on shared resources"""
        test_data = await setup_integration_test
        
        # Create multiple projects concurrently
        project_requests = [
            {
                "name": f"Concurrent Project {i}",
                "description": f"Concurrent test project {i}"
            }
            for i in range(3)
        ]
        
        # Create projects
        created_projects = []
        for project_data in project_requests:
            response = client.post(
                "/api/v1/projects/",
                headers=auth_headers,
                json=project_data
            )
            assert response.status_code == status.HTTP_201_CREATED
            created_projects.append(response.json())
        
        # Concurrently add same shared page to all projects
        shared_page_id = test_data["existing_pages"][2].id
        
        async with AsyncSessionLocal() as session:
            # Add shared page to all concurrent projects
            associations = []
            for project in created_projects:
                association = ProjectPage(
                    project_id=project["id"],
                    page_id=shared_page_id,
                    added_by=test_data["user"].id,
                    review_status=PageReviewStatus.PENDING,
                    priority_level=PagePriority.MEDIUM
                )
                associations.append(association)
            
            session.add_all(associations)
            await session.commit()
        
        # Verify shared page appears in all projects
        response = client.get(
            f"/api/v1/shared-pages/{shared_page_id}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        page_data = response.json()
        
        # Should have associations from original project + 3 concurrent projects = 4 total
        assert len(page_data["project_associations"]) == 4
        
        project_ids = [assoc["project_id"] for assoc in page_data["project_associations"]]
        assert test_data["existing_project"].id in project_ids
        for project in created_projects:
            assert project["id"] in project_ids
    
    async def test_error_handling_in_integration_workflow(self, client: TestClient, auth_headers):
        """Test error handling in complete integration workflow"""
        # Try to create project with invalid data
        invalid_project_data = {
            "name": "",  # Invalid: empty name
            "description": "Test project"
        }
        
        response = client.post(
            "/api/v1/projects/",
            headers=auth_headers,
            json=invalid_project_data
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        
        # Create valid project
        valid_project_data = {
            "name": "Error Handling Test Project",
            "description": "Project for testing error handling"
        }
        
        response = client.post(
            "/api/v1/projects/",
            headers=auth_headers,
            json=valid_project_data
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        project = response.json()
        project_id = project["id"]
        
        # Try to process CDX with invalid domain
        invalid_cdx_request = {
            "domain_id": 99999,  # Non-existent domain
            "cdx_records": [
                {
                    "url": "https://error-test.com/page",
                    "timestamp": 1234567890
                }
            ]
        }
        
        response = client.post(
            f"/api/v1/shared-pages/projects/{project_id}/process-cdx",
            headers=auth_headers,
            json=invalid_cdx_request
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        
        # Try to access non-existent project
        response = client.get(
            "/api/v1/shared-pages/projects/99999/pages",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN


# Import AsyncSessionLocal from conftest
from tests.conftest import AsyncSessionLocal