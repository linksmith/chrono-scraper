"""
Enhanced email templates for user approval workflow with action buttons
"""
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.config import settings
from app.models.user import User
from app.services.user_evaluation_service import EvaluationResult


class EmailTemplates:
    """Email template generator for user approval workflow"""
    
    @staticmethod
    def get_base_url() -> str:
        """Get base URL for links based on environment"""
        if settings.ENVIRONMENT == "production":
            return settings.FRONTEND_URL if settings.FRONTEND_URL else "https://chrono-scraper.com"
        else:
            return "http://localhost:5173"
    
    @staticmethod
    def get_backend_url() -> str:
        """Get backend URL for API endpoints"""
        if settings.ENVIRONMENT == "production":
            return settings.BACKEND_URL if hasattr(settings, 'BACKEND_URL') else "https://api.chrono-scraper.com"
        else:
            return "http://localhost:8000"

    @staticmethod
    def generate_admin_approval_notification(
        user: User,
        evaluation: EvaluationResult,
        approval_token: str,
        denial_token: str
    ) -> tuple[str, str, str]:
        """
        Generate admin notification email with embedded action buttons
        Returns (subject, html_content, text_content)
        """
        # Determine recommendation styling
        if evaluation.recommendation == "approve":
            rec_color = "#16a34a"
            rec_bg = "#f0fdf4"
            rec_text = "✅ RECOMMENDED FOR APPROVAL"
            urgency_class = "low-priority"
        elif evaluation.recommendation == "deny":
            rec_color = "#dc2626"
            rec_bg = "#fef2f2"
            rec_text = "❌ RECOMMENDED FOR DENIAL"
            urgency_class = "high-priority"
        else:
            rec_color = "#f59e0b"
            rec_bg = "#fffbeb"
            rec_text = "⚠️ MANUAL REVIEW REQUIRED"
            urgency_class = "medium-priority"
        
        backend_url = EmailTemplates.get_backend_url()
        approval_url = f"{backend_url}/api/v1/admin/approve-user/{approval_token}"
        denial_url = f"{backend_url}/api/v1/admin/deny-user/{denial_token}"
        admin_panel_url = f"{backend_url}/admin/"
        
        subject = f"🔔 User Registration: {user.email} (Score: {evaluation.overall_score:.1f}/10)"
        
        # HTML Email Template
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>User Registration Approval</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            margin: 0;
            padding: 0;
            background-color: #f9fafb;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 25px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .content {{
            padding: 30px 25px;
        }}
        .recommendation {{
            background: {rec_bg};
            border: 2px solid {rec_color};
            color: {rec_color};
            padding: 20px;
            text-align: center;
            border-radius: 8px;
            font-weight: bold;
            font-size: 16px;
            margin: 25px 0;
        }}
        .user-card {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .user-card h3 {{
            margin-top: 0;
            color: #374151;
            font-size: 18px;
        }}
        .user-info {{
            display: grid;
            gap: 8px;
        }}
        .user-info div {{
            display: flex;
        }}
        .user-info strong {{
            min-width: 140px;
            color: #6b7280;
            font-size: 14px;
        }}
        .user-info span {{
            color: #111827;
        }}
        .score-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin: 25px 0;
        }}
        .score-item {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border: 1px solid #e5e7eb;
        }}
        .score-item h4 {{
            margin: 0 0 10px 0;
            color: #6b7280;
            font-size: 14px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        .score-value {{
            font-size: 28px;
            font-weight: 700;
            margin: 5px 0;
        }}
        .score-overall {{ color: #3b82f6; }}
        .score-risk {{ color: #ef4444; }}
        .score-legitimacy {{ color: #10b981; }}
        .score-intent {{ color: #8b5cf6; }}
        .actions {{
            display: flex;
            gap: 15px;
            margin: 30px 0;
        }}
        .btn {{
            display: inline-block;
            padding: 15px 25px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            text-align: center;
            flex: 1;
            font-size: 16px;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .btn-approve {{
            background: #16a34a;
            color: white;
        }}
        .btn-approve:hover {{
            background: #15803d;
        }}
        .btn-deny {{
            background: #dc2626;
            color: white;
        }}
        .btn-deny:hover {{
            background: #b91c1c;
        }}
        .analysis {{
            background: #fffbeb;
            border: 1px solid #fbbf24;
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
        }}
        .analysis h3 {{
            margin-top: 0;
            color: #92400e;
            font-size: 16px;
        }}
        .analysis p {{
            margin: 10px 0;
            color: #451a03;
            line-height: 1.5;
        }}
        .flags {{
            margin: 15px 0;
        }}
        .flag-item {{
            background: white;
            border-radius: 6px;
            padding: 10px;
            margin: 8px 0;
            border-left: 4px solid #fbbf24;
        }}
        .red-flag {{
            border-left-color: #ef4444;
            background: #fef2f2;
        }}
        .positive-flag {{
            border-left-color: #10b981;
            background: #f0fdf4;
        }}
        .footer {{
            background: #f3f4f6;
            padding: 20px 25px;
            text-align: center;
            color: #6b7280;
            font-size: 12px;
        }}
        .footer a {{
            color: #3b82f6;
            text-decoration: none;
        }}
        .confidence {{
            background: #e5e7eb;
            color: #374151;
            padding: 8px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            display: inline-block;
            margin: 10px 0;
        }}
        @media (max-width: 600px) {{
            .container {{
                margin: 0;
                border-radius: 0;
            }}
            .score-grid {{
                grid-template-columns: 1fr;
            }}
            .actions {{
                flex-direction: column;
            }}
            .content {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔔 New User Registration</h1>
            <p style="margin: 5px 0 0 0; opacity: 0.9;">
                {datetime.utcnow().strftime('%B %d, %Y at %H:%M UTC')}
            </p>
        </div>
        
        <div class="content">
            <div class="recommendation {urgency_class}">
                {rec_text}
            </div>
            
            <div class="user-card">
                <h3>👤 User Information</h3>
                <div class="user-info">
                    <div><strong>Email:</strong> <span>{user.email}</span></div>
                    <div><strong>Name:</strong> <span>{user.full_name or 'Not provided'}</span></div>
                    <div><strong>Domain:</strong> <span>{user.email.split('@')[1] if '@' in user.email else 'Unknown'}</span></div>
                    <div><strong>Registered:</strong> <span>{user.created_at.strftime('%Y-%m-%d %H:%M UTC')}</span></div>
                </div>
            </div>
            
            <div class="score-grid">
                <div class="score-item">
                    <h4>Overall Score</h4>
                    <div class="score-value score-overall">{evaluation.overall_score:.1f}/10</div>
                </div>
                <div class="score-item">
                    <h4>Risk Level</h4>
                    <div class="score-value score-risk">{evaluation.risk_score:.1f}/10</div>
                </div>
                <div class="score-item">
                    <h4>Legitimacy</h4>
                    <div class="score-value score-legitimacy">{evaluation.legitimacy_score:.1f}/10</div>
                </div>
                <div class="score-item">
                    <h4>Research Intent</h4>
                    <div class="score-value score-intent">{evaluation.research_intent_score:.1f}/10</div>
                </div>
            </div>
            
            <div class="confidence">
                🎯 Confidence Level: {int(evaluation.confidence * 100)}%
            </div>
            
            <div class="actions">
                <a href="{approval_url}" class="btn btn-approve">
                    ✅ Approve User
                </a>
                <a href="{denial_url}" class="btn btn-deny">
                    ❌ Deny Registration
                </a>
            </div>
            
            <div class="analysis">
                <h3>🧠 LLM Analysis</h3>
                <p><strong>Reasoning:</strong> {evaluation.reasoning}</p>
                
                {f'''
                <div class="flags">
                    <div class="flag-item red-flag">
                        <strong>🚩 Red Flags:</strong> {evaluation.red_flags}
                    </div>
                </div>
                ''' if evaluation.red_flags else ''}
                
                {f'''
                <div class="flags">
                    <div class="flag-item positive-flag">
                        <strong>✅ Positive Indicators:</strong> {evaluation.positive_indicators}
                    </div>
                </div>
                ''' if evaluation.positive_indicators else ''}
            </div>
            
            <div class="user-card">
                <h3>📋 Research Details</h3>
                <div class="user-info">
                    <div><strong>Research Interests:</strong> <span>{user.research_interests or 'Not provided'}</span></div>
                    <div><strong>Affiliation:</strong> <span>{user.academic_affiliation or 'Not provided'}</span></div>
                    <div><strong>Title:</strong> <span>{user.professional_title or 'Not provided'}</span></div>
                    <div><strong>Purpose:</strong> <span>{user.research_purpose or 'Not provided'}</span></div>
                    <div><strong>Expected Usage:</strong> <span>{user.expected_usage or 'Not provided'}</span></div>
                    <div><strong>Website:</strong> <span>{user.organization_website or 'Not provided'}</span></div>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>
                <a href="{admin_panel_url}">Admin Panel</a> • 
                <a href="mailto:{settings.ADMIN_EMAIL}">Contact Support</a><br>
                This notification was generated automatically by {settings.PROJECT_NAME}'s evaluation system.
            </p>
        </div>
    </div>
</body>
</html>
        """
        
        # Text Email Content
        text_content = f"""
🔔 NEW USER REGISTRATION - {settings.PROJECT_NAME}

{rec_text}
Overall Score: {evaluation.overall_score:.1f}/10

USER INFORMATION
================
Email: {user.email}
Name: {user.full_name or 'Not provided'}
Domain: {user.email.split('@')[1] if '@' in user.email else 'Unknown'}
Registered: {user.created_at.strftime('%Y-%m-%d %H:%M UTC')}

EVALUATION SCORES
================
Overall Score: {evaluation.overall_score:.1f}/10
Risk Level: {evaluation.risk_score:.1f}/10  
Legitimacy: {evaluation.legitimacy_score:.1f}/10
Research Intent: {evaluation.research_intent_score:.1f}/10
Confidence: {int(evaluation.confidence * 100)}%

LLM ANALYSIS
============
{evaluation.reasoning}

{f"Red Flags: {evaluation.red_flags}" if evaluation.red_flags else ""}
{f"Positive Indicators: {evaluation.positive_indicators}" if evaluation.positive_indicators else ""}

RESEARCH DETAILS
===============
Research Interests: {user.research_interests or 'Not provided'}
Academic Affiliation: {user.academic_affiliation or 'Not provided'}  
Professional Title: {user.professional_title or 'Not provided'}
Research Purpose: {user.research_purpose or 'Not provided'}
Expected Usage: {user.expected_usage or 'Not provided'}
Organization Website: {user.organization_website or 'Not provided'}

QUICK ACTIONS
============
Approve: {approval_url}
Deny: {denial_url}
Admin Panel: {admin_panel_url}

---
This notification was generated automatically by {settings.PROJECT_NAME}.
        """
        
        return subject, html_content, text_content

    @staticmethod 
    def generate_user_approval_confirmation(
        user: User,
        approved: bool,
        admin_message: Optional[str] = None
    ) -> tuple[str, str, str]:
        """
        Generate user confirmation email for approval/denial
        Returns (subject, html_content, text_content)
        """
        base_url = EmailTemplates.get_base_url()
        
        if approved:
            subject = f"🎉 Welcome to {settings.PROJECT_NAME} - Account Approved!"
            status_color = "#16a34a"
            status_bg = "#f0fdf4" 
            status_text = "✅ Account Approved"
            main_text = f"Great news! Your {settings.PROJECT_NAME} account has been approved and you can now access all platform features."
            cta_text = "Start Using Platform"
            cta_url = f"{base_url}/login"
        else:
            subject = f"{settings.PROJECT_NAME} - Registration Update"
            status_color = "#dc2626"
            status_bg = "#fef2f2"
            status_text = "Registration Decision"
            main_text = f"Thank you for your interest in {settings.PROJECT_NAME}. Unfortunately, we are unable to approve your account at this time."
            cta_text = "Contact Support"
            cta_url = f"mailto:{settings.ADMIN_EMAIL or 'support@chrono-scraper.com'}"
        
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Account Status Update</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            margin: 0;
            padding: 0;
            background-color: #f9fafb;
        }}
        .container {{
            max-width: 600px;
            margin: 40px auto;
            background-color: white;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        .header {{
            background: {status_color};
            color: white;
            padding: 40px 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 32px;
            font-weight: 600;
        }}
        .content {{
            padding: 40px 30px;
        }}
        .status-badge {{
            background: {status_bg};
            border: 2px solid {status_color};
            color: {status_color};
            padding: 15px 25px;
            text-align: center;
            border-radius: 10px;
            font-weight: 600;
            font-size: 18px;
            margin: 25px 0;
        }}
        .main-message {{
            font-size: 18px;
            line-height: 1.7;
            margin: 25px 0;
            color: #374151;
        }}
        .cta-button {{
            display: inline-block;
            background: {status_color};
            color: white;
            padding: 18px 35px;
            text-decoration: none;
            border-radius: 10px;
            font-weight: 600;
            font-size: 16px;
            margin: 30px 0;
            transition: all 0.3s ease;
        }}
        .user-info {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
        }}
        .footer {{
            background: #f3f4f6;
            padding: 25px 30px;
            text-align: center;
            color: #6b7280;
            font-size: 14px;
        }}
        {".admin-message { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 20px; margin: 20px 0; border-radius: 8px; }" if admin_message else ""}
        @media (max-width: 600px) {{
            .container {{ margin: 20px; }}
            .header, .content {{ padding: 25px 20px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{settings.PROJECT_NAME}</h1>
        </div>
        
        <div class="content">
            <div class="status-badge">
                {status_text}
            </div>
            
            <div class="user-info">
                <strong>Account:</strong> {user.email}<br>
                <strong>Date:</strong> {datetime.utcnow().strftime('%B %d, %Y')}
            </div>
            
            <div class="main-message">
                {main_text}
            </div>
            
            {f'''
            <div class="admin-message">
                <strong>📝 Additional Information:</strong><br>
                {admin_message}
            </div>
            ''' if admin_message else ''}
            
            <div style="text-align: center;">
                <a href="{cta_url}" class="cta-button">
                    {cta_text}
                </a>
            </div>
            
            {'''
            <div style="margin-top: 30px; padding: 20px; background: #e0f2fe; border-radius: 8px;">
                <h3 style="margin-top: 0; color: #0277bd;">🚀 What's Next?</h3>
                <ul style="color: #01579b; margin: 10px 0;">
                    <li>Log in to your account</li>
                    <li>Create your first scraping project</li>
                    <li>Explore historical web content</li>
                    <li>Start your research journey</li>
                </ul>
            </div>
            ''' if approved else ''}
        </div>
        
        <div class="footer">
            <p>
                If you have any questions, please contact us at<br>
                <strong>{settings.ADMIN_EMAIL or 'support@chrono-scraper.com'}</strong>
            </p>
            <p style="margin-top: 20px; font-size: 12px; opacity: 0.8;">
                © {datetime.utcnow().year} {settings.PROJECT_NAME}. Professional web archiving and research platform.
            </p>
        </div>
    </div>
</body>
</html>
        """
        
        text_content = f"""
{settings.PROJECT_NAME} - Account Status Update

{status_text.upper()}

Account: {user.email}
Date: {datetime.utcnow().strftime('%B %d, %Y')}

{main_text}

{f"Additional Information: {admin_message}" if admin_message else ""}

{cta_text}: {cta_url}

{"Next Steps:" if approved else ""}
{'''
- Log in to your account
- Create your first scraping project  
- Explore historical web content
- Start your research journey
''' if approved else ''}

Questions? Contact us at {settings.ADMIN_EMAIL or 'support@chrono-scraper.com'}

© {datetime.utcnow().year} {settings.PROJECT_NAME}
        """
        
        return subject, html_content, text_content

    @staticmethod
    def generate_pending_approval_notification(user: User) -> tuple[str, str, str]:
        """
        Generate email to user confirming registration and pending approval
        Returns (subject, html_content, text_content)
        """
        subject = f"✅ Registration Received - {settings.PROJECT_NAME}"
        
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Registration Confirmation</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            margin: 0;
            padding: 0;
            background-color: #f9fafb;
        }}
        .container {{
            max-width: 600px;
            margin: 40px auto;
            background-color: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }}
        .content {{
            padding: 40px 30px;
        }}
        .status {{
            background: #eff6ff;
            border: 2px solid #3b82f6;
            color: #1e40af;
            padding: 20px;
            text-align: center;
            border-radius: 10px;
            font-weight: 600;
            margin: 25px 0;
        }}
        .timeline {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 25px;
            margin: 25px 0;
        }}
        .timeline-item {{
            display: flex;
            margin: 15px 0;
            align-items: center;
        }}
        .timeline-icon {{
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 15px;
            font-size: 14px;
            font-weight: bold;
        }}
        .completed {{ background: #10b981; color: white; }}
        .pending {{ background: #f59e0b; color: white; }}
        .upcoming {{ background: #e5e7eb; color: #6b7280; }}
        .footer {{
            background: #f3f4f6;
            padding: 25px 30px;
            text-align: center;
            color: #6b7280;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎯 Registration Received!</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9; font-size: 16px;">
                Thank you for joining {settings.PROJECT_NAME}
            </p>
        </div>
        
        <div class="content">
            <div class="status">
                ⏳ Your registration is being reviewed
            </div>
            
            <p style="font-size: 18px; color: #374151;">
                Hello <strong>{user.full_name or user.email}</strong>,
            </p>
            
            <p style="font-size: 16px; line-height: 1.7; color: #4b5563;">
                We've received your registration for {settings.PROJECT_NAME} and our team is currently 
                reviewing your application. This process typically takes 1-2 business days.
            </p>
            
            <div class="timeline">
                <h3 style="margin-top: 0; color: #374151;">📋 Application Process</h3>
                
                <div class="timeline-item">
                    <div class="timeline-icon completed">✓</div>
                    <div>
                        <strong>Registration Submitted</strong><br>
                        <small style="color: #6b7280;">Your application has been received</small>
                    </div>
                </div>
                
                <div class="timeline-item">
                    <div class="timeline-icon pending">⏳</div>
                    <div>
                        <strong>Under Review</strong><br>
                        <small style="color: #6b7280;">Our team is evaluating your application</small>
                    </div>
                </div>
                
                <div class="timeline-item">
                    <div class="timeline-icon upcoming">📧</div>
                    <div>
                        <strong>Decision Notification</strong><br>
                        <small style="color: #6b7280;">You'll receive an email with the outcome</small>
                    </div>
                </div>
                
                <div class="timeline-item">
                    <div class="timeline-icon upcoming">🚀</div>
                    <div>
                        <strong>Platform Access</strong><br>
                        <small style="color: #6b7280;">Start your research journey</small>
                    </div>
                </div>
            </div>
            
            <div style="background: #eff6ff; border-radius: 8px; padding: 20px; margin: 25px 0;">
                <h3 style="margin-top: 0; color: #1e40af;">💡 While You Wait</h3>
                <ul style="color: #1e3a8a; margin: 10px 0;">
                    <li>Check out our <a href="#" style="color: #3b82f6;">documentation</a> to learn about features</li>
                    <li>Read our <a href="#" style="color: #3b82f6;">research guide</a> for best practices</li>
                    <li>Plan your first scraping project</li>
                </ul>
            </div>
        </div>
        
        <div class="footer">
            <p>
                <strong>Questions about your application?</strong><br>
                Contact us at <strong>{settings.ADMIN_EMAIL or 'support@chrono-scraper.com'}</strong>
            </p>
        </div>
    </div>
</body>
</html>
        """
        
        text_content = f"""
{settings.PROJECT_NAME} - Registration Received

Hello {user.full_name or user.email},

✅ REGISTRATION RECEIVED

We've received your registration for {settings.PROJECT_NAME} and our team is currently reviewing your application. This process typically takes 1-2 business days.

APPLICATION PROCESS:
✓ Registration Submitted - Your application has been received  
⏳ Under Review - Our team is evaluating your application
📧 Decision Notification - You'll receive an email with the outcome
🚀 Platform Access - Start your research journey

WHILE YOU WAIT:
- Review our documentation to learn about features
- Read our research guide for best practices  
- Plan your first scraping project

Questions? Contact us at {settings.ADMIN_EMAIL or 'support@chrono-scraper.com'}

© {datetime.utcnow().year} {settings.PROJECT_NAME}
        """
        
        return subject, html_content, text_content


# Global instance for easy access
email_templates = EmailTemplates()