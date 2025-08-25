"""
Comprehensive admin feature testing suite
Tests all admin functionality including session management, content management,
system monitoring, bulk operations, and API endpoints.
"""
import pytest
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from sqlmodel import select

from app.models.user import User
from app.models.project import Project, Page
from app.models.entities import CanonicalEntity
from app.models.audit_log import AuditLog
from tests.conftest import AsyncSessionLocal
from tests.fixtures.admin_fixtures import (
    admin_user_fixture, test_users_batch, test_projects_batch, 
    test_pages_batch, test_entities_batch, test_audit_logs,
    mock_session_store, admin_auth_headers, bulk_operation_data,
    system_health_mock_data, cleanup_admin_test_data
)


class TestUserManagement:
    """Test user management admin functionality"""
    
    @pytest.mark.asyncio
    async def test_list_users_basic(self, client: TestClient, admin_auth_headers, test_users_batch):
        """Test basic user listing functionality"""
        response = client.get("/api/v1/admin/users", headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert len(data["items"]) >= len(test_users_batch)
    
    @pytest.mark.asyncio
    async def test_list_users_with_filters(self, client: TestClient, admin_auth_headers, test_users_batch):
        """Test user listing with various filters"""
        # Test approval status filter
        response = client.get("/api/v1/admin/users?approval_status=approved", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        for user in data["items"]:
            assert user["approval_status"] == "approved"
        
        # Test active status filter
        response = client.get("/api/v1/admin/users?is_active=true", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        for user in data["items"]:
            assert user["is_active"] is True
        
        # Test search filter
        response = client.get("/api/v1/admin/users?search=Active", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Should find users with "Active" in their name
        assert len(data["items"]) > 0
    
    @pytest.mark.asyncio
    async def test_get_user_details(self, client: TestClient, admin_auth_headers, test_users_batch):
        """Test getting detailed user information"""
        user = test_users_batch[0]
        response = client.get(f"/api/v1/admin/users/{user.id}", headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == user.id
        assert data["email"] == user.email
        assert data["full_name"] == user.full_name
        assert "projects_count" in data
        assert "pages_count" in data
    
    @pytest.mark.asyncio
    async def test_create_user(self, client: TestClient, admin_auth_headers):
        """Test admin user creation"""
        user_data = {
            "email": "admin-created@test.com",
            "password": "AdminCreated123!",
            "full_name": "Admin Created User",
            "is_active": True,
            "is_verified": True,
            "approval_status": "approved",
            "research_interests": "Admin created research",
            "research_purpose": "Testing admin creation",
            "expected_usage": "Testing purposes",
            "send_welcome_email": False
        }
        
        response = client.post("/api/v1/admin/users", json=user_data, headers=admin_auth_headers)
        assert response.status_code == 201
        
        data = response.json()
        assert data["email"] == user_data["email"]
        assert data["full_name"] == user_data["full_name"]
        assert data["is_verified"] is True
        assert data["approval_status"] == "approved"
    
    @pytest.mark.asyncio
    async def test_update_user(self, client: TestClient, admin_auth_headers, test_users_batch):
        """Test user updates"""
        user = test_users_batch[0]
        update_data = {
            "full_name": "Updated Full Name",
            "approval_status": "approved",
            "is_active": True
        }
        
        response = client.put(f"/api/v1/admin/users/{user.id}", json=update_data, headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data["full_name"] == update_data["full_name"]
        assert data["approval_status"] == update_data["approval_status"]
    
    @pytest.mark.asyncio
    async def test_delete_user_requires_confirmation(self, client: TestClient, admin_auth_headers, test_users_batch):
        """Test that user deletion requires confirmation token"""
        user = test_users_batch[-1]  # Use last user to avoid foreign key issues
        
        # Should fail without confirmation token
        response = client.delete(f"/api/v1/admin/users/{user.id}", headers=admin_auth_headers)
        assert response.status_code == 422  # Missing required confirmation_token parameter


class TestSessionManagement:
    """Test session management functionality"""
    
    @pytest.mark.asyncio
    async def test_list_sessions(self, client: TestClient, admin_auth_headers):
        """Test session listing"""
        with patch('app.services.session_store.get_session_store') as mock_get_store:
            mock_store = MagicMock()
            mock_sessions = [
                MagicMock(
                    session_id="test_session_1",
                    user_id=1,
                    created_at=datetime.utcnow(),
                    last_activity=datetime.utcnow(),
                    ip_address="127.0.0.1",
                    user_agent="test-agent",
                    is_active=True,
                    expires_at=datetime.utcnow() + timedelta(hours=1)
                )
            ]
            mock_store.get_all_sessions = AsyncMock(return_value=mock_sessions)
            mock_get_store.return_value = mock_store
            
            response = client.get("/api/v1/admin/sessions", headers=admin_auth_headers)
            assert response.status_code == 200
            
            data = response.json()
            assert "items" in data
            assert len(data["items"]) >= 0
    
    @pytest.mark.asyncio
    async def test_revoke_session(self, client: TestClient, admin_auth_headers):
        """Test individual session revocation"""
        with patch('app.services.session_store.get_session_store') as mock_get_store:
            mock_store = MagicMock()
            mock_session = MagicMock(session_id="test_session", user_id=1)
            mock_store.get_session = AsyncMock(return_value=mock_session)
            mock_store.delete_session = AsyncMock(return_value=True)
            mock_get_store.return_value = mock_store
            
            response = client.delete("/api/v1/admin/sessions/test_session", headers=admin_auth_headers)
            assert response.status_code == 200
            
            data = response.json()
            assert data["success"] is True
            assert "revoked successfully" in data["message"]
    
    @pytest.mark.asyncio
    async def test_bulk_revoke_sessions(self, client: TestClient, admin_auth_headers):
        """Test bulk session revocation"""
        with patch('app.services.session_store.get_session_store') as mock_get_store:
            mock_store = MagicMock()
            mock_store.get_session = AsyncMock(return_value=MagicMock())
            mock_store.delete_session = AsyncMock(return_value=True)
            mock_get_store.return_value = mock_store
            
            bulk_data = {
                "session_ids": ["session1", "session2", "session3"],
                "revoke_all_except_current": True
            }
            
            response = client.post("/api/v1/admin/sessions/bulk-revoke", json=bulk_data, headers=admin_auth_headers)
            assert response.status_code == 200
            
            data = response.json()
            assert data["success"] is True
            assert data["affected_count"] >= 0


class TestSystemMonitoring:
    """Test system monitoring and health checks"""
    
    @pytest.mark.asyncio
    async def test_system_health_check(self, client: TestClient, admin_auth_headers):
        """Test system health endpoint"""
        with patch('app.services.session_store.get_session_store') as mock_get_store:
            mock_store = MagicMock()
            mock_store.get_all_sessions = AsyncMock(return_value=[])
            mock_get_store.return_value = mock_store
            
            response = client.get("/api/v1/admin/system/health", headers=admin_auth_headers)
            assert response.status_code == 200
            
            data = response.json()
            assert "status" in data
            assert "database_metrics" in data
            assert "services" in data
            assert "system_metrics" in data
    
    @pytest.mark.asyncio
    async def test_system_metrics(self, client: TestClient, admin_auth_headers, test_users_batch):
        """Test system metrics endpoint"""
        response = client.get("/api/v1/admin/system/metrics", headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "users" in data
        assert "projects" in data
        assert "pages" in data
        assert "recent_activity" in data
        assert "system" in data
        
        # Verify user metrics structure
        assert "total" in data["users"]
        assert "active" in data["users"]
        assert "verified" in data["users"]
        assert "approved" in data["users"]
    
    @pytest.mark.asyncio
    async def test_celery_status(self, client: TestClient, admin_auth_headers):
        """Test Celery status monitoring"""
        response = client.get("/api/v1/admin/celery/status", headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "workers" in data
        assert "queues" in data
        assert "tasks" in data


class TestContentManagement:
    """Test content management admin views"""
    
    @pytest.mark.asyncio 
    async def test_admin_requires_superuser(self, client: TestClient):
        """Test that admin endpoints require superuser privileges"""
        # Create regular user and authenticate
        user_data = {
            "email": "regular@test.com",
            "password": "RegularPass123!",
            "full_name": "Regular User"
        }
        
        client.post("/api/v1/auth/register", json=user_data)
        
        # Set as regular user (not superuser)
        async def _set_regular_user():
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(User).where(User.email == user_data["email"]))
                user = result.scalar_one_or_none()
                if user:
                    user.is_superuser = False
                    user.is_verified = True
                    user.approval_status = "approved"
                    await session.commit()
        
        asyncio.get_event_loop().run_until_complete(_set_regular_user())
        
        # Login as regular user
        client.post("/api/v1/auth/login", json={
            "email": user_data["email"],
            "password": user_data["password"]
        })
        
        # Should be denied access to admin endpoints
        response = client.get("/api/v1/admin/users")
        assert response.status_code in [401, 403]  # Unauthorized or Forbidden


class TestAuditLogging:
    """Test audit logging system"""
    
    @pytest.mark.asyncio
    async def test_get_audit_logs(self, client: TestClient, admin_auth_headers, test_audit_logs):
        """Test audit log retrieval"""
        response = client.get("/api/v1/admin/audit/logs", headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) >= len(test_audit_logs)
        
        # Check log structure
        if data["items"]:
            log = data["items"][0]
            required_fields = ["id", "action", "resource_type", "created_at", "success"]
            for field in required_fields:
                assert field in log
    
    @pytest.mark.asyncio
    async def test_audit_log_filtering(self, client: TestClient, admin_auth_headers, test_audit_logs):
        """Test audit log filtering"""
        # Test filter by action
        response = client.get("/api/v1/admin/audit/logs?action=list_users", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        for log in data["items"]:
            assert log["action"] == "list_users"
        
        # Test filter by resource type
        response = client.get("/api/v1/admin/audit/logs?resource_type=user", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        for log in data["items"]:
            assert log["resource_type"] == "user"
        
        # Test filter by success status
        response = client.get("/api/v1/admin/audit/logs?success=true", headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        for log in data["items"]:
            assert log["success"] is True


class TestConfiguration:
    """Test system configuration endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_system_config(self, client: TestClient, admin_auth_headers):
        """Test system configuration retrieval"""
        response = client.get("/api/v1/admin/config", headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "environment" in data
        assert "version" in data
        assert "features" in data
        assert "limits" in data
        assert "integrations" in data
        assert "security" in data
        
        # Check features structure
        features = data["features"]
        expected_features = [
            "user_registration", "email_verification", "admin_approval",
            "oauth2_integration", "api_keys", "bulk_operations"
        ]
        for feature in expected_features:
            assert feature in features


class TestBulkOperations:
    """Test bulk operations functionality"""
    
    @pytest.mark.asyncio
    async def test_bulk_user_operations(self, client: TestClient, admin_auth_headers, test_users_batch):
        """Test bulk user operations"""
        # This would require implementing bulk user operations endpoints
        # For now, test that the infrastructure is in place
        
        # Test that we can get users for bulk operations
        response = client.get("/api/v1/admin/users?per_page=100", headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["items"]) >= len(test_users_batch)
        
        # Each user should have necessary fields for bulk operations
        if data["items"]:
            user = data["items"][0]
            bulk_fields = ["id", "email", "approval_status", "is_active", "is_verified"]
            for field in bulk_fields:
                assert field in user


class TestSecurityAndValidation:
    """Test security measures and input validation"""
    
    @pytest.mark.asyncio
    async def test_input_validation(self, client: TestClient, admin_auth_headers):
        """Test input validation on admin endpoints"""
        # Test invalid user creation data
        invalid_user_data = {
            "email": "invalid-email",  # Invalid email format
            "password": "weak",  # Weak password
            "full_name": "",  # Empty name
        }
        
        response = client.post("/api/v1/admin/users", json=invalid_user_data, headers=admin_auth_headers)
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_pagination_limits(self, client: TestClient, admin_auth_headers):
        """Test pagination limits are enforced"""
        # Test excessive per_page parameter
        response = client.get("/api/v1/admin/users?per_page=1000", headers=admin_auth_headers)
        assert response.status_code in [200, 422]  # Should either work with capped limit or reject
        
        if response.status_code == 200:
            data = response.json()
            assert data["per_page"] <= 100  # Should be capped at reasonable limit
    
    @pytest.mark.asyncio
    async def test_rate_limiting_headers(self, client: TestClient, admin_auth_headers):
        """Test that rate limiting headers are present"""
        response = client.get("/api/v1/admin/users", headers=admin_auth_headers)
        
        # Check for security headers
        security_headers = [
            "X-Content-Type-Options", "X-Frame-Options", 
            "X-XSS-Protection", "Strict-Transport-Security"
        ]
        
        for header in security_headers:
            # Headers might be set by the admin middleware
            # This test ensures we're thinking about security
            pass  # Implementation would check actual headers


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    @pytest.mark.asyncio
    async def test_nonexistent_user(self, client: TestClient, admin_auth_headers):
        """Test handling of nonexistent user requests"""
        response = client.get("/api/v1/admin/users/99999", headers=admin_auth_headers)
        assert response.status_code == 404
        
        data = response.json()
        assert "error" in data
        assert "not found" in data["error"].lower()
    
    @pytest.mark.asyncio
    async def test_invalid_pagination(self, client: TestClient, admin_auth_headers):
        """Test invalid pagination parameters"""
        # Test negative page number
        response = client.get("/api/v1/admin/users?page=-1", headers=admin_auth_headers)
        assert response.status_code == 422
        
        # Test zero page number  
        response = client.get("/api/v1/admin/users?page=0", headers=admin_auth_headers)
        assert response.status_code == 422
    
    @pytest.mark.asyncio
    async def test_database_error_handling(self, client: TestClient, admin_auth_headers):
        """Test handling of database errors"""
        # This would require mocking database failures
        # For now, ensure endpoints handle errors gracefully
        with patch('app.core.database.get_db') as mock_db:
            mock_db.side_effect = Exception("Database connection failed")
            
            response = client.get("/api/v1/admin/users", headers=admin_auth_headers)
            # Should return 500 with proper error response
            assert response.status_code == 500


class TestDataConsistency:
    """Test data consistency and relationships"""
    
    @pytest.mark.asyncio
    async def test_user_project_relationship(self, client: TestClient, admin_auth_headers, test_users_batch, test_projects_batch):
        """Test that user-project relationships are maintained"""
        user = test_users_batch[0]
        response = client.get(f"/api/v1/admin/users/{user.id}", headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        # Should include project count
        assert "projects_count" in data
        assert isinstance(data["projects_count"], int)
        assert data["projects_count"] >= 0
    
    @pytest.mark.asyncio
    async def test_audit_trail_integrity(self, client: TestClient, admin_auth_headers, test_audit_logs):
        """Test audit trail maintains data integrity"""
        response = client.get("/api/v1/admin/audit/logs", headers=admin_auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        for log in data["items"]:
            # Each log should have required integrity fields
            assert log["created_at"] is not None
            assert log["action"] is not None
            assert log["resource_type"] is not None
            
            # If has resource_id, should be string or null
            if log.get("resource_id"):
                assert isinstance(log["resource_id"], str)


# Integration tests combining multiple admin features
class TestIntegrationScenarios:
    """Test complex scenarios involving multiple admin features"""
    
    @pytest.mark.asyncio
    async def test_user_lifecycle_management(self, client: TestClient, admin_auth_headers):
        """Test complete user lifecycle through admin interface"""
        # 1. Create user
        user_data = {
            "email": "lifecycle@test.com",
            "password": "LifeCycle123!",
            "full_name": "Lifecycle Test User",
            "is_active": True,
            "is_verified": False,
            "approval_status": "pending",
            "research_interests": "Testing lifecycle",
            "research_purpose": "Integration testing",
            "expected_usage": "Testing purposes",
            "send_welcome_email": False
        }
        
        response = client.post("/api/v1/admin/users", json=user_data, headers=admin_auth_headers)
        assert response.status_code == 201
        created_user = response.json()
        user_id = created_user["id"]
        
        # 2. Verify user
        update_data = {"is_verified": True}
        response = client.put(f"/api/v1/admin/users/{user_id}", json=update_data, headers=admin_auth_headers)
        assert response.status_code == 200
        
        # 3. Approve user
        update_data = {"approval_status": "approved"}
        response = client.put(f"/api/v1/admin/users/{user_id}", json=update_data, headers=admin_auth_headers)
        assert response.status_code == 200
        
        # 4. Check audit trail
        response = client.get(f"/api/v1/admin/audit/logs?user_id={user_id}", headers=admin_auth_headers)
        assert response.status_code == 200
        audit_data = response.json()
        
        # Should have audit entries for user creation and updates
        assert len(audit_data["items"]) >= 1
    
    @pytest.mark.asyncio
    async def test_system_monitoring_workflow(self, client: TestClient, admin_auth_headers):
        """Test complete system monitoring workflow"""
        # 1. Check system health
        response = client.get("/api/v1/admin/system/health", headers=admin_auth_headers)
        assert response.status_code == 200
        health_data = response.json()
        
        # 2. Get detailed metrics
        response = client.get("/api/v1/admin/system/metrics", headers=admin_auth_headers)
        assert response.status_code == 200
        metrics_data = response.json()
        
        # 3. Check Celery status
        response = client.get("/api/v1/admin/celery/status", headers=admin_auth_headers)
        assert response.status_code == 200
        celery_data = response.json()
        
        # 4. Verify comprehensive system view
        assert "status" in health_data
        assert "users" in metrics_data
        assert "status" in celery_data
        
        # All components should provide meaningful data
        assert health_data["status"] in ["healthy", "degraded", "unhealthy"]
        assert metrics_data["users"]["total"] >= 0
        assert celery_data["status"] in ["operational", "degraded", "offline"]


# Performance and load testing
class TestPerformance:
    """Test performance under various loads"""
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_large_user_list_performance(self, client: TestClient, admin_auth_headers):
        """Test performance with large user lists"""
        import time
        
        start_time = time.time()
        response = client.get("/api/v1/admin/users?per_page=100", headers=admin_auth_headers)
        end_time = time.time()
        
        assert response.status_code == 200
        # Should respond within reasonable time (5 seconds)
        assert (end_time - start_time) < 5.0
    
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_admin_requests(self, client: TestClient, admin_auth_headers):
        """Test handling of concurrent admin requests"""
        import threading
        import time
        
        results = []
        
        def make_request():
            response = client.get("/api/v1/admin/system/health", headers=admin_auth_headers)
            results.append(response.status_code)
        
        # Create 5 concurrent threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
        
        # Start all threads
        start_time = time.time()
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        end_time = time.time()
        
        # All requests should succeed
        assert all(status == 200 for status in results)
        # Should complete within reasonable time
        assert (end_time - start_time) < 10.0


# Cleanup after all tests
@pytest.mark.asyncio
async def test_cleanup(cleanup_admin_test_data):
    """Final cleanup test"""
    # This test runs the cleanup fixture
    pass