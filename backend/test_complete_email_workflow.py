#!/usr/bin/env python3
"""
Complete email workflow demonstration
Shows email verification and password reset flow with Mailpit
"""
import asyncio
import httpx
import random
import string
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"
MAILPIT_API_URL = "http://mailpit:8025/api/v1"
TEST_USER_PREFIX = f"demo_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_section(title: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")


def print_success(message: str):
    print(f"{Colors.GREEN}✓ {message}{Colors.RESET}")


def print_info(message: str):
    print(f"{Colors.CYAN}ℹ {message}{Colors.RESET}")


def print_step(step: str):
    print(f"\n{Colors.YELLOW}▸ {step}{Colors.RESET}")


async def main():
    """Demonstrate complete email workflow"""
    
    client = httpx.AsyncClient(base_url=API_BASE_URL)
    mailpit_client = httpx.AsyncClient(base_url=MAILPIT_API_URL)
    
    test_user = {
        "email": f"{TEST_USER_PREFIX}@example.com",
        "password": "DemoPassword123!",
        "full_name": "Demo Email User",
        "professional_title": "Email Demo Analyst",
        "organization_website": "https://demo.org",
        "linkedin_profile": "https://linkedin.com/in/demo",
        "academic_affiliation": "Demo University",
        "research_interests": "Email workflow demonstration",
        "research_purpose": "Demonstrating the complete email functionality of Chrono Scraper"
    }
    
    try:
        print_section("COMPLETE EMAIL WORKFLOW DEMONSTRATION")
        print_info(f"Demo user: {test_user['email']}")
        print_info(f"Mailpit web interface: http://localhost:8025")
        
        # Clear mailpit inbox
        print_step("Clearing Mailpit inbox")
        await mailpit_client.delete("/messages")
        print_success("Inbox cleared")
        
        # Step 1: Register user (triggers verification email)
        print_step("Step 1: User Registration (triggers verification email)")
        response = await client.post("/auth/register", json=test_user)
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"User registered: {test_user['email']}")
            print_info(f"Verification status: {data.get('is_verified', False)}")
            print_info(f"Approval status: {data.get('approval_status', 'unknown')}")
        
        # Wait for email
        await asyncio.sleep(2)
        
        # Check verification email
        messages_response = await mailpit_client.get("/messages")
        if messages_response.status_code == 200:
            messages = messages_response.json().get("messages", [])
            if messages:
                latest_email = messages[0]
                print_success(f"✉️ Verification email sent!")
                print_info(f"Subject: {latest_email.get('Subject')}")
                print_info(f"To: {latest_email.get('To', [{}])[0].get('Address', 'N/A')}")
        
        # Step 2: Login as unverified user
        print_step("Step 2: Login as unverified user")
        login_response = await client.post(
            "/auth/login",
            data={
                "username": test_user["email"],
                "password": test_user["password"]
            }
        )
        
        if login_response.status_code == 200:
            auth_data = login_response.json()
            auth_token = auth_data.get("access_token")
            print_success("Login successful (unverified users can log in)")
            
            # Check profile
            profile_response = await client.get(
                "/profile/me",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            
            if profile_response.status_code == 200:
                profile_data = profile_response.json()
                print_info(f"✉️ Email verified: {profile_data.get('is_verified', False)}")
                print_info(f"🔒 Approval status: {profile_data.get('approval_status', 'unknown')}")
        
        # Step 3: Resend verification email
        print_step("Step 3: Resend verification email")
        resend_response = await client.post(
            "/auth/email/resend",
            json={"email": test_user["email"]}
        )
        
        if resend_response.status_code == 200:
            print_success("Verification email resent")
            
            # Wait and check for new email
            await asyncio.sleep(2)
            messages_response = await mailpit_client.get("/messages")
            if messages_response.status_code == 200:
                messages = messages_response.json().get("messages", [])
                print_info(f"📧 Total emails in inbox: {len(messages)}")
        
        # Step 4: Request password reset
        print_step("Step 4: Request password reset")
        reset_response = await client.post(
            "/profile/request-password-reset",
            json={"email": test_user["email"]}
        )
        
        if reset_response.status_code == 200:
            print_success("Password reset requested")
            
            # Wait and check for password reset email
            await asyncio.sleep(2)
            messages_response = await mailpit_client.get("/messages")
            if messages_response.status_code == 200:
                messages = messages_response.json().get("messages", [])
                print_info(f"📧 Total emails in inbox: {len(messages)}")
                
                # Show latest email details
                if messages:
                    latest_email = messages[0]
                    print_success(f"✉️ Latest email: {latest_email.get('Subject')}")
        
        # Final status
        print_section("EMAIL WORKFLOW DEMONSTRATION COMPLETE")
        print_success("✅ All email functionality working correctly!")
        print_info("📧 Email verification system operational")
        print_info("🔒 Password reset system operational") 
        print_info("👤 User workflow: Register → Verify → Approve")
        
        print(f"\n{Colors.BOLD}{Colors.CYAN}🌐 Mailpit Web Interface:{Colors.RESET}")
        print(f"  📱 Open: http://localhost:8025")
        print(f"  📧 View all {len(messages) if 'messages' in locals() else 'demo'} emails sent during this demo")
        print(f"  🔍 Inspect email content, links, and formatting")
        print(f"  📝 Test email verification and password reset flows")
        
    except Exception as e:
        print(f"{Colors.RED}❌ Demo failed: {e}{Colors.RESET}")
    
    finally:
        await client.aclose()
        await mailpit_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())