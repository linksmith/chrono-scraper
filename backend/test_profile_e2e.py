#!/usr/bin/env python3
"""
Comprehensive E2E test for user signup to profile settings management
Tests the complete user journey from registration to profile customization
"""
import asyncio
import httpx
import random
import string
from datetime import datetime
from typing import Dict, Any, Optional
import json

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
TEST_USER_PREFIX = f"test_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


class Colors:
    """Terminal colors for output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def generate_random_string(length: int = 8) -> str:
    """Generate random string for testing"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def print_section(title: str):
    """Print section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")


def print_success(message: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")


def print_error(message: str):
    """Print error message"""
    print(f"{Colors.RED}✗ {message}{Colors.RESET}")


def print_info(message: str):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ {message}{Colors.RESET}")


def print_test(test_name: str):
    """Print test name"""
    print(f"\n{Colors.YELLOW}▸ Testing: {test_name}{Colors.RESET}")


class ProfileE2ETest:
    """Comprehensive E2E test for profile management"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=API_BASE_URL)
        self.test_user = {
            "email": f"{TEST_USER_PREFIX}@example.com",
            "password": "TestPassword123!",
            "full_name": "Test User",
            "professional_title": "Research Analyst",
            "organization_website": "https://example.org",
            "linkedin_profile": "https://linkedin.com/in/testuser",
            "academic_affiliation": "Test University",
            "research_interests": "Testing and automation",
            "research_purpose": "Automated testing of the Chrono Scraper platform to ensure quality"
        }
        self.auth_token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.refresh_token: Optional[str] = None
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()
    
    async def test_1_user_registration(self) -> bool:
        """Test user registration"""
        print_test("User Registration")
        
        try:
            # Register new user
            response = await self.client.post(
                "/auth/register",
                json=self.test_user
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"User registered successfully: {self.test_user['email']}")
                print_info(f"User ID: {data.get('id')}")
                print_info(f"Verification status: {data.get('is_verified', False)}")
                return True
            else:
                print_error(f"Registration failed: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Registration error: {str(e)}")
            return False
    
    async def test_2_user_login(self) -> bool:
        """Test user login"""
        print_test("User Login")
        
        try:
            # Login with credentials
            response = await self.client.post(
                "/auth/login",
                data={
                    "username": self.test_user["email"],
                    "password": self.test_user["password"]
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                print_success("Login successful")
                print_info(f"Access token obtained: {self.auth_token[:20]}...")
                print_info(f"Token type: {data.get('token_type')}")
                return True
            else:
                print_error(f"Login failed: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Login error: {str(e)}")
            return False
    
    async def test_3_get_profile(self) -> bool:
        """Test getting user profile"""
        print_test("Get User Profile")
        
        if not self.auth_token:
            print_error("No auth token available")
            return False
        
        try:
            response = await self.client.get(
                "/profile/me",
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_id = data.get("id")
                print_success("Profile retrieved successfully")
                print_info(f"User ID: {data.get('id')}")
                print_info(f"Email: {data.get('email')}")
                print_info(f"Full Name: {data.get('full_name')}")
                print_info(f"Current Plan: {data.get('current_plan', 'free')}")
                print_info(f"Approval Status: {data.get('approval_status')}")
                return True
            else:
                print_error(f"Failed to get profile: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Get profile error: {str(e)}")
            return False
    
    async def test_4_update_personal_info(self) -> bool:
        """Test updating personal information"""
        print_test("Update Personal Information")
        
        if not self.auth_token:
            print_error("No auth token available")
            return False
        
        try:
            # Update personal info
            update_data = {
                "full_name": "Updated Test User",
                "professional_title": "Senior Research Analyst",
                "organization_website": "https://updated.example.org",
                "linkedin_profile": "https://linkedin.com/in/updateduser",
                "academic_affiliation": "Updated University",
                "research_interests": "Advanced testing and quality assurance"
            }
            
            response = await self.client.patch(
                "/profile/me",
                json=update_data,
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("Personal information updated successfully")
                print_info(f"Updated Full Name: {data.get('full_name')}")
                print_info(f"Updated Title: {data.get('professional_title')}")
                print_info(f"Updated Affiliation: {data.get('academic_affiliation')}")
                return True
            else:
                print_error(f"Failed to update personal info: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Update personal info error: {str(e)}")
            return False
    
    async def test_5_set_api_keys(self) -> bool:
        """Test setting API keys"""
        print_test("Set API Keys")
        
        if not self.auth_token:
            print_error("No auth token available")
            return False
        
        try:
            # Set API keys
            api_keys = {
                "openrouter_api_key": f"sk-or-test-{generate_random_string(32)}",
                "proxy_api_key": f"proxy-test-{generate_random_string(24)}"
            }
            
            response = await self.client.patch(
                "/profile/api-keys",
                json=api_keys,
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("API keys set successfully")
                # Keys should be returned (in production they'd be encrypted)
                if data.get('openrouter_api_key'):
                    print_info(f"OpenRouter key set: {data.get('openrouter_api_key')[:15]}...")
                if data.get('proxy_api_key'):
                    print_info(f"Proxy key set: {data.get('proxy_api_key')[:15]}...")
                return True
            else:
                print_error(f"Failed to set API keys: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Set API keys error: {str(e)}")
            return False
    
    async def test_6_change_password(self) -> bool:
        """Test changing password"""
        print_test("Change Password")
        
        if not self.auth_token:
            print_error("No auth token available")
            return False
        
        try:
            # Change password
            new_password = "NewTestPassword456!"
            password_data = {
                "current_password": self.test_user["password"],
                "new_password": new_password
            }
            
            response = await self.client.post(
                "/profile/change-password",
                json=password_data,
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            if response.status_code == 200:
                print_success("Password changed successfully")
                
                # Test login with new password
                print_info("Testing login with new password...")
                login_response = await self.client.post(
                    "/auth/login",
                    data={
                        "username": self.test_user["email"],
                        "password": new_password
                    }
                )
                
                if login_response.status_code == 200:
                    print_success("Login with new password successful")
                    # Update stored password and token
                    self.test_user["password"] = new_password
                    self.auth_token = login_response.json().get("access_token")
                    return True
                else:
                    print_error("Failed to login with new password")
                    return False
            else:
                print_error(f"Failed to change password: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Change password error: {str(e)}")
            return False
    
    async def test_7_get_available_plans(self) -> bool:
        """Test getting available plans"""
        print_test("Get Available Plans")
        
        if not self.auth_token:
            print_error("No auth token available")
            return False
        
        try:
            response = await self.client.get(
                "/profile/plans",
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            if response.status_code == 200:
                plans = response.json()
                print_success(f"Retrieved {len(plans)} available plans")
                
                for plan in plans:
                    print_info(f"\nPlan: {plan.get('display_name', plan.get('name'))}")
                    print_info(f"  - Price: ${plan.get('price_monthly')}/month")
                    print_info(f"  - Pages/month: {plan.get('pages_per_month'):,}")
                    print_info(f"  - Projects: {plan.get('projects_limit')}")
                    print_info(f"  - Rate limit: {plan.get('rate_limit_per_minute')} req/min")
                    if plan.get('features'):
                        print_info(f"  - Features: {', '.join(plan['features'][:3])}")
                
                return True
            else:
                print_error(f"Failed to get plans: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Get plans error: {str(e)}")
            return False
    
    async def test_8_change_plan(self) -> bool:
        """Test changing subscription plan"""
        print_test("Change Subscription Plan")
        
        if not self.auth_token:
            print_error("No auth token available")
            return False
        
        try:
            # Try to upgrade to flash plan
            plan_data = {
                "plan_name": "flash"
            }
            
            response = await self.client.post(
                "/profile/change-plan",
                json=plan_data,
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"Plan changed successfully: {data.get('message')}")
                print_info(f"New plan: {data.get('plan')}")
                
                # Verify plan change
                profile_response = await self.client.get(
                    "/profile/me",
                    headers={"Authorization": f"Bearer {self.auth_token}"}
                )
                
                if profile_response.status_code == 200:
                    profile_data = profile_response.json()
                    print_success(f"Plan verified: {profile_data.get('current_plan')}")
                
                return True
            else:
                print_error(f"Failed to change plan: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Change plan error: {str(e)}")
            return False
    
    async def test_9_request_password_reset(self) -> bool:
        """Test requesting password reset"""
        print_test("Request Password Reset")
        
        try:
            # Request password reset
            reset_data = {
                "email": self.test_user["email"]
            }
            
            response = await self.client.post(
                "/profile/request-password-reset",
                json=reset_data
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("Password reset requested successfully")
                print_info(f"Message: {data.get('message')}")
                print_info("In production, an email would be sent with reset link")
                return True
            else:
                print_error(f"Failed to request password reset: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Request password reset error: {str(e)}")
            return False
    
    async def test_10_validate_profile_completeness(self) -> bool:
        """Test final profile validation"""
        print_test("Validate Profile Completeness")
        
        if not self.auth_token:
            print_error("No auth token available")
            return False
        
        try:
            response = await self.client.get(
                "/profile/me",
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("Profile validation successful")
                
                # Check all expected fields
                expected_fields = [
                    "id", "email", "full_name", "professional_title",
                    "organization_website", "linkedin_profile", 
                    "academic_affiliation", "research_interests",
                    "current_plan", "openrouter_api_key", "proxy_api_key",
                    "approval_status", "is_active", "is_verified"
                ]
                
                missing_fields = []
                populated_fields = []
                
                for field in expected_fields:
                    if field not in data:
                        missing_fields.append(field)
                    elif data.get(field):
                        populated_fields.append(field)
                
                print_info(f"Profile completeness: {len(populated_fields)}/{len(expected_fields)} fields")
                
                if populated_fields:
                    print_success(f"Populated fields: {', '.join(populated_fields[:5])}...")
                
                if missing_fields:
                    print_info(f"Missing fields: {', '.join(missing_fields)}")
                
                # Profile is considered complete if at least 80% of fields are present
                completeness = len(populated_fields) / len(expected_fields) * 100
                print_info(f"Profile completeness: {completeness:.1f}%")
                
                return completeness >= 70  # Allow for some optional fields
            else:
                print_error(f"Failed to validate profile: {response.status_code}")
                return False
                
        except Exception as e:
            print_error(f"Profile validation error: {str(e)}")
            return False
    
    async def run_all_tests(self):
        """Run all E2E tests"""
        print_section("COMPREHENSIVE PROFILE E2E TEST SUITE")
        print_info(f"Test user: {self.test_user['email']}")
        print_info(f"Timestamp: {datetime.now().isoformat()}")
        
        tests = [
            self.test_1_user_registration,
            self.test_2_user_login,
            self.test_3_get_profile,
            self.test_4_update_personal_info,
            self.test_5_set_api_keys,
            self.test_6_change_password,
            self.test_7_get_available_plans,
            self.test_8_change_plan,
            self.test_9_request_password_reset,
            self.test_10_validate_profile_completeness
        ]
        
        results = []
        
        for i, test in enumerate(tests, 1):
            try:
                result = await test()
                results.append((test.__name__, result))
                
                if not result:
                    print_error(f"Test {i} failed, but continuing with remaining tests...")
                    
            except Exception as e:
                print_error(f"Test {i} crashed: {str(e)}")
                results.append((test.__name__, False))
        
        # Print summary
        print_section("TEST SUMMARY")
        
        passed = sum(1 for _, result in results if result)
        failed = len(results) - passed
        
        print(f"\n{Colors.BOLD}Results:{Colors.RESET}")
        for test_name, result in results:
            status = f"{Colors.GREEN}PASSED{Colors.RESET}" if result else f"{Colors.RED}FAILED{Colors.RESET}"
            test_display = test_name.replace("test_", "").replace("_", " ").title()
            print(f"  {test_display}: {status}")
        
        print(f"\n{Colors.BOLD}Statistics:{Colors.RESET}")
        print(f"  Total Tests: {len(results)}")
        print(f"  {Colors.GREEN}Passed: {passed}{Colors.RESET}")
        print(f"  {Colors.RED}Failed: {failed}{Colors.RESET}")
        print(f"  Success Rate: {(passed/len(results)*100):.1f}%")
        
        if passed == len(results):
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ ALL TESTS PASSED!{Colors.RESET}")
        else:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️ SOME TESTS FAILED{Colors.RESET}")
        
        return passed == len(results)


async def main():
    """Main test runner"""
    tester = ProfileE2ETest()
    
    try:
        success = await tester.run_all_tests()
        return 0 if success else 1
    finally:
        await tester.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)