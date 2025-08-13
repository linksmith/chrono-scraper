#!/usr/bin/env python3
"""
Test script for email functionality
Usage: python test_email.py
"""
import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from app.core.config import settings
from app.core.email_service import email_service
from app.core.email import (
    send_email,
    generate_password_reset_email,
    generate_email_verification_email,
    generate_approval_notification_email
)


async def test_email_service():
    """Test the email service functionality"""
    print(f"Testing email service in {settings.ENVIRONMENT} environment")
    print("-" * 50)
    
    # Test recipient email
    test_email = "test@example.com"
    
    # Test 1: Simple email
    print("Test 1: Sending simple test email...")
    success = await send_email(
        email_to=test_email,
        subject="Test Email from Chrono Scraper",
        html_content="<h1>Test Email</h1><p>This is a test email from Chrono Scraper.</p>",
        text_content="Test Email\n\nThis is a test email from Chrono Scraper."
    )
    print(f"✓ Simple email sent: {success}")
    
    # Test 2: Password reset email
    print("\nTest 2: Sending password reset email...")
    subject, html_content = generate_password_reset_email(test_email, "test-token-123")
    success = await send_email(
        email_to=test_email,
        subject=subject,
        html_content=html_content
    )
    print(f"✓ Password reset email sent: {success}")
    
    # Test 3: Email verification
    print("\nTest 3: Sending email verification...")
    subject, html_content = generate_email_verification_email(test_email, "verify-token-456")
    success = await send_email(
        email_to=test_email,
        subject=subject,
        html_content=html_content
    )
    print(f"✓ Email verification sent: {success}")
    
    # Test 4: Approval notification (approved)
    print("\nTest 4: Sending approval notification (approved)...")
    subject, html_content = generate_approval_notification_email(test_email, approved=True)
    success = await send_email(
        email_to=test_email,
        subject=subject,
        html_content=html_content
    )
    print(f"✓ Approval notification (approved) sent: {success}")
    
    # Test 5: Approval notification (rejected)
    print("\nTest 5: Sending approval notification (rejected)...")
    subject, html_content = generate_approval_notification_email(test_email, approved=False)
    success = await send_email(
        email_to=test_email,
        subject=subject,
        html_content=html_content
    )
    print(f"✓ Approval notification (rejected) sent: {success}")
    
    # Test 6: Bulk email (if multiple recipients needed)
    print("\nTest 6: Testing bulk email...")
    recipients = ["test1@example.com", "test2@example.com", "test3@example.com"]
    results = await email_service.send_bulk_emails(
        recipients=recipients,
        subject="Bulk Test Email",
        html_content="<h1>Bulk Email Test</h1><p>This is a bulk email test.</p>",
        text_content="Bulk Email Test\n\nThis is a bulk email test."
    )
    print(f"✓ Bulk email results: {results}")
    
    # Test 7: Email validation (production only)
    if settings.ENVIRONMENT == "production":
        print("\nTest 7: Testing email validation...")
        validation_result = await email_service.verify_email_address(test_email)
        print(f"✓ Email validation result: {validation_result}")
    
    print("\n" + "=" * 50)
    print("Email testing completed!")
    
    if settings.ENVIRONMENT == "development":
        print("\n📧 Check Mailpit at http://localhost:8025 to see the test emails")
    else:
        print("\n📧 Check your Mailgun dashboard or email inbox for the test emails")


if __name__ == "__main__":
    asyncio.run(test_email_service())