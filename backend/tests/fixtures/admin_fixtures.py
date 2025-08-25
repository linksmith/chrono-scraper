"""
Admin test fixtures for comprehensive admin feature testing
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any
from fastapi.testclient import TestClient
from sqlmodel import select
from unittest.mock import AsyncMock, MagicMock

from app.models.user import User
from app.models.project import Project, Page
from app.models.entities import CanonicalEntity
from app.models.audit_log import AuditLog
from app.models.admin_settings import AdminSettings
from app.core.security import get_password_hash
from tests.conftest import AsyncSessionLocal


@pytest.fixture
async def admin_user_fixture():
    """Create a superuser admin for testing"""
    async with AsyncSessionLocal() as session:
        admin = User(
            email="admin@test.com",
            hashed_password=get_password_hash("AdminPass123!"),
            full_name="Test Admin",
            is_active=True,
            is_verified=True,
            is_superuser=True,
            approval_status="approved",
            data_handling_agreement=True,
            ethics_agreement=True,
            research_interests="System administration",
            research_purpose="Testing admin functionality",
            expected_usage="Administrative testing"
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin


@pytest.fixture
async def test_users_batch():
    """Create a batch of test users with various statuses"""
    users_data = [
        {
            "email": "active@test.com",
            "full_name": "Active User",
            "is_active": True,
            "is_verified": True,
            "approval_status": "approved"
        },
        {
            "email": "pending@test.com", 
            "full_name": "Pending User",
            "is_active": True,
            "is_verified": True,
            "approval_status": "pending"
        },
        {
            "email": "inactive@test.com",
            "full_name": "Inactive User", 
            "is_active": False,
            "is_verified": True,
            "approval_status": "approved"
        },
        {
            "email": "unverified@test.com",
            "full_name": "Unverified User",
            "is_active": True,
            "is_verified": False,
            "approval_status": "pending"
        },
        {
            "email": "rejected@test.com",
            "full_name": "Rejected User",
            "is_active": True,
            "is_verified": True,
            "approval_status": "rejected"
        }
    ]
    
    async with AsyncSessionLocal() as session:
        users = []
        for i, user_data in enumerate(users_data):
            user = User(
                email=user_data["email"],
                hashed_password=get_password_hash("TestPass123!"),
                full_name=user_data["full_name"],
                is_active=user_data["is_active"],
                is_verified=user_data["is_verified"],
                approval_status=user_data["approval_status"],
                data_handling_agreement=True,
                ethics_agreement=True,
                research_interests=f"Research area {i+1}",
                research_purpose=f"Purpose {i+1}",
                expected_usage="Testing purposes",
                created_at=datetime.utcnow() - timedelta(days=i+1)
            )
            session.add(user)
            users.append(user)
        
        await session.commit()
        for user in users:
            await session.refresh(user)
        return users


@pytest.fixture
async def test_projects_batch(test_users_batch):
    """Create test projects for users"""
    async with AsyncSessionLocal() as session:
        projects = []
        for i, user in enumerate(test_users_batch[:3]):  # Only create projects for first 3 users
            for j in range(2):  # 2 projects per user
                project = Project(
                    name=f"Test Project {i+1}-{j+1}",
                    description=f"Description for project {i+1}-{j+1}",
                    user_id=user.id,
                    created_at=datetime.utcnow() - timedelta(days=i*2+j)
                )
                session.add(project)
                projects.append(project)
        
        await session.commit()
        for project in projects:
            await session.refresh(project)
        return projects


@pytest.fixture
async def test_pages_batch(test_projects_batch, test_users_batch):
    """Create test pages for projects"""
    async with AsyncSessionLocal() as session:
        pages = []
        for i, project in enumerate(test_projects_batch[:2]):  # Only for first 2 projects
            for j in range(3):  # 3 pages per project
                page = Page(
                    url=f"https://example.com/page-{i+1}-{j+1}",
                    title=f"Test Page {i+1}-{j+1}",
                    content=f"Content for page {i+1}-{j+1} " * 50,  # Realistic content length
                    snapshot_date=datetime.utcnow() - timedelta(days=i+j),
                    user_id=test_users_batch[0].id,  # Assign to first user
                    project_id=project.id,
                    created_at=datetime.utcnow() - timedelta(days=i*2+j)
                )
                session.add(page)
                pages.append(page)
        
        await session.commit()
        for page in pages:
            await session.refresh(page)
        return pages


@pytest.fixture
async def test_entities_batch(test_pages_batch):
    """Create test entities"""
    async with AsyncSessionLocal() as session:
        entities = []
        entity_types = ["PERSON", "ORGANIZATION", "LOCATION", "EVENT"]
        
        for i, page in enumerate(test_pages_batch[:2]):  # Only for first 2 pages
            for j, entity_type in enumerate(entity_types):
                entity_name = f"Test {entity_type.lower()} {i+1}-{j+1}"
                entity = CanonicalEntity(
                    entity_type=entity_type.lower(),
                    primary_name=entity_name,
                    normalized_name=entity_name.lower(),
                    description=f"Description for {entity_type.lower()} {i+1}-{j+1}",
                    confidence_score=0.8 + (j * 0.05)
                )
                session.add(entity)
                entities.append(entity)
        
        await session.commit()
        for entity in entities:
            await session.refresh(entity)
        return entities


@pytest.fixture
async def test_audit_logs(admin_user_fixture, test_users_batch):
    """Create test audit logs"""
    async with AsyncSessionLocal() as session:
        logs = []
        actions = ["list_users", "update_user", "delete_user", "create_project", "system_health"]
        
        for i, action in enumerate(actions):
            log = AuditLog(
                admin_user_id=admin_user_fixture.id,
                user_id=test_users_batch[0].id if i % 2 == 0 else None,
                action=action,
                resource_type="user" if "user" in action else "system",
                resource_id=str(test_users_batch[0].id) if "user" in action else None,
                details={"test": True, "operation": f"test_operation_{i+1}"},
                ip_address="127.0.0.1",
                user_agent="pytest-admin-test",
                success=True,
                affected_count=1,
                created_at=datetime.utcnow() - timedelta(hours=i+1)
            )
            session.add(log)
            logs.append(log)
        
        await session.commit()
        for log in logs:
            await session.refresh(log)
        return logs


@pytest.fixture
def mock_session_store():
    """Mock session store for testing"""
    class MockSessionData:
        def __init__(self, session_id: str, user_id: int, user_email: str):
            self.session_id = session_id
            self.user_id = user_id
            self.user_email = user_email
            self.created_at = datetime.utcnow()
            self.last_activity = datetime.utcnow()
            self.ip_address = "127.0.0.1"
            self.user_agent = "pytest-test-agent"
            self.is_active = True
            self.expires_at = datetime.utcnow() + timedelta(hours=24)

    mock_store = MagicMock()
    
    # Sample sessions
    sessions = [
        MockSessionData("session_1", 1, "user1@test.com"),
        MockSessionData("session_2", 2, "user2@test.com"),
        MockSessionData("session_3", 3, "user3@test.com")
    ]
    
    mock_store.get_all_sessions = AsyncMock(return_value=sessions)
    mock_store.get_session = AsyncMock(return_value=sessions[0])
    mock_store.delete_session = AsyncMock(return_value=True)
    
    return mock_store


@pytest.fixture
def mock_redis():
    """Mock Redis for session storage testing"""
    class MockRedis:
        def __init__(self):
            self.data = {}
        
        async def setex(self, key: str, ttl: int, value: str):
            self.data[key] = value
        
        async def get(self, key: str):
            return self.data.get(key)
        
        async def delete(self, key: str):
            return self.data.pop(key, None) is not None
        
        async def exists(self, key: str):
            return key in self.data
        
        async def scan_iter(self, match: str = None):
            for key in self.data.keys():
                if match is None or key.startswith(match.replace("*", "")):
                    yield key
    
    return MockRedis()


@pytest.fixture
def admin_auth_headers(client: TestClient):
    """Create authentication headers for admin user"""
    # Register admin user
    admin_data = {
        "email": "admin-test@example.com",
        "password": "AdminPass123!",
        "full_name": "Admin Test User"
    }
    
    resp = client.post("/api/v1/auth/register", json=admin_data)
    assert resp.status_code in (200, 201)
    
    # Set user as superuser in database
    async def _set_superuser():
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.email == admin_data["email"]))
            user = result.scalar_one_or_none()
            if user:
                user.is_superuser = True
                user.is_verified = True
                user.approval_status = "approved"
                await session.commit()
    
    asyncio.get_event_loop().run_until_complete(_set_superuser())
    
    # Login
    login_resp = client.post("/api/v1/auth/login", json={
        "email": admin_data["email"],
        "password": admin_data["password"]
    })
    assert login_resp.status_code == 200
    
    return {}  # TestClient handles cookies automatically


@pytest.fixture
def bulk_operation_data():
    """Test data for bulk operations"""
    return {
        "user_ids_to_approve": [1, 2, 3],
        "user_ids_to_reject": [4, 5],
        "user_ids_to_deactivate": [6, 7, 8],
        "session_ids_to_revoke": ["session_1", "session_2", "session_3"],
        "export_filters": {
            "start_date": datetime.utcnow() - timedelta(days=30),
            "end_date": datetime.utcnow(),
            "include_inactive": False
        }
    }


@pytest.fixture
def performance_test_data():
    """Large dataset for performance testing"""
    users_data = []
    for i in range(100):  # Create 100 test users
        users_data.append({
            "email": f"perftest{i}@test.com",
            "password": "TestPass123!",
            "full_name": f"Performance Test User {i}",
            "is_active": i % 10 != 0,  # 90% active
            "is_verified": i % 5 != 0,  # 80% verified
            "approval_status": "approved" if i % 3 == 0 else "pending"
        })
    return users_data


@pytest.fixture
def system_health_mock_data():
    """Mock data for system health checks"""
    return {
        "database_healthy": True,
        "redis_healthy": True,
        "meilisearch_healthy": True,
        "celery_healthy": True,
        "firecrawl_healthy": True,
        "response_times": {
            "database": 12.5,
            "redis": 2.1,
            "meilisearch": 45.3,
            "celery": 8.7,
            "firecrawl": 156.2
        },
        "metrics": {
            "active_sessions": 25,
            "total_users": 150,
            "active_tasks": 3,
            "queue_depth": 12
        }
    }


@pytest.fixture
def admin_settings_data():
    """Test data for admin settings"""
    return {
        "signup_enabled": True,
        "approval_required": True,
        "email_verification_required": True,
        "max_projects_per_user": 10,
        "session_timeout_hours": 24,
        "rate_limit_enabled": True,
        "maintenance_mode": False,
        "backup_retention_days": 30,
        "log_retention_days": 90
    }


@pytest.fixture
async def cleanup_admin_test_data():
    """Cleanup fixture that runs after admin tests"""
    yield
    
    # Cleanup test data after tests complete
    async with AsyncSessionLocal() as session:
        # Clean up in reverse dependency order
        await session.execute("DELETE FROM audit_logs WHERE ip_address = '127.0.0.1'")
        await session.execute("DELETE FROM canonical_entities WHERE primary_name LIKE 'Test %'")
        await session.execute("DELETE FROM pages WHERE url LIKE 'https://example.com/page-%'")
        await session.execute("DELETE FROM projects WHERE name LIKE 'Test Project %'")
        await session.execute("DELETE FROM users WHERE email LIKE '%test.com' OR email LIKE '%example.com'")
        await session.commit()