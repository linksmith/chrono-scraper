#!/usr/bin/env python3
"""
OAuth2 Integration Test Script

This script tests the OAuth2 integration without requiring actual OAuth2 provider setup.
It validates the core OAuth2 functionality, state management, and error handling.

Usage:
    python test_oauth2_integration.py
"""

import asyncio
import json
import sys
import os
from unittest.mock import Mock, patch, AsyncMock

# Add the backend app to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '.'))

from app.core.config import settings
from app.services.oauth2_providers import oauth2_manager, GoogleOAuth2Provider, GitHubOAuth2Provider
from app.core.oauth2 import OAuth2StateManager, get_oauth2_provider, normalize_oauth2_user_data


class OAuth2IntegrationTester:
    """Test OAuth2 integration functionality"""
    
    def __init__(self):
        self.passed_tests = 0
        self.failed_tests = 0
    
    def log_test(self, test_name: str, passed: bool, message: str = ""):
        """Log test result"""
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {test_name}: {message}")
        
        if passed:
            self.passed_tests += 1
        else:
            self.failed_tests += 1
    
    def test_provider_initialization(self):
        """Test OAuth2 provider initialization"""
        print("\n=== Testing Provider Initialization ===")
        
        # Test Google provider
        try:
            google_provider = GoogleOAuth2Provider(
                client_id="test_client_id",
                client_secret="test_client_secret",
                redirect_uri="http://localhost:8000/api/v1/auth/oauth2/google/callback"
            )
            
            assert google_provider.client_id == "test_client_id"
            assert google_provider.client_secret == "test_client_secret"
            assert "google" in google_provider.redirect_uri
            
            self.log_test("Google Provider Init", True, "Provider initialized correctly")
        except Exception as e:
            self.log_test("Google Provider Init", False, f"Error: {e}")
        
        # Test GitHub provider
        try:
            github_provider = GitHubOAuth2Provider(
                client_id="test_client_id",
                client_secret="test_client_secret", 
                redirect_uri="http://localhost:8000/api/v1/auth/oauth2/github/callback"
            )
            
            assert github_provider.client_id == "test_client_id"
            assert github_provider.client_secret == "test_client_secret"
            assert "github" in github_provider.redirect_uri
            
            self.log_test("GitHub Provider Init", True, "Provider initialized correctly")
        except Exception as e:
            self.log_test("GitHub Provider Init", False, f"Error: {e}")
    
    def test_authorization_urls(self):
        """Test OAuth2 authorization URL generation"""
        print("\n=== Testing Authorization URLs ===")
        
        # Test Google authorization URL
        try:
            google_provider = GoogleOAuth2Provider(
                client_id="test_client_id",
                client_secret="test_client_secret",
                redirect_uri="http://localhost:8000/api/v1/auth/oauth2/google/callback"
            )
            
            auth_url = google_provider.get_authorization_url("test_state")
            
            assert "accounts.google.com/o/oauth2" in auth_url
            assert "client_id=test_client_id" in auth_url
            assert "state=test_state" in auth_url
            assert "scope=" in auth_url
            
            self.log_test("Google Auth URL", True, f"URL generated: {auth_url[:60]}...")
        except Exception as e:
            self.log_test("Google Auth URL", False, f"Error: {e}")
        
        # Test GitHub authorization URL
        try:
            github_provider = GitHubOAuth2Provider(
                client_id="test_client_id",
                client_secret="test_client_secret",
                redirect_uri="http://localhost:8000/api/v1/auth/oauth2/github/callback"
            )
            
            auth_url = github_provider.get_authorization_url("test_state")
            
            assert "github.com/login/oauth/authorize" in auth_url
            assert "client_id=test_client_id" in auth_url
            assert "state=test_state" in auth_url
            assert "scope=" in auth_url
            
            self.log_test("GitHub Auth URL", True, f"URL generated: {auth_url[:60]}...")
        except Exception as e:
            self.log_test("GitHub Auth URL", False, f"Error: {e}")
    
    async def test_state_management(self):
        """Test OAuth2 state management with Redis"""
        print("\n=== Testing State Management ===")
        
        try:
            # Mock Redis session store
            mock_redis = AsyncMock()
            mock_session_store = AsyncMock()
            mock_session_store.redis = mock_redis
            
            with patch('app.services.session_store.get_session_store', return_value=mock_session_store):
                # Test state creation
                state = await OAuth2StateManager.create_state("google")
                
                assert len(state) > 20  # Should be a long random string
                mock_redis.setex.assert_called_once()
                
                # Verify the call arguments
                call_args = mock_redis.setex.call_args
                assert call_args[0][0] == f"oauth2_state:{state}"
                assert call_args[0][1] == 600  # 10 minutes
                assert call_args[0][2] == "google:anonymous"
                
                self.log_test("State Creation", True, f"State created: {state[:10]}...")
                
                # Test state validation
                mock_redis.get.return_value = b"google:anonymous"
                is_valid = await OAuth2StateManager.validate_state(state, "google")
                
                assert is_valid is True
                self.log_test("State Validation", True, "State validated successfully")
                
                # Test state consumption
                mock_redis.get.return_value = b"google:anonymous"
                consumed_state = await OAuth2StateManager.consume_state(state)
                
                assert consumed_state is not None
                assert consumed_state["provider"] == "google"
                mock_redis.delete.assert_called_with(f"oauth2_state:{state}")
                
                self.log_test("State Consumption", True, "State consumed successfully")
                
        except Exception as e:
            self.log_test("State Management", False, f"Error: {e}")
    
    def test_user_data_normalization(self):
        """Test OAuth2 user data normalization"""
        print("\n=== Testing User Data Normalization ===")
        
        # Test Google user data normalization
        try:
            google_data = {
                "id": "123456789",
                "email": "test@example.com",
                "name": "Test User",
                "verified_email": True
            }
            
            normalized = normalize_oauth2_user_data("google", google_data)
            
            assert normalized["email"] == "test@example.com"
            assert normalized["full_name"] == "Test User"
            assert normalized["oauth2_provider"] == "google"
            assert normalized["oauth2_id"] == "123456789"
            assert normalized["is_verified"] is True
            
            self.log_test("Google Data Normalization", True, "Data normalized correctly")
        except Exception as e:
            self.log_test("Google Data Normalization", False, f"Error: {e}")
        
        # Test GitHub user data normalization
        try:
            github_data = {
                "id": 123456789,
                "email": "test@example.com",
                "name": "Test User",
                "login": "testuser"
            }
            
            normalized = normalize_oauth2_user_data("github", github_data)
            
            assert normalized["email"] == "test@example.com"
            assert normalized["full_name"] == "Test User"
            assert normalized["oauth2_provider"] == "github"
            assert normalized["oauth2_id"] == "123456789"
            assert normalized["is_verified"] is True
            
            self.log_test("GitHub Data Normalization", True, "Data normalized correctly")
        except Exception as e:
            self.log_test("GitHub Data Normalization", False, f"Error: {e}")
    
    def test_provider_factory(self):
        """Test OAuth2 provider factory"""
        print("\n=== Testing Provider Factory ===")
        
        # Test with mock configuration
        try:
            with patch.object(settings, 'GOOGLE_CLIENT_ID', 'test_google_id'), \
                 patch.object(settings, 'GOOGLE_CLIENT_SECRET', 'test_google_secret'):
                
                provider = get_oauth2_provider("google")
                
                assert provider is not None
                assert isinstance(provider, GoogleOAuth2Provider)
                assert provider.client_id == "test_google_id"
                
                self.log_test("Google Provider Factory", True, "Provider created via factory")
            
            with patch.object(settings, 'GITHUB_CLIENT_ID', 'test_github_id'), \
                 patch.object(settings, 'GITHUB_CLIENT_SECRET', 'test_github_secret'):
                
                provider = get_oauth2_provider("github")
                
                assert provider is not None
                assert isinstance(provider, GitHubOAuth2Provider)
                assert provider.client_id == "test_github_id"
                
                self.log_test("GitHub Provider Factory", True, "Provider created via factory")
                
        except Exception as e:
            self.log_test("Provider Factory", False, f"Error: {e}")
        
        # Test unknown provider
        try:
            provider = get_oauth2_provider("unknown")
            assert provider is None
            self.log_test("Unknown Provider", True, "Unknown provider handled correctly")
        except Exception as e:
            self.log_test("Unknown Provider", False, f"Error: {e}")
    
    def test_oauth2_manager(self):
        """Test OAuth2 provider manager"""
        print("\n=== Testing OAuth2 Manager ===")
        
        try:
            # Test with disabled OAuth2
            with patch.object(settings, 'OAUTH2_ENABLED', False):
                manager = oauth2_manager.__class__()
                
                assert not manager.is_enabled()
                assert len(manager.list_enabled_providers()) == 0
                
                self.log_test("Disabled OAuth2", True, "OAuth2 correctly disabled")
            
            # Test with enabled OAuth2
            with patch.object(settings, 'OAUTH2_ENABLED', True), \
                 patch.object(settings, 'GOOGLE_CLIENT_ID', 'test_id'), \
                 patch.object(settings, 'GOOGLE_CLIENT_SECRET', 'test_secret'):
                
                manager = oauth2_manager.__class__()
                
                assert manager.is_enabled()
                providers = manager.list_enabled_providers()
                assert "google" in providers
                
                self.log_test("Enabled OAuth2", True, f"Providers: {providers}")
                
        except Exception as e:
            self.log_test("OAuth2 Manager", False, f"Error: {e}")
    
    async def test_error_handling(self):
        """Test OAuth2 error handling"""
        print("\n=== Testing Error Handling ===")
        
        try:
            # Test invalid state validation
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None  # No state found
            mock_session_store = AsyncMock()
            mock_session_store.redis = mock_redis
            
            with patch('app.services.session_store.get_session_store', return_value=mock_session_store):
                is_valid = await OAuth2StateManager.validate_state("invalid_state", "google")
                
                assert is_valid is False
                self.log_test("Invalid State Handling", True, "Invalid state rejected")
            
            # Test provider mismatch
            mock_redis.get.return_value = b"github:anonymous"  # Different provider
            
            with patch('app.services.session_store.get_session_store', return_value=mock_session_store):
                is_valid = await OAuth2StateManager.validate_state("test_state", "google")
                
                assert is_valid is False
                self.log_test("Provider Mismatch", True, "Provider mismatch detected")
            
        except Exception as e:
            self.log_test("Error Handling", False, f"Error: {e}")
    
    def test_configuration_validation(self):
        """Test OAuth2 configuration validation"""
        print("\n=== Testing Configuration Validation ===")
        
        try:
            # Test missing configuration
            with patch.object(settings, 'GOOGLE_CLIENT_ID', None):
                provider = get_oauth2_provider("google")
                assert provider is None
                
                self.log_test("Missing Config", True, "Missing configuration handled")
            
            # Test partial configuration
            with patch.object(settings, 'GOOGLE_CLIENT_ID', 'test_id'), \
                 patch.object(settings, 'GOOGLE_CLIENT_SECRET', None):
                
                provider = get_oauth2_provider("google")
                assert provider is None
                
                self.log_test("Partial Config", True, "Partial configuration handled")
                
        except Exception as e:
            self.log_test("Configuration Validation", False, f"Error: {e}")
    
    async def run_all_tests(self):
        """Run all OAuth2 integration tests"""
        print("🔐 OAuth2 Integration Test Suite")
        print("=" * 50)
        
        # Run tests
        self.test_provider_initialization()
        self.test_authorization_urls()
        await self.test_state_management()
        self.test_user_data_normalization()
        self.test_provider_factory()
        self.test_oauth2_manager()
        await self.test_error_handling()
        self.test_configuration_validation()
        
        # Summary
        print("\n" + "=" * 50)
        print("📊 Test Summary:")
        print(f"✅ Passed: {self.passed_tests}")
        print(f"❌ Failed: {self.failed_tests}")
        print(f"📈 Success Rate: {(self.passed_tests / (self.passed_tests + self.failed_tests) * 100):.1f}%")
        
        if self.failed_tests == 0:
            print("\n🎉 All OAuth2 integration tests passed!")
            return True
        else:
            print(f"\n⚠️  {self.failed_tests} test(s) failed. Please review the errors above.")
            return False


async def main():
    """Main test runner"""
    tester = OAuth2IntegrationTester()
    success = await tester.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())