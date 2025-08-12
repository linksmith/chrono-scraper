"""
Email utilities for password reset and verification
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_email(
    email_to: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None
) -> bool:
    """
    Send email using SMTP
    Returns True if successful, False otherwise
    """
    if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD]):
        logger.warning("SMTP settings not configured, skipping email send")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.EMAILS_FROM_EMAIL or settings.SMTP_USER
        msg["To"] = email_to
        
        # Add text content if provided
        if text_content:
            text_part = MIMEText(text_content, "plain")
            msg.attach(text_part)
        
        # Add HTML content
        html_part = MIMEText(html_content, "html")
        msg.attach(html_part)
        
        # Send email
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_TLS:
                server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Email sent successfully to {email_to}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {email_to}: {str(e)}")
        return False


def generate_password_reset_email(email: str, token: str) -> tuple[str, str]:
    """
    Generate password reset email content
    Returns (subject, html_content)
    """
    subject = f"{settings.PROJECT_NAME} - Password Reset"
    
    # In production, this would be the frontend URL
    reset_url = f"http://localhost:5173/reset-password?token={token}"
    
    html_content = f"""
    <html>
        <body>
            <h2>Password Reset Request</h2>
            <p>Hello,</p>
            <p>You requested a password reset for your {settings.PROJECT_NAME} account.</p>
            <p>Click the link below to reset your password:</p>
            <p><a href="{reset_url}">Reset Password</a></p>
            <p>This link will expire in {settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS} hours.</p>
            <p>If you did not request this reset, please ignore this email.</p>
            <p>Best regards,<br>The {settings.PROJECT_NAME} Team</p>
        </body>
    </html>
    """
    
    return subject, html_content


def generate_email_verification_email(email: str, token: str) -> tuple[str, str]:
    """
    Generate email verification email content
    Returns (subject, html_content)
    """
    subject = f"{settings.PROJECT_NAME} - Email Verification"
    
    # In production, this would be the frontend URL
    verify_url = f"http://localhost:5173/verify-email?token={token}"
    
    html_content = f"""
    <html>
        <body>
            <h2>Email Verification</h2>
            <p>Hello,</p>
            <p>Thank you for registering with {settings.PROJECT_NAME}.</p>
            <p>Please click the link below to verify your email address:</p>
            <p><a href="{verify_url}">Verify Email</a></p>
            <p>If you did not create this account, please ignore this email.</p>
            <p>Best regards,<br>The {settings.PROJECT_NAME} Team</p>
        </body>
    </html>
    """
    
    return subject, html_content


def generate_approval_notification_email(email: str, approved: bool) -> tuple[str, str]:
    """
    Generate account approval notification email
    Returns (subject, html_content)
    """
    if approved:
        subject = f"{settings.PROJECT_NAME} - Account Approved"
        html_content = f"""
        <html>
            <body>
                <h2>Account Approved</h2>
                <p>Hello,</p>
                <p>Your {settings.PROJECT_NAME} account has been approved!</p>
                <p>You can now log in and start using the platform.</p>
                <p><a href="http://localhost:5173/login">Login Now</a></p>
                <p>Best regards,<br>The {settings.PROJECT_NAME} Team</p>
            </body>
        </html>
        """
    else:
        subject = f"{settings.PROJECT_NAME} - Account Application Update"
        html_content = f"""
        <html>
            <body>
                <h2>Account Application Update</h2>
                <p>Hello,</p>
                <p>Thank you for your interest in {settings.PROJECT_NAME}.</p>
                <p>Unfortunately, we are unable to approve your account at this time.</p>
                <p>If you have questions, please contact our support team.</p>
                <p>Best regards,<br>The {settings.PROJECT_NAME} Team</p>
            </body>
        </html>
        """
    
    return subject, html_content