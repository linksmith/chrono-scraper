"""
Integration Tests for Secure Multi-Tenant Search Endpoints

This module provides comprehensive integration tests for the secure search
endpoints, testing project isolation, sharing permissions, and security.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app
from app.models.project import Project
from app.models.user import User
from app.models.sharing import ProjectShare, PublicSearchConfig, SharePermission, ShareStatus
from app.core.database import get_db
from app.api.deps import get_current_active_user


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Create async test client"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_db():
    """Mock database session"""
    return AsyncMock()


@pytest.fixture
def owner_user():
    """Create mock owner user"""
    user = Mock(spec=User)
    user.id = 1
    user.email = "owner@test.com"
    user.is_active = True
    return user


@pytest.fixture
def shared_user():
    """Create mock shared user"""
    user = Mock(spec=User)
    user.id = 2
    user.email = "shared@test.com"
    user.is_active = True
    return user


@pytest.fixture
def unauthorized_user():
    """Create mock unauthorized user"""
    user = Mock(spec=User)
    user.id = 3
    user.email = "unauthorized@test.com"
    user.is_active = True
    return user


@pytest.fixture
def test_project():
    """Create mock test project"""
    project = Mock(spec=Project)
    project.id = 100
    project.name = "Test Project"
    project.user_id = 1  # Owned by owner_user
    project.index_search_key = "test_search_key_100"
    project.index_search_key_uid = "test_key_uid_100"
    return project


@pytest.fixture
def project_share():
    """Create mock project share"""
    share = Mock(spec=ProjectShare)
    share.id = 50
    share.project_id = 100
    share.shared_with_user_id = 2  # Shared with shared_user
    share.permission = SharePermission.LIMITED
    share.status = ShareStatus.ACTIVE
    share.expires_at = datetime.utcnow() + timedelta(hours=24)
    share.access_count = 0
    return share


@pytest.fixture
def public_config():
    """Create mock public search configuration"""
    config = Mock(spec=PublicSearchConfig)
    config.project_id = 100
    config.is_enabled = True
    config.search_key = "public_search_key_100"
    config.search_key_uid = "public_key_uid_100"
    config.custom_title = "Public Test Project"
    config.rate_limit_per_hour = 100
    config.allow_downloads = False
    return config


class TestSecureProjectSearch:
    """Test secure project search endpoint"""
    
    @pytest.mark.asyncio
    async def test_project_owner_search_success(self, async_client, mock_db, owner_user, test_project):
        """Test successful search by project owner"""
        # Mock database queries
        mock_db.execute.return_value.scalar_one_or_none.return_value = test_project
        
        # Mock MeilisearchService
        mock_search_results = {
            "hits": [{"id": "page_1", "title": "Test Page"}],
            "totalHits": 1,
            "facetDistribution": {},
            "processingTimeMs": 10
        }
        
        with patch("app.api.v1.endpoints.meilisearch_routes.get_db", return_value=mock_db):
            with patch("app.api.v1.endpoints.meilisearch_routes.get_current_active_user", return_value=owner_user):
                with patch("app.api.v1.endpoints.meilisearch_routes._verify_project_access") as mock_verify:
                    mock_verify.return_value = {
                        "has_access": True,
                        "access_type": "owner",
                        "project": test_project,
                        "share": None
                    }
                    
                    with patch("app.services.meilisearch_service.MeilisearchService.for_project") as mock_service:
                        mock_ms = AsyncMock()
                        mock_ms.__aenter__.return_value = mock_ms
                        mock_ms.search_with_entity_filters.return_value = mock_search_results
                        mock_service.return_value = mock_ms
                        
                        response = await async_client.get(
                            f"/api/v1/meilisearch/projects/{test_project.id}/search",
                            params={"q": "test query", "limit": 20}
                        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["hits"] == mock_search_results["hits"]
        assert data["totalHits"] == 1
        assert data["projectId"] == test_project.id
        assert data["accessType"] == "owner"
    
    @pytest.mark.asyncio
    async def test_shared_user_search_with_filtering(self, async_client, mock_db, shared_user, test_project, project_share):
        """Test search by shared user with permission-based filtering"""
        # Mock database queries
        mock_db.execute.return_value.scalar_one_or_none.return_value = test_project
        
        mock_search_results = {
            "hits": [{"id": "page_1", "title": "Relevant Page"}],
            "totalHits": 1,
            "facetDistribution": {},
            "processingTimeMs": 15
        }
        
        with patch("app.api.v1.endpoints.meilisearch_routes.get_db", return_value=mock_db):
            with patch("app.api.v1.endpoints.meilisearch_routes.get_current_active_user", return_value=shared_user):
                with patch("app.api.v1.endpoints.meilisearch_routes._verify_project_access") as mock_verify:
                    mock_verify.return_value = {
                        "has_access": True,
                        "access_type": "shared",
                        "project": test_project,
                        "share": project_share
                    }
                    
                    with patch("app.services.meilisearch_service.MeilisearchService.for_project") as mock_service:
                        mock_ms = AsyncMock()
                        mock_ms.__aenter__.return_value = mock_ms
                        mock_ms.search_with_entity_filters.return_value = mock_search_results
                        mock_service.return_value = mock_ms
                        
                        response = await async_client.get(
                            f"/api/v1/meilisearch/projects/{test_project.id}/search",
                            params={"q": "test query", "limit": 20}
                        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["accessType"] == "shared"
        
        # Verify that permission filter was applied
        call_args = mock_ms.search_with_entity_filters.call_args
        filters = call_args[1]["filters"]
        assert "review_status != 'irrelevant'" in filters.get("filter", "")
    
    @pytest.mark.asyncio
    async def test_unauthorized_user_search_denied(self, async_client, mock_db, unauthorized_user, test_project):
        """Test search denial for unauthorized user"""
        with patch("app.api.v1.endpoints.meilisearch_routes.get_db", return_value=mock_db):
            with patch("app.api.v1.endpoints.meilisearch_routes.get_current_active_user", return_value=unauthorized_user):
                with patch("app.api.v1.endpoints.meilisearch_routes._verify_project_access") as mock_verify:
                    mock_verify.return_value = {"has_access": False}
                    
                    response = await async_client.get(
                        f"/api/v1/meilisearch/projects/{test_project.id}/search",
                        params={"q": "test query"}
                    )
        
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_project_search_with_facets(self, async_client, mock_db, owner_user, test_project):
        """Test project search with facets"""
        mock_search_results = {
            "hits": [{"id": "page_1", "title": "Test Page"}],
            "totalHits": 1,
            "facetDistribution": {"language": {"en": 5, "fr": 2}},
            "processingTimeMs": 12
        }
        
        with patch("app.api.v1.endpoints.meilisearch_routes.get_db", return_value=mock_db):
            with patch("app.api.v1.endpoints.meilisearch_routes.get_current_active_user", return_value=owner_user):
                with patch("app.api.v1.endpoints.meilisearch_routes._verify_project_access") as mock_verify:
                    mock_verify.return_value = {
                        "has_access": True,
                        "access_type": "owner",
                        "project": test_project,
                        "share": None
                    }
                    
                    with patch("app.services.meilisearch_service.MeilisearchService.for_project") as mock_service:
                        mock_ms = AsyncMock()
                        mock_ms.__aenter__.return_value = mock_ms
                        mock_ms.search_with_entity_filters.return_value = mock_search_results
                        mock_service.return_value = mock_ms
                        
                        response = await async_client.get(
                            f"/api/v1/meilisearch/projects/{test_project.id}/search",
                            params={
                                "q": "test query",
                                "facets": "language,author,page_category"
                            }
                        )
        
        assert response.status_code == 200
        data = response.json()
        assert "facetDistribution" in data
        assert data["facetDistribution"]["language"] == {"en": 5, "fr": 2}
        
        # Verify facets were passed correctly
        call_args = mock_ms.search_with_entity_filters.call_args
        facets = call_args[1]["facets"]
        assert facets == ["language", "author", "page_category"]


class TestPublicSearch:
    """Test public search endpoint"""
    
    @pytest.mark.asyncio
    async def test_public_search_success(self, async_client, mock_db, test_project, public_config):
        """Test successful public search"""
        # Mock database queries
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [public_config, test_project]
        
        mock_search_results = {
            "hits": [{"id": "page_1", "title": "Public Page"}],
            "totalHits": 1,
            "processingTimeMs": 8
        }
        
        with patch("app.api.v1.endpoints.meilisearch_routes.get_db", return_value=mock_db):
            with patch("app.services.meilisearch_service.MeilisearchService.for_public") as mock_service:
                mock_ms = AsyncMock()
                mock_ms.__aenter__.return_value = mock_ms
                mock_ms.search_with_entity_filters.return_value = mock_search_results
                mock_service.return_value = mock_ms
                
                response = await async_client.get(
                    f"/api/v1/meilisearch/public/projects/{test_project.id}/search",
                    params={"q": "public query", "limit": 20}
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["hits"] == mock_search_results["hits"]
        assert data["projectTitle"] == "Public Test Project"
        assert data["isPublicSearch"] is True
        assert data["allowDownloads"] is False
    
    @pytest.mark.asyncio
    async def test_public_search_not_enabled(self, async_client, mock_db, test_project):
        """Test public search when not enabled"""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        
        with patch("app.api.v1.endpoints.meilisearch_routes.get_db", return_value=mock_db):
            response = await async_client.get(
                f"/api/v1/meilisearch/public/projects/{test_project.id}/search",
                params={"q": "query"}
            )
        
        assert response.status_code == 404
        assert "Public search not available" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_public_search_rate_limit_enforced(self, async_client, mock_db, test_project, public_config):
        """Test public search rate limiting"""
        # Simulate rate limit enforcement
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [public_config, test_project]
        
        with patch("app.api.v1.endpoints.meilisearch_routes.get_db", return_value=mock_db):
            # Test that limit parameter is capped at 50 for public access
            with patch("app.services.meilisearch_service.MeilisearchService.for_public") as mock_service:
                mock_ms = AsyncMock()
                mock_ms.__aenter__.return_value = mock_ms
                mock_ms.search_with_entity_filters.return_value = {"hits": [], "totalHits": 0}
                mock_service.return_value = mock_ms
                
                response = await async_client.get(
                    f"/api/v1/meilisearch/public/projects/{test_project.id}/search",
                    params={"q": "query", "limit": 100}  # Request 100 but should be capped
                )
        
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50  # Should be capped at 50 for public access


class TestTenantTokenSearch:
    """Test tenant token search endpoint"""
    
    @pytest.mark.asyncio
    async def test_tenant_token_search_success(self, async_client, test_project):
        """Test successful search with tenant token"""
        tenant_token = "valid_jwt_tenant_token"
        
        mock_search_results = {
            "hits": [{"id": "page_1", "title": "Shared Page"}],
            "totalHits": 1,
            "processingTimeMs": 7
        }
        
        with patch("app.services.meilisearch_service.MeilisearchService.for_tenant_token") as mock_service:
            mock_ms = AsyncMock()
            mock_ms.__aenter__.return_value = mock_ms
            mock_ms.search_with_entity_filters.return_value = mock_search_results
            mock_service.return_value = mock_ms
            
            response = await async_client.get(
                f"/api/v1/meilisearch/projects/{test_project.id}/search/tenant",
                params={
                    "tenant_token": tenant_token,
                    "q": "shared query",
                    "limit": 15
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["hits"] == mock_search_results["hits"]
        assert data["accessType"] == "tenant_token"
        assert data["limit"] == 15
        
        # Verify tenant token was used correctly
        mock_service.assert_called_once_with(tenant_token)
    
    @pytest.mark.asyncio
    async def test_tenant_token_search_invalid_token(self, async_client, test_project):
        """Test tenant token search with invalid token"""
        invalid_token = "invalid_token"
        
        with patch("app.services.meilisearch_service.MeilisearchService.for_tenant_token") as mock_service:
            mock_service.side_effect = Exception("Invalid token")
            
            response = await async_client.get(
                f"/api/v1/meilisearch/projects/{test_project.id}/search/tenant",
                params={
                    "tenant_token": invalid_token,
                    "q": "query"
                }
            )
        
        assert response.status_code == 500
        assert "Tenant search operation failed" in response.json()["detail"]


class TestMeilisearchHealth:
    """Test Meilisearch health endpoint"""
    
    @pytest.mark.asyncio
    async def test_meilisearch_health_success(self, async_client):
        """Test successful health check"""
        mock_health = {"status": "available"}
        
        with patch("app.services.meilisearch_service.MeilisearchService.for_admin") as mock_admin:
            mock_ms = AsyncMock()
            mock_ms.__aenter__.return_value = mock_ms
            mock_ms.client.health.return_value = mock_health
            mock_admin.return_value = mock_ms
            
            response = await async_client.get("/api/v1/meilisearch/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["meilisearch"] == mock_health
    
    @pytest.mark.asyncio
    async def test_meilisearch_health_failure(self, async_client):
        """Test health check failure"""
        with patch("app.services.meilisearch_service.MeilisearchService.for_admin") as mock_admin:
            mock_admin.side_effect = Exception("Connection failed")
            
            response = await async_client.get("/api/v1/meilisearch/health")
        
        assert response.status_code == 503
        assert "Meilisearch service unavailable" in response.json()["detail"]


class TestProjectAccessVerification:
    """Test project access verification helper"""
    
    @pytest.mark.asyncio
    async def test_verify_project_access_owner(self, mock_db, owner_user, test_project):
        """Test access verification for project owner"""
        mock_db.execute.return_value.scalar_one_or_none.return_value = test_project
        
        from app.api.v1.endpoints.meilisearch_routes import _verify_project_access
        
        result = await _verify_project_access(mock_db, test_project.id, owner_user.id)
        
        assert result["has_access"] is True
        assert result["access_type"] == "owner"
        assert result["project"] == test_project
        assert result["share"] is None
    
    @pytest.mark.asyncio
    async def test_verify_project_access_shared(self, mock_db, shared_user, test_project, project_share):
        """Test access verification for shared user"""
        # Mock owner query returning None, then shared query returning share
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.execute.return_value.first.return_value = (project_share, test_project)
        
        from app.api.v1.endpoints.meilisearch_routes import _verify_project_access
        
        result = await _verify_project_access(mock_db, test_project.id, shared_user.id)
        
        assert result["has_access"] is True
        assert result["access_type"] == "shared"
        assert result["project"] == test_project
        assert result["share"] == project_share
    
    @pytest.mark.asyncio
    async def test_verify_project_access_denied(self, mock_db, unauthorized_user, test_project):
        """Test access verification denial"""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.execute.return_value.first.return_value = None
        
        from app.api.v1.endpoints.meilisearch_routes import _verify_project_access
        
        result = await _verify_project_access(mock_db, test_project.id, unauthorized_user.id)
        
        assert result["has_access"] is False
    
    @pytest.mark.asyncio
    async def test_verify_project_access_expired_share(self, mock_db, shared_user, test_project, project_share):
        """Test access verification with expired share"""
        # Set share as expired
        project_share.expires_at = datetime.utcnow() - timedelta(hours=1)
        
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.execute.return_value.first.return_value = (project_share, test_project)
        
        from app.api.v1.endpoints.meilisearch_routes import _verify_project_access
        
        result = await _verify_project_access(mock_db, test_project.id, shared_user.id)
        
        assert result["has_access"] is False


class TestPermissionFiltering:
    """Test permission-based filtering"""
    
    def test_build_permission_filter_limited(self):
        """Test filter building for LIMITED permission"""
        from app.api.v1.endpoints.meilisearch_routes import _build_permission_filter
        
        permission = Mock()
        permission.value = 'limited'
        
        result = _build_permission_filter(permission)
        assert result == "review_status != 'irrelevant'"
    
    def test_build_permission_filter_restricted(self):
        """Test filter building for RESTRICTED permission"""
        from app.api.v1.endpoints.meilisearch_routes import _build_permission_filter
        
        permission = Mock()
        permission.value = 'restricted'
        
        result = _build_permission_filter(permission)
        assert result == "review_status = 'relevant'"
    
    def test_build_permission_filter_read(self):
        """Test filter building for READ permission (no filtering)"""
        from app.api.v1.endpoints.meilisearch_routes import _build_permission_filter
        
        permission = Mock()
        permission.value = 'read'
        
        result = _build_permission_filter(permission)
        assert result == ""


class TestErrorHandling:
    """Test error handling in search endpoints"""
    
    @pytest.mark.asyncio
    async def test_search_with_meilisearch_service_error(self, async_client, mock_db, owner_user, test_project):
        """Test search endpoint when MeilisearchService fails"""
        with patch("app.api.v1.endpoints.meilisearch_routes.get_db", return_value=mock_db):
            with patch("app.api.v1.endpoints.meilisearch_routes.get_current_active_user", return_value=owner_user):
                with patch("app.api.v1.endpoints.meilisearch_routes._verify_project_access") as mock_verify:
                    mock_verify.return_value = {
                        "has_access": True,
                        "access_type": "owner",
                        "project": test_project,
                        "share": None
                    }
                    
                    with patch("app.services.meilisearch_service.MeilisearchService.for_project") as mock_service:
                        mock_service.side_effect = Exception("Meilisearch connection failed")
                        
                        response = await async_client.get(
                            f"/api/v1/meilisearch/projects/{test_project.id}/search",
                            params={"q": "test query"}
                        )
        
        assert response.status_code == 500
        assert "Search operation failed" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_search_with_invalid_project_id(self, async_client, mock_db, owner_user):
        """Test search endpoint with invalid project ID"""
        with patch("app.api.v1.endpoints.meilisearch_routes.get_db", return_value=mock_db):
            with patch("app.api.v1.endpoints.meilisearch_routes.get_current_active_user", return_value=owner_user):
                with patch("app.api.v1.endpoints.meilisearch_routes._verify_project_access") as mock_verify:
                    mock_verify.return_value = {"has_access": False}
                    
                    response = await async_client.get(
                        "/api/v1/meilisearch/projects/99999/search",
                        params={"q": "test query"}
                    )
        
        assert response.status_code == 403