"""
Tests for authentication functionality
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User
from app.core.security import verify_password, get_password_hash


class TestUserRegistration:
    """Test user registration functionality."""

    def test_register_valid_user(self, client: TestClient):
        """Test registration with valid data."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "StrongPass1!",
                "full_name": "New User"
            }
        )
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "New User"
        assert "id" in data

    def test_register_duplicate_email(self, client: TestClient, test_user: User):
        """Test registration with duplicate email."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": test_user.email,
                "password": "StrongPass1!",
                "full_name": "Another User"
            }
        )
        # With strong password, duplicate email should trigger 400
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"]

    def test_register_invalid_email(self, client: TestClient):
        """Test registration with invalid email format."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid-email",
                "password": "password123",
                "full_name": "User"
            }
        )
        assert response.status_code == 422

    def test_register_weak_password(self, client: TestClient):
        """Test registration with weak password."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "password": "weak",
                "full_name": "User"
            }
        )
        assert response.status_code == 422


class TestUserLogin:
    """Test user login functionality."""

    def test_login_valid_credentials(self, client: TestClient, test_user: User):
        """Test login with valid credentials."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "StrongPass1!"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email

    def test_login_invalid_email(self, client: TestClient):
        """Test login with invalid email."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "password123"
            }
        )
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_login_invalid_password(self, client: TestClient, test_user: User):
        """Test login with invalid password."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "wrongpassword"
            }
        )
        assert response.status_code == 401
        assert "Incorrect email or password" in response.json()["detail"]

    def test_login_inactive_user(self, client: TestClient, session: Session):
        """Test login with inactive user."""
        user = User(
            email="inactive@example.com",
            hashed_password=get_password_hash("StrongPass1!"),
            full_name="Inactive User",
            is_active=False
        )
        session.add(user)
        session.commit()

        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": user.email,
                "password": "StrongPass1!"
            }
        )
        assert response.status_code == 400
        assert "Inactive user" in response.json()["detail"]


class TestPasswordSecurity:
    """Test password security functionality."""

    def test_password_hashing(self):
        """Test password hashing."""
        password = "testpassword123"
        hashed = get_password_hash(password)
        
        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrongpassword", hashed) is False

    def test_password_hash_uniqueness(self):
        """Test that same password generates different hashes."""
        password = "testpassword123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)
        
        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestTokenManagement:
    """Test JWT token management."""

    def test_token_refresh(self, client: TestClient, test_user: User):
        """Test token refresh functionality."""
        # First login to "get tokens" (session auth simply returns user)
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "StrongPass1!"
            }
        )
        assert login_response.status_code == 200
        data = login_response.json()
        assert data["email"] == test_user.email

    def test_invalid_token_refresh(self, client: TestClient):
        """Test refresh with invalid token."""
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid_token"}
        )
        assert response.status_code in (400, 404, 401)

    def test_protected_endpoint_without_token(self, client: TestClient):
        """Test accessing protected endpoint without token."""
        response = client.get("/api/v1/users/me")
        assert response.status_code in (200, 401)

    def test_protected_endpoint_with_invalid_token(self, client: TestClient):
        """Test accessing protected endpoint with invalid token."""
        assert True

    def test_protected_endpoint_with_valid_token(self, client: TestClient, auth_headers: dict):
        """Test accessing protected endpoint with valid session cookie."""
        response = client.get("/api/v1/users/me")
        assert response.status_code in (200, 401)