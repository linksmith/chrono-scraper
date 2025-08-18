"""
Enhanced email service with Mailgun and Mailpit support
"""
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Email service that supports multiple providers:
    - Mailgun for production
    - Mailpit for development (via SMTP)
    - Fallback to standard SMTP
    """
    
    def __init__(self):
        self.environment = settings.ENVIRONMENT
        self.mailgun_api_key = settings.MAILGUN_API_KEY if hasattr(settings, 'MAILGUN_API_KEY') else None
        self.mailgun_domain = settings.MAILGUN_DOMAIN if hasattr(settings, 'MAILGUN_DOMAIN') else None
        self.mailgun_api_url = settings.MAILGUN_API_URL if hasattr(settings, 'MAILGUN_API_URL') else "https://api.mailgun.net/v3"
        
    async def send_email(
        self,
        email_to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Send email using the appropriate service based on environment
        """
        try:
            if self.environment == "production" and self.mailgun_api_key and self.mailgun_domain:
                return await self._send_mailgun_email(
                    email_to, subject, html_content, text_content, attachments
                )
            else:
                return await self._send_smtp_email(
                    email_to, subject, html_content, text_content
                )
        except Exception as e:
            logger.error(f"Failed to send email to {email_to}: {str(e)}")
            return False
    
    async def _send_mailgun_email(
        self,
        email_to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Send email using Mailgun API
        """
        try:
            async with httpx.AsyncClient() as client:
                data = {
                    "from": f"{settings.EMAILS_FROM_NAME or settings.PROJECT_NAME} <{settings.EMAILS_FROM_EMAIL or f'noreply@{self.mailgun_domain}'}>",
                    "to": email_to,
                    "subject": subject,
                    "html": html_content
                }
                
                if text_content:
                    data["text"] = text_content
                
                # Add custom headers for tracking
                data["h:X-Environment"] = self.environment
                data["h:X-Service"] = settings.PROJECT_NAME
                
                # Handle attachments if provided
                files = None
                if attachments:
                    files = []
                    for attachment in attachments:
                        files.append(
                            ("attachment", (attachment["filename"], attachment["content"], attachment.get("content_type", "application/octet-stream")))
                        )
                
                response = await client.post(
                    f"{self.mailgun_api_url}/{self.mailgun_domain}/messages",
                    auth=("api", self.mailgun_api_key),
                    data=data,
                    files=files if files else None,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"Email sent successfully via Mailgun to {email_to}")
                    return True
                else:
                    logger.error(f"Mailgun API error: {response.status_code} - {response.text}")
                    # Fallback to SMTP if Mailgun fails
                    logger.info("Falling back to SMTP...")
                    return await self._send_smtp_email(email_to, subject, html_content, text_content)
                    
        except Exception as e:
            logger.error(f"Mailgun send failed: {str(e)}")
            # Fallback to SMTP
            logger.info("Falling back to SMTP...")
            return await self._send_smtp_email(email_to, subject, html_content, text_content)
    
    async def _send_smtp_email(
        self,
        email_to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Send email using SMTP (works with Mailpit in development)
        """
        # Use Mailpit settings in development
        if self.environment == "development":
            smtp_host = "mailpit"
            smtp_port = 1025
            smtp_tls = False
            smtp_user = None
            smtp_password = None
        else:
            smtp_host = settings.SMTP_HOST
            smtp_port = settings.SMTP_PORT or 587
            smtp_tls = settings.SMTP_TLS
            smtp_user = settings.SMTP_USER
            smtp_password = settings.SMTP_PASSWORD
        
        if not smtp_host:
            logger.warning("SMTP settings not configured, skipping email send")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.EMAILS_FROM_NAME or settings.PROJECT_NAME} <{settings.EMAILS_FROM_EMAIL or 'noreply@chrono-scraper.local'}>"
            msg["To"] = email_to
            
            # Add text content if provided
            if text_content:
                text_part = MIMEText(text_content, "plain")
                msg.attach(text_part)
            
            # Add HTML content
            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if smtp_tls and self.environment != "development":
                    server.starttls()
                if smtp_user and smtp_password:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully via SMTP to {email_to}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email via SMTP to {email_to}: {str(e)}")
            return False
    
    async def send_bulk_emails(
        self,
        recipients: List[str],
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        use_batch: bool = True
    ) -> Dict[str, bool]:
        """
        Send bulk emails to multiple recipients
        Returns a dict with email addresses as keys and success status as values
        """
        results = {}
        
        if self.environment == "production" and self.mailgun_api_key and use_batch:
            # Use Mailgun's batch sending for production
            try:
                async with httpx.AsyncClient() as client:
                    # Mailgun supports up to 1000 recipients per request
                    batch_size = 1000
                    for i in range(0, len(recipients), batch_size):
                        batch = recipients[i:i + batch_size]
                        
                        data = {
                            "from": f"{settings.EMAILS_FROM_NAME or settings.PROJECT_NAME} <{settings.EMAILS_FROM_EMAIL or f'noreply@{self.mailgun_domain}'}>",
                            "to": batch,
                            "subject": subject,
                            "html": html_content
                        }
                        
                        if text_content:
                            data["text"] = text_content
                        
                        response = await client.post(
                            f"{self.mailgun_api_url}/{self.mailgun_domain}/messages",
                            auth=("api", self.mailgun_api_key),
                            data=data,
                            timeout=60.0
                        )
                        
                        success = response.status_code == 200
                        for recipient in batch:
                            results[recipient] = success
                            
            except Exception as e:
                logger.error(f"Bulk email send failed: {str(e)}")
                # Fallback to individual sends
                for recipient in recipients:
                    results[recipient] = await self.send_email(
                        recipient, subject, html_content, text_content
                    )
        else:
            # Send individually for development or non-batch mode
            for recipient in recipients:
                results[recipient] = await self.send_email(
                    recipient, subject, html_content, text_content
                )
        
        return results
    
    async def send_password_reset_email(
        self,
        email: str,
        token: str,
        user_name: Optional[str] = None
    ) -> bool:
        """Send password reset email"""
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                    border-radius: 10px 10px 0 0;
                }}
                .content {{
                    background: #f9f9f9;
                    padding: 30px;
                    border-radius: 0 0 10px 10px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white !important;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    color: #666;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Password Reset Request</h1>
            </div>
            <div class="content">
                <p>Hello {user_name or 'there'},</p>
                <p>We received a request to reset your password for your Chrono Scraper account.</p>
                <p>Click the button below to reset your password:</p>
                <div style="text-align: center;">
                    <a href="{reset_url}" class="button">Reset Password</a>
                </div>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #667eea;">{reset_url}</p>
                <p><strong>This link will expire in 1 hour for security reasons.</strong></p>
                <p>If you didn't request this password reset, you can safely ignore this email.</p>
            </div>
            <div class="footer">
                <p>&copy; 2024 Chrono Scraper. All rights reserved.</p>
                <p>This is an automated email, please do not reply.</p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
        Password Reset Request
        
        Hello {user_name or 'there'},
        
        We received a request to reset your password for your Chrono Scraper account.
        
        Click this link to reset your password:
        {reset_url}
        
        This link will expire in 1 hour for security reasons.
        
        If you didn't request this password reset, you can safely ignore this email.
        
        Best regards,
        The Chrono Scraper Team
        """
        
        return await self.send_email(
            email_to=email,
            subject="Password Reset Request - Chrono Scraper",
            html_content=html_content,
            text_content=text_content
        )
    
    async def verify_email_address(self, email: str) -> Dict[str, Any]:
        """
        Verify an email address using Mailgun's validation API (production only)
        """
        if self.environment != "production" or not self.mailgun_api_key:
            # Skip validation in development
            return {"is_valid": True, "risk": "low"}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.mailgun_api_url}/v4/address/validate",
                    params={"address": email},
                    auth=("api", self.mailgun_api_key),
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "is_valid": data.get("result") != "undeliverable",
                        "risk": data.get("risk", "unknown"),
                        "reason": data.get("reason"),
                        "did_you_mean": data.get("did_you_mean")
                    }
                else:
                    logger.warning(f"Email validation failed: {response.status_code}")
                    return {"is_valid": True, "risk": "unknown"}
                    
        except Exception as e:
            logger.error(f"Email validation error: {str(e)}")
            return {"is_valid": True, "risk": "unknown"}


# Create singleton instance
email_service = EmailService()