"""
Test configuration and fixtures for backend tests
"""
import asyncio
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session
from sqlmodel.pool import StaticPool
import os
import sys

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test.db"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(name="session")
def session_fixture():
    """Create a test database session."""
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture(name="app")
def app_fixture():
    """Create a minimal test FastAPI app."""
    app = FastAPI(title="Test App")
    
    @app.get("/health")
    def health_check():
        return {"status": "ok"}
    
    return app


@pytest.fixture(name="client")
def client_fixture(app: FastAPI):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    return {
        "id": 1,
        "email": "test@example.com",
        "hashed_password": pwd_context.hash("testpassword123"),
        "full_name": "Test User",
        "is_active": True,
        "is_verified": True
    }


@pytest.fixture
def mock_project(mock_user):
    """Create a mock project for testing."""
    return {
        "id": 1,
        "name": "Test Project",
        "description": "A test project",
        "owner_id": mock_user["id"],
        "config": {"test": True}
    }


@pytest.fixture
def auth_headers():
    """Get mock authentication headers."""
    return {"Authorization": "Bearer mock_jwt_token"}