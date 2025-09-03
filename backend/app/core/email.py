"""
Email utilities for password reset and verification
"""
from typing import Optional
import logging
from app.core.config import settings
from app.core.email_service import email_service

logger = logging.getLogger(__name__)


async def send_email(
    email_to: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None
) -> bool:
    """
    Send email using the configured email service
    Returns True if successful, False otherwise
    """
    return await email_service.send_email(
        email_to=email_to,
        subject=subject,
        html_content=html_content,
        text_content=text_content
    )


def generate_password_reset_email(email: str, token: str) -> tuple[str, str]:
    """
    Generate password reset email content
    Returns (subject, html_content)
    """
    subject = f"{settings.PROJECT_NAME} - Password Reset"
    
    # Use frontend URL based on environment
    if settings.ENVIRONMENT == "production":
        base_url = settings.FRONTEND_URL if hasattr(settings, 'FRONTEND_URL') else "https://chrono-scraper.com"
    else:
        base_url = "http://localhost:5173"
    
    reset_url = f"{base_url}/reset-password?token={token}"
    
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Password Reset Request</h2>
                <p>Hello,</p>
                <p>You requested a password reset for your {settings.PROJECT_NAME} account.</p>
                <p>Click the button below to reset your password:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" style="background-color: #3498db; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">Reset Password</a>
                </div>
                <p>Or copy and paste this link into your browser:</p>
                <p style="background-color: #f4f4f4; padding: 10px; border-radius: 5px; word-break: break-all;">{reset_url}</p>
                <p><strong>This link will expire in {settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS} hours.</strong></p>
                <p>If you did not request this reset, please ignore this email and your password will remain unchanged.</p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #7f8c8d; font-size: 0.9em;">Best regards,<br>The {settings.PROJECT_NAME} Team</p>
            </div>
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
    
    # Use frontend URL based on environment
    if settings.ENVIRONMENT == "production":
        base_url = settings.FRONTEND_URL if hasattr(settings, 'FRONTEND_URL') else "https://chrono-scraper.com"
    else:
        base_url = "http://localhost:5173"
    
    verify_url = f"{base_url}/verify-email?token={token}"
    
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #2c3e50;">Email Verification</h2>
                <p>Hello,</p>
                <p>Thank you for registering with {settings.PROJECT_NAME}.</p>
                <p>Please click the button below to verify your email address:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verify_url}" style="background-color: #27ae60; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">Verify Email</a>
                </div>
                <p>Or copy and paste this link into your browser:</p>
                <p style="background-color: #f4f4f4; padding: 10px; border-radius: 5px; word-break: break-all;">{verify_url}</p>
                <p>If you did not create this account, please ignore this email.</p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #7f8c8d; font-size: 0.9em;">Best regards,<br>The {settings.PROJECT_NAME} Team</p>
            </div>
        </body>
    </html>
    """
    
    
    return subject, html_content


def generate_approval_notification_email(email: str, approved: bool) -> tuple[str, str]:
    """
    Generate account approval notification email
    Returns (subject, html_content)
    """
    # Use frontend URL based on environment
    if settings.ENVIRONMENT == "production":
        base_url = settings.FRONTEND_URL if hasattr(settings, 'FRONTEND_URL') else "https://chrono-scraper.com"
    else:
        base_url = "http://localhost:5173"
    
    if approved:
        subject = f"{settings.PROJECT_NAME} - Account Approved"
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #27ae60;">Account Approved!</h2>
                    <p>Hello,</p>
                    <p>Great news! Your {settings.PROJECT_NAME} account has been approved.</p>
                    <p>You can now log in and start using all the features of the platform.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{base_url}/login" style="background-color: #27ae60; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">Login Now</a>
                    </div>
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                    <p style="color: #7f8c8d; font-size: 0.9em;">Best regards,<br>The {settings.PROJECT_NAME} Team</p>
                </div>
            </body>
        </html>
        """
        
    else:
        subject = f"{settings.PROJECT_NAME} - Account Application Update"
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #e74c3c;">Account Application Update</h2>
                    <p>Hello,</p>
                    <p>Thank you for your interest in {settings.PROJECT_NAME}.</p>
                    <p>Unfortunately, we are unable to approve your account at this time.</p>
                    <p>If you believe this is an error or would like to provide additional information, please contact our support team.</p>
                    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                    <p style="color: #7f8c8d; font-size: 0.9em;">Best regards,<br>The {settings.PROJECT_NAME} Team</p>
                </div>
            </body>
        </html>
        """
        
    
    return subject, html_content