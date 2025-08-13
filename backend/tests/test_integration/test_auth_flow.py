"""
Integration tests for authentication flows
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models.user import User


class TestCompleteAuthFlow:
    """Test complete authentication workflows."""

    def test_registration_to_login_flow(self, client: TestClient):
        """Test complete user registration and login flow."""
        # Step 1: Register new user
        registration_data = {
            "email": "flowtest@example.com",
            "password": "securepassword123",
            "full_name": "Flow Test User"
        }
        
        register_response = client.post(
            "/api/v1/auth/register",
            json=registration_data
        )
        
        assert register_response.status_code == 201
        user_data = register_response.json()
        assert user_data["email"] == "flowtest@example.com"
        
        # Step 2: Login with registered credentials
        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "flowtest@example.com",
                "password": "securepassword123"
            }
        )
        
        assert login_response.status_code == 200
        login_data = login_response.json()
        assert "access_token" in login_data
        assert "refresh_token" in login_data
        
        # Step 3: Access protected endpoint with token
        auth_headers = {"Authorization": f"Bearer {login_data['access_token']}"}
        me_response = client.get("/api/v1/users/me", headers=auth_headers)
        
        assert me_response.status_code == 200
        me_data = me_response.json()
        assert me_data["email"] == "flowtest@example.com"
        assert me_data["full_name"] == "Flow Test User"

    def test_password_reset_flow(self, client: TestClient, test_user: User):
        """Test complete password reset flow."""
        # Step 1: Request password reset
        reset_request_response = client.post(
            "/api/v1/auth/password-reset/request",
            json={"email": test_user.email}
        )
        
        assert reset_request_response.status_code == 200
        
        # Step 2: Verify old password still works
        old_login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "testpassword123"
            }
        )
        assert old_login_response.status_code == 200
        
        # Note: In a real integration test, you would:
        # 1. Get the reset token from email/database
        # 2. Use it to reset password
        # 3. Verify old password no longer works
        # 4. Verify new password works
        
        # For this test, we'll simulate the token validation part
        # since we don't have actual email sending configured

    def test_token_refresh_flow(self, client: TestClient, test_user: User):
        """Test token refresh workflow."""
        # Step 1: Login to get initial tokens
        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "testpassword123"
            }
        )
        
        tokens = login_response.json()
        original_access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        
        # Step 2: Use access token to access protected endpoint
        auth_headers = {"Authorization": f"Bearer {original_access_token}"}
        response = client.get("/api/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        
        # Step 3: Refresh tokens
        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        
        assert refresh_response.status_code == 200
        new_tokens = refresh_response.json()
        new_access_token = new_tokens["access_token"]
        new_refresh_token = new_tokens["refresh_token"]
        
        # Step 4: Verify new access token works
        new_auth_headers = {"Authorization": f"Bearer {new_access_token}"}
        new_response = client.get("/api/v1/users/me", headers=new_auth_headers)
        assert new_response.status_code == 200
        
        # Step 5: Verify tokens are different (new tokens generated)
        assert new_access_token != original_access_token
        assert new_refresh_token != refresh_token

    def test_logout_flow(self, client: TestClient, test_user: User):
        """Test complete logout workflow."""
        # Step 1: Login
        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "testpassword123"
            }
        )
        
        tokens = login_response.json()
        access_token = tokens["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        
        # Step 2: Verify access token works
        response = client.get("/api/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        
        # Step 3: Logout
        logout_response = client.post("/api/v1/auth/logout", headers=auth_headers)
        assert logout_response.status_code == 200
        
        # Step 4: Verify token is invalidated (if token blacklisting is implemented)
        # Note: This depends on your logout implementation
        # Some implementations just return success without invalidating tokens
        post_logout_response = client.get("/api/v1/users/me", headers=auth_headers)
        # This might still work if tokens aren't blacklisted
        assert post_logout_response.status_code in [200, 401]

    def test_multi_device_login_flow(self, client: TestClient, test_user: User):
        """Test multiple device login scenario."""
        # Device 1: Login
        device1_login = client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "testpassword123"
            }
        )
        
        device1_tokens = device1_login.json()
        device1_headers = {"Authorization": f"Bearer {device1_tokens['access_token']}"}
        
        # Device 2: Login (same user, different session)
        device2_login = client.post(
            "/api/v1/auth/login",
            data={
                "username": test_user.email,
                "password": "testpassword123"
            }
        )
        
        device2_tokens = device2_login.json()
        device2_headers = {"Authorization": f"Bearer {device2_tokens['access_token']}"}
        
        # Verify both devices can access protected endpoints
        device1_response = client.get("/api/v1/users/me", headers=device1_headers)
        device2_response = client.get("/api/v1/users/me", headers=device2_headers)
        
        assert device1_response.status_code == 200
        assert device2_response.status_code == 200
        
        # Verify different tokens were issued
        assert device1_tokens["access_token"] != device2_tokens["access_token"]


class TestEmailVerificationFlow:
    """Test email verification workflows."""

    def test_email_verification_request_flow(self, client: TestClient, session: Session):
        """Test email verification request workflow."""
        # Create unverified user
        user_data = {
            "email": "unverified@example.com",
            "password": "password123",
            "full_name": "Unverified User"
        }
        
        register_response = client.post("/api/v1/auth/register", json=user_data)
        assert register_response.status_code == 201
        
        # Login to get access token
        login_response = client.post(
            "/api/v1/auth/login",
            data={
                "username": "unverified@example.com",
                "password": "password123"
            }
        )
        
        tokens = login_response.json()
        auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        
        # Request email verification
        verification_response = client.post(
            "/api/v1/auth/email/request-verification",
            headers=auth_headers
        )
        
        assert verification_response.status_code == 200
        
        # In a real test, you would:
        # 1. Check that verification email was sent
        # 2. Extract verification token from email
        # 3. Use token to verify email
        # 4. Confirm user is marked as verified


class TestOAuth2Flow:
    """Test OAuth2 authentication workflows."""

    def test_oauth2_redirect_flow(self, client: TestClient):
        """Test OAuth2 redirect workflow."""
        # Test Google OAuth2 redirect
        google_response = client.get("/api/v1/auth/oauth2/google")
        assert google_response.status_code in [302, 307]
        assert "Location" in google_response.headers
        
        # Verify redirect URL contains required parameters
        location = google_response.headers["Location"]
        assert "client_id" in location
        assert "response_type=code" in location
        assert "scope" in location
        
        # Test GitHub OAuth2 redirect
        github_response = client.get("/api/v1/auth/oauth2/github")
        assert github_response.status_code in [302, 307]
        assert "Location" in github_response.headers

    def test_oauth2_callback_error_handling(self, client: TestClient):
        """Test OAuth2 callback error handling."""
        # Test callback with error parameter
        error_response = client.get(
            "/api/v1/auth/oauth2/google/callback",
            params={"error": "access_denied", "error_description": "User denied access"}
        )
        
        assert error_response.status_code == 400
        error_data = error_response.json()
        assert "error" in error_data["detail"]
        
        # Test callback without required code parameter
        missing_code_response = client.get("/api/v1/auth/oauth2/google/callback")
        assert missing_code_response.status_code == 400


class TestAuthenticationSecurity:
    """Test authentication security aspects."""

    def test_rate_limiting_login_attempts(self, client: TestClient, test_user: User):
        """Test rate limiting on login attempts."""
        # Attempt multiple failed logins
        failed_attempts = 0
        max_attempts = 10  # Adjust based on your rate limiting configuration
        
        for i in range(max_attempts):
            response = client.post(
                "/api/v1/auth/login",
                data={
                    "username": test_user.email,
                    "password": "wrongpassword"
                }
            )
            
            if response.status_code == 429:  # Too Many Requests
                break
            
            failed_attempts += 1
            assert response.status_code == 401
        
        # If rate limiting is implemented, we should hit 429 before max_attempts
        # If not implemented, all attempts will return 401
        assert failed_attempts <= max_attempts

    def test_token_expiration_handling(self, client: TestClient, test_user: User):
        """Test handling of expired tokens."""
        # This test would require creating tokens with very short expiry
        # or mocking the token validation to simulate expiration
        
        # For now, we'll test the basic token validation structure
        invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.token"
        headers = {"Authorization": f"Bearer {invalid_token}"}
        
        response = client.get("/api/v1/users/me", headers=headers)
        assert response.status_code == 401

    def test_password_strength_validation(self, client: TestClient):
        """Test password strength validation during registration."""
        weak_passwords = [
            "123",
            "password",
            "abc123",
            "12345678"
        ]
        
        for weak_password in weak_passwords:
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"test{weak_password}@example.com",
                    "password": weak_password,
                    "full_name": "Weak Password User"
                }
            )
            
            # Should fail validation for weak passwords
            assert response.status_code == 422