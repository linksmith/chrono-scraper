#!/usr/bin/env python3
"""
Comprehensive email functionality test using Mailpit
Tests password reset and signup verification emails
"""
import asyncio
import httpx
import random
import string
from datetime import datetime
from typing import Dict, Any, Optional
import json
import time

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
MAILPIT_API_URL = "http://mailpit:8025/api/v1"
TEST_USER_PREFIX = f"test_email_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


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


class EmailFunctionalityTest:
    """Comprehensive email functionality test"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(base_url=API_BASE_URL)
        self.mailpit_client = httpx.AsyncClient(base_url=MAILPIT_API_URL)
        self.test_user = {
            "email": f"{TEST_USER_PREFIX}@example.com",
            "password": "TestPassword123!",
            "full_name": "Test Email User",
            "professional_title": "Email Test Analyst",
            "organization_website": "https://emailtest.org",
            "linkedin_profile": "https://linkedin.com/in/emailtestuser",
            "academic_affiliation": "Email Test University",
            "research_interests": "Email testing and verification",
            "research_purpose": "Testing email functionality of the Chrono Scraper platform"
        }
        self.auth_token: Optional[str] = None
        self.user_id: Optional[int] = None
    
    async def close(self):
        """Close HTTP clients"""
        await self.client.aclose()
        await self.mailpit_client.aclose()
    
    async def clear_mailpit_inbox(self) -> bool:
        """Clear all emails from Mailpit inbox"""
        print_test("Clear Mailpit Inbox")
        
        try:
            # Delete all messages
            response = await self.mailpit_client.delete("/messages")
            
            if response.status_code in [200, 204]:
                print_success("Mailpit inbox cleared")
                return True
            else:
                print_error(f"Failed to clear Mailpit inbox: {response.status_code}")
                return False
                
        except Exception as e:
            print_error(f"Error clearing Mailpit inbox: {str(e)}")
            return False
    
    async def get_mailpit_messages(self) -> list:
        """Get all messages from Mailpit"""
        try:
            response = await self.mailpit_client.get("/messages")
            
            if response.status_code == 200:
                data = response.json()
                return data.get("messages", [])
            else:
                print_error(f"Failed to get Mailpit messages: {response.status_code}")
                return []
                
        except Exception as e:
            print_error(f"Error getting Mailpit messages: {str(e)}")
            return []
    
    async def get_latest_email_to(self, recipient_email: str) -> Optional[Dict]:
        """Get the latest email sent to a specific recipient"""
        messages = await self.get_mailpit_messages()
        
        for message in messages:
            if any(to_addr.get("Address") == recipient_email for to_addr in message.get("To", [])):
                return message
        
        return None
    
    async def get_email_content(self, message_id: str) -> Optional[Dict]:
        """Get detailed email content by message ID"""
        try:
            response = await self.mailpit_client.get(f"/message/{message_id}")
            
            if response.status_code == 200:
                return response.json()
            else:
                print_error(f"Failed to get email content: {response.status_code}")
                return None
                
        except Exception as e:
            print_error(f"Error getting email content: {str(e)}")
            return None
    
    async def test_1_user_registration(self) -> bool:
        """Test user registration (should trigger verification email)"""
        print_test("User Registration (Verification Email)")
        
        try:
            # Clear inbox first
            await self.clear_mailpit_inbox()
            
            # Register new user
            response = await self.client.post(
                "/auth/register",
                json=self.test_user
            )
            
            if response.status_code == 200:
                data = response.json()
                self.user_id = data.get('id')
                print_success(f"User registered successfully: {self.test_user['email']}")
                print_info(f"User ID: {data.get('id')}")
                print_info(f"Verification status: {data.get('is_verified', False)}")
                
                # Wait a moment for email to be sent
                await asyncio.sleep(2)
                
                # Check for verification email
                latest_email = await self.get_latest_email_to(self.test_user["email"])
                
                if latest_email:
                    print_success("Verification email found in Mailpit!")
                    print_info(f"Email subject: {latest_email.get('Subject')}")
                    print_info(f"From: {latest_email.get('From', {}).get('Address')}")
                    print_info(f"Sent at: {latest_email.get('Date')}")
                    
                    # Get full email content
                    email_content = await self.get_email_content(latest_email.get('ID'))
                    if email_content:
                        text_body = email_content.get('Text', '')
                        html_body = email_content.get('HTML', '')
                        
                        print_info("Email content preview:")
                        if text_body:
                            # Show first 200 characters of text
                            print_info(f"Text: {text_body[:200]}...")
                        if html_body:
                            print_info(f"HTML body present: {len(html_body)} characters")
                        
                        # Look for verification link
                        if "verify-email" in text_body or "verify-email" in html_body:
                            print_success("Verification link found in email content")
                        else:
                            print_error("No verification link found in email")
                    
                    return True
                else:
                    print_error("No verification email found in Mailpit")
                    return False
                    
            else:
                print_error(f"Registration failed: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Registration error: {str(e)}")
            return False
    
    async def test_2_resend_verification_email(self) -> bool:
        """Test resending verification email"""
        print_test("Resend Verification Email")
        
        try:
            # Clear inbox to isolate new email
            await self.clear_mailpit_inbox()
            
            # Try to resend verification email
            response = await self.client.post(
                "/auth/email/resend",
                json={"email": self.test_user["email"]}
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("Verification email resend requested")
                print_info(f"Message: {data.get('message')}")
                
                # Wait for email
                await asyncio.sleep(2)
                
                # Check for new verification email
                latest_email = await self.get_latest_email_to(self.test_user["email"])
                
                if latest_email:
                    print_success("Resent verification email found in Mailpit!")
                    print_info(f"Email subject: {latest_email.get('Subject')}")
                    return True
                else:
                    print_error("No resent verification email found")
                    return False
                    
            else:
                print_error(f"Failed to resend verification: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Resend verification error: {str(e)}")
            return False
    
    async def test_3_login_unverified_user(self) -> bool:
        """Test that unverified users can login but have limited access"""
        print_test("Login as Unverified User")
        
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
                print_success("Login successful for unverified user")
                print_info(f"Access token obtained: {self.auth_token[:20]}...")
                
                # Try to access a protected endpoint that requires verification
                profile_response = await self.client.get(
                    "/profile/me",
                    headers={"Authorization": f"Bearer {self.auth_token}"}
                )
                
                if profile_response.status_code == 200:
                    profile_data = profile_response.json()
                    print_success("Profile access granted (basic access)")
                    print_info(f"Verification status: {profile_data.get('is_verified', False)}")
                    
                    # User should NOT be verified yet
                    if not profile_data.get('is_verified', False):
                        print_success("User correctly shows as unverified")
                        return True
                    else:
                        print_error("User incorrectly shows as verified")
                        return False
                else:
                    print_error(f"Profile access denied: {profile_response.status_code}")
                    return False
                    
            else:
                print_error(f"Login failed: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Login error: {str(e)}")
            return False
    
    async def test_4_request_password_reset(self) -> bool:
        """Test password reset email functionality"""
        print_test("Password Reset Email")
        
        try:
            # Clear inbox to isolate password reset email
            await self.clear_mailpit_inbox()
            
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
                
                # Wait for email
                await asyncio.sleep(2)
                
                # Check for password reset email
                latest_email = await self.get_latest_email_to(self.test_user["email"])
                
                if latest_email:
                    print_success("Password reset email found in Mailpit!")
                    print_info(f"Email subject: {latest_email.get('Subject')}")
                    print_info(f"From: {latest_email.get('From', {}).get('Address')}")
                    
                    # Get full email content
                    email_content = await self.get_email_content(latest_email.get('ID'))
                    if email_content:
                        text_body = email_content.get('Text', '')
                        html_body = email_content.get('HTML', '')
                        
                        print_info("Password reset email content preview:")
                        if text_body:
                            print_info(f"Text: {text_body[:300]}...")
                        
                        # Look for reset link or token
                        if "reset" in text_body.lower() or "reset" in html_body.lower():
                            print_success("Password reset content found in email")
                        else:
                            print_error("No password reset content found in email")
                    
                    return True
                else:
                    print_error("No password reset email found in Mailpit")
                    return False
                    
            else:
                print_error(f"Failed to request password reset: {response.status_code}")
                print_error(f"Response: {response.text}")
                return False
                
        except Exception as e:
            print_error(f"Password reset error: {str(e)}")
            return False
    
    async def test_5_password_reset_nonexistent_email(self) -> bool:
        """Test password reset for non-existent email (should not reveal info)"""
        print_test("Password Reset - Non-existent Email")
        
        try:
            # Clear inbox
            await self.clear_mailpit_inbox()
            
            # Request password reset for non-existent email
            fake_email = f"nonexistent_{generate_random_string()}@example.com"
            reset_data = {
                "email": fake_email
            }
            
            response = await self.client.post(
                "/profile/request-password-reset",
                json=reset_data
            )
            
            if response.status_code == 200:
                data = response.json()
                print_success("Password reset request handled securely")
                print_info(f"Message: {data.get('message')}")
                
                # Wait a moment
                await asyncio.sleep(2)
                
                # Should NOT receive any email for non-existent user
                latest_email = await self.get_latest_email_to(fake_email)
                
                if latest_email:
                    print_error("Security issue: Email sent to non-existent address")
                    return False
                else:
                    print_success("Security correct: No email sent to non-existent address")
                    return True
                    
            else:
                print_error(f"Unexpected response: {response.status_code}")
                return False
                
        except Exception as e:
            print_error(f"Password reset security test error: {str(e)}")
            return False
    
    async def test_6_mailpit_interface_check(self) -> bool:
        """Test accessing Mailpit web interface"""
        print_test("Mailpit Web Interface Accessibility")
        
        try:
            # Check if Mailpit web interface is accessible
            web_response = await self.mailpit_client.get("/info")
            
            if web_response.status_code == 200:
                info = web_response.json()
                print_success("Mailpit API accessible")
                print_info(f"Version: {info.get('version', 'unknown')}")
                
                # Get message count
                messages = await self.get_mailpit_messages()
                print_info(f"Total messages in inbox: {len(messages)}")
                
                print_info("🌐 Mailpit web interface should be accessible at: http://localhost:8025")
                print_info("📧 You can view all test emails in the web interface")
                
                return True
            else:
                print_error(f"Mailpit API not accessible: {web_response.status_code}")
                return False
                
        except Exception as e:
            print_error(f"Mailpit interface check error: {str(e)}")
            return False
    
    async def test_7_email_workflow_verification(self) -> bool:
        """Test complete email verification workflow"""
        print_test("Complete Email Verification Workflow")
        
        try:
            # Get current user status
            if not self.auth_token:
                print_error("No auth token available")
                return False
            
            profile_response = await self.client.get(
                "/profile/me",
                headers={"Authorization": f"Bearer {self.auth_token}"}
            )
            
            if profile_response.status_code == 200:
                profile_data = profile_response.json()
                print_info(f"Current verification status: {profile_data.get('is_verified', False)}")
                print_info(f"Current approval status: {profile_data.get('approval_status', 'unknown')}")
                
                # User should be unverified and pending
                if not profile_data.get('is_verified', False):
                    print_success("User correctly unverified - email verification required")
                    
                    # Check approval status
                    approval_status = profile_data.get('approval_status', 'pending')
                    if approval_status == 'pending':
                        print_success("User approval correctly pending until email verification")
                        return True
                    else:
                        print_error(f"Unexpected approval status: {approval_status}")
                        return False
                else:
                    print_error("User incorrectly shows as verified")
                    return False
            else:
                print_error(f"Failed to get profile: {profile_response.status_code}")
                return False
                
        except Exception as e:
            print_error(f"Email workflow verification error: {str(e)}")
            return False
    
    async def run_all_tests(self):
        """Run all email functionality tests"""
        print_section("COMPREHENSIVE EMAIL FUNCTIONALITY TEST SUITE")
        print_info(f"Test user: {self.test_user['email']}")
        print_info(f"Timestamp: {datetime.now().isoformat()}")
        print_info(f"API Base URL: {API_BASE_URL}")
        print_info(f"Mailpit API URL: {MAILPIT_API_URL}")
        
        tests = [
            self.test_1_user_registration,
            self.test_2_resend_verification_email,
            self.test_3_login_unverified_user,
            self.test_4_request_password_reset,
            self.test_5_password_reset_nonexistent_email,
            self.test_6_mailpit_interface_check,
            self.test_7_email_workflow_verification
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
        print_section("EMAIL TEST SUMMARY")
        
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
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ ALL EMAIL TESTS PASSED!{Colors.RESET}")
            print(f"\n{Colors.CYAN}{Colors.BOLD}📧 Mailpit Interface:{Colors.RESET}")
            print(f"  🌐 Web UI: http://localhost:8025")
            print(f"  📨 All test emails can be viewed in the web interface")
            print(f"  🔍 Check email content, links, and formatting")
        else:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️ SOME EMAIL TESTS FAILED{Colors.RESET}")
        
        return passed == len(results)


async def main():
    """Main test runner"""
    tester = EmailFunctionalityTest()
    
    try:
        success = await tester.run_all_tests()
        return 0 if success else 1
    finally:
        await tester.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)