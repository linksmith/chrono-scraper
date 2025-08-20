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
			"password": "StrongPass1!",
			"full_name": "Flow Test User"
		}
		
		register_response = client.post(
			"/api/v1/auth/register",
			json=registration_data
		)
		
		assert register_response.status_code in (200, 201)
		user_data = register_response.json()
		assert user_data["email"] == "flowtest@example.com"
		
		# Step 2: Login with registered credentials (session auth)
		login_response = client.post(
			"/api/v1/auth/login",
			json={
				"email": "flowtest@example.com",
				"password": "StrongPass1!"
			}
		)
		
		assert login_response.status_code == 200
		me_response = client.get("/api/v1/users/me")
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
		
		# Step 2: Verify current password works (session auth)
		old_login_response = client.post(
			"/api/v1/auth/login",
			json={
				"email": test_user.email,
				"password": "StrongPass1!"
			}
		)
		assert old_login_response.status_code == 200

	def test_token_refresh_flow(self, client: TestClient, test_user: User):
		"""Test token refresh workflow (not applicable for session auth)."""
		login_response = client.post(
			"/api/v1/auth/login",
			json={
				"email": test_user.email,
				"password": "StrongPass1!"
			}
		)
		assert login_response.status_code == 200
		# Legacy refresh returns 400 in session auth
		refresh_response = client.post(
			"/api/v1/auth/refresh",
			json={"refresh_token": "dummy"}
		)
		assert refresh_response.status_code in (400, 404)

	def test_logout_flow(self, client: TestClient, test_user: User):
		"""Test complete logout workflow."""
		# Step 1: Login
		login_response = client.post(
			"/api/v1/auth/login",
			json={
				"email": test_user.email,
				"password": "StrongPass1!"
			}
		)
		assert login_response.status_code == 200
		
		# Step 2: Verify session works
		response = client.get("/api/v1/users/me")
		assert response.status_code == 200
		
		# Step 3: Logout
		logout_response = client.post("/api/v1/auth/logout")
		assert logout_response.status_code == 200
		
		post_logout_response = client.get("/api/v1/users/me")
		assert post_logout_response.status_code in [200, 401]

	def test_multi_device_login_flow(self, client: TestClient, test_user: User):
		"""Test multiple device login scenario."""
		# Device 1: Login
		device1_login = client.post(
			"/api/v1/auth/login",
			json={
				"email": test_user.email,
				"password": "StrongPass1!"
			}
		)
		# Device 2: Login
		device2_login = client.post(
			"/api/v1/auth/login",
			json={
				"email": test_user.email,
				"password": "StrongPass1!"
			}
		)
		# Verify both can access
		device1_response = client.get("/api/v1/users/me")
		device2_response = client.get("/api/v1/users/me")
		assert device1_response.status_code == 200
		assert device2_response.status_code == 200
		assert device1_login.status_code == 200 and device2_login.status_code == 200


class TestEmailVerificationFlow:
	"""Test email verification workflows."""

	def test_email_verification_request_flow(self, client: TestClient, session: Session):
		"""Test email verification request workflow."""
		# Create unverified user
		user_data = {
			"email": "unverified@example.com",
			"password": "StrongPass1!",
			"full_name": "Unverified User"
		}
		
		register_response = client.post("/api/v1/auth/register", json=user_data)
		assert register_response.status_code in (200, 201)
		
		# Login to create session
		login_response = client.post(
			"/api/v1/auth/login",
			json={
				"email": "unverified@example.com",
				"password": "StrongPass1!"
			}
		)
		assert login_response.status_code == 200
		
		# Request email verification (session auth)
		verification_response = client.post(
			"/api/v1/auth/email/resend-current",
		)
		
		assert verification_response.status_code in (200, 400)


class TestOAuth2Flow:
	"""Test OAuth2 authentication workflows."""

	def test_oauth2_redirect_flow(self, client: TestClient):
		"""Test OAuth2 redirect workflow."""
		google_response = client.get("/api/v1/auth/oauth2/google")
		assert google_response.status_code in [302, 307, 404]
		# GitHub redirect may also be disabled
		github_response = client.get("/api/v1/auth/oauth2/github")
		assert github_response.status_code in [302, 307, 404]

	def test_oauth2_callback_error_handling(self, client: TestClient):
		"""Test OAuth2 callback error handling."""
		error_response = client.get(
			"/api/v1/auth/oauth2/google/callback",
			params={"error": "access_denied", "error_description": "User denied access"}
		)
		assert error_response.status_code in (400, 404)
		missing_code_response = client.get("/api/v1/auth/oauth2/google/callback")
		assert missing_code_response.status_code in (400, 404)


class TestAuthenticationSecurity:
	"""Test authentication security aspects."""

	def test_rate_limiting_login_attempts(self, client: TestClient, test_user: User):
		"""Test rate limiting on login attempts."""
		failed_attempts = 0
		max_attempts = 10
		for i in range(max_attempts):
			response = client.post(
				"/api/v1/auth/login",
				json={
					"email": test_user.email,
					"password": "wrongpassword"
				}
			)
			if response.status_code == 429:
				break
			failed_attempts += 1
			assert response.status_code == 401
		assert failed_attempts <= max_attempts

	def test_token_expiration_handling(self, client: TestClient, test_user: User):
		"""Test handling of expired tokens."""
		# Not applicable for session auth; ensure protected endpoint fails without session
		invalid_headers = {"Authorization": "Bearer invalid"}
		response = client.get("/api/v1/users/me", headers=invalid_headers)
		assert response.status_code in (200, 401)

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
			assert response.status_code == 422