"""
Basic tests to verify test setup works
"""
import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_mock_user_fixture(mock_user):
    """Test that mock user fixture works."""
    assert mock_user["email"] == "test@example.com"
    assert mock_user["full_name"] == "Test User"
    assert mock_user["is_active"] is True


def test_mock_project_fixture(mock_project, mock_user):
    """Test that mock project fixture works."""
    assert mock_project["name"] == "Test Project"
    assert mock_project["owner_id"] == mock_user["id"]
    assert mock_project["config"]["test"] is True


def test_auth_headers_fixture(auth_headers):
    """Test that auth fixture logs in with session successfully (cookies managed by client)."""
    assert isinstance(auth_headers, dict)


class TestPasswordSecurity:
    """Test password security functionality."""

    def test_password_hashing(self):
        """Test password hashing."""
        from passlib.context import CryptContext
        
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        password = "testpassword123"
        hashed = pwd_context.hash(password)
        
        assert hashed != password
        assert pwd_context.verify(password, hashed) is True
        assert pwd_context.verify("wrongpassword", hashed) is False

    def test_password_hash_uniqueness(self):
        """Test that same password generates different hashes."""
        from passlib.context import CryptContext
        
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        password = "testpassword123"
        hash1 = pwd_context.hash(password)
        hash2 = pwd_context.hash(password)
        
        assert hash1 != hash2
        assert pwd_context.verify(password, hash1) is True
        assert pwd_context.verify(password, hash2) is True


class TestUtilities:
    """Test utility functions."""

    def test_environment_setup(self):
        """Test that test environment is properly set up."""
        import os
        # Basic environment check
        assert os.path.exists(".")

    def test_imports(self):
        """Test that basic imports work."""
        import fastapi
        import sqlmodel
        import pytest
        
        assert fastapi is not None
        assert sqlmodel is not None
        assert pytest is not None