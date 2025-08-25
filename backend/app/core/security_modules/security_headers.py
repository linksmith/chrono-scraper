"""
Comprehensive security headers implementation with CSP, HSTS, and CSRF protection
"""
import secrets
import hashlib
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta, timezone
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import re

from app.core.config import settings


class SecurityHeadersManager:
    """
    Manages comprehensive security headers including:
    - Content Security Policy (CSP) with nonce support
    - HTTP Strict Transport Security (HSTS)
    - X-Frame-Options, X-Content-Type-Options, etc.
    - Certificate pinning headers
    - Permissions Policy
    """
    
    def __init__(self):
        self.nonces: Dict[str, str] = {}  # Session ID -> nonce mapping
        self.csp_violation_count: Dict[str, int] = {}
    
    def generate_nonce(self, session_id: Optional[str] = None) -> str:
        """Generate cryptographically secure nonce for CSP"""
        nonce = secrets.token_urlsafe(16)
        if session_id:
            self.nonces[session_id] = nonce
        return nonce
    
    def get_csp_policy(self, nonce: Optional[str] = None, is_admin: bool = False) -> str:
        """
        Generate Content Security Policy based on context
        """
        if is_admin:
            # More restrictive CSP for admin pages
            directives = [
                "default-src 'self'",
                f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic'" if nonce else "script-src 'self'",
                f"style-src 'self' 'nonce-{nonce} 'unsafe-inline'" if nonce else "style-src 'self' 'unsafe-inline'",
                "img-src 'self' data: https:",
                "font-src 'self'",
                "connect-src 'self'",
                "form-action 'self'",
                "base-uri 'self'",
                "frame-ancestors 'none'",
                "object-src 'none'",
                "media-src 'self'",
                "worker-src 'self'",
                "manifest-src 'self'",
                "frame-src 'none'",
                "child-src 'none'",
                "upgrade-insecure-requests"
            ]
        else:
            # Standard CSP for regular pages
            directives = [
                "default-src 'self'",
                f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com" if nonce else "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
                f"style-src 'self' 'nonce-{nonce}' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com" if nonce else "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com",
                "img-src 'self' data: https:",
                "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com",
                "connect-src 'self' ws: wss:",
                "form-action 'self'",
                "base-uri 'self'",
                "frame-ancestors 'self'",
                "object-src 'none'",
                "media-src 'self'",
                "worker-src 'self'",
                "manifest-src 'self'"
            ]
        
        policy = "; ".join(directives)
        
        # Add report URI if configured
        if settings.CSP_REPORT_URI:
            policy += f"; report-uri {settings.CSP_REPORT_URI}"
        
        return policy
    
    def get_security_headers(self, request: Request, response: Response, is_admin: bool = False) -> Dict[str, str]:
        """Get all security headers for response"""
        headers = {}
        
        # Generate nonce if CSP nonce is enabled
        nonce = None
        if settings.ENABLE_CSP_NONCE:
            session_id = request.cookies.get("session_id")
            nonce = self.generate_nonce(session_id)
        
        # Content Security Policy
        headers["Content-Security-Policy"] = self.get_csp_policy(nonce, is_admin)
        
        # HSTS (HTTP Strict Transport Security)
        if settings.ENABLE_HSTS and settings.ENVIRONMENT == "production":
            hsts_value = f"max-age={settings.HSTS_MAX_AGE}"
            if settings.HSTS_INCLUDE_SUBDOMAINS:
                hsts_value += "; includeSubDomains"
            if settings.HSTS_PRELOAD:
                hsts_value += "; preload"
            headers["Strict-Transport-Security"] = hsts_value
        
        # X-Frame-Options
        headers["X-Frame-Options"] = settings.X_FRAME_OPTIONS
        
        # X-Content-Type-Options
        headers["X-Content-Type-Options"] = settings.X_CONTENT_TYPE_OPTIONS
        
        # X-XSS-Protection (legacy but still useful)
        headers["X-XSS-Protection"] = settings.X_XSS_PROTECTION
        
        # Referrer Policy
        headers["Referrer-Policy"] = settings.REFERRER_POLICY
        
        # Permissions Policy (formerly Feature Policy)
        headers["Permissions-Policy"] = settings.PERMISSIONS_POLICY
        
        # Certificate Pinning (HPKP) - only in production with explicit config
        if settings.ENABLE_CERTIFICATE_PINNING and settings.PINNED_CERTIFICATES:
            pin_header = "pin-sha256=\"" + "\"; pin-sha256=\"".join(settings.PINNED_CERTIFICATES) + "\""
            pin_header += f"; max-age={settings.HSTS_MAX_AGE}; includeSubDomains"
            headers["Public-Key-Pins"] = pin_header
        
        # Cache Control for sensitive pages
        if is_admin:
            headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            headers["Pragma"] = "no-cache"
            headers["Expires"] = "0"
        
        # Add nonce to response for template usage
        if nonce:
            # Store nonce in response for template access
            setattr(response, "csp_nonce", nonce)
        
        return headers


class CSRFProtection:
    """
    CSRF (Cross-Site Request Forgery) protection implementation
    Uses double-submit cookie pattern and synchronizer tokens
    """
    
    def __init__(self):
        self.token_cache: Dict[str, Dict] = {}
        self.token_lifetime = 3600  # 1 hour
    
    def generate_csrf_token(self, session_id: str) -> str:
        """Generate CSRF token for session"""
        token = secrets.token_urlsafe(32)
        
        # Store token with expiry
        self.token_cache[session_id] = {
            "token": token,
            "created_at": datetime.now(timezone.utc),
            "used": False
        }
        
        return token
    
    def validate_csrf_token(self, session_id: str, token: str, one_time_use: bool = True) -> bool:
        """Validate CSRF token"""
        if session_id not in self.token_cache:
            return False
        
        cached_data = self.token_cache[session_id]
        
        # Check if token matches
        if cached_data["token"] != token:
            return False
        
        # Check if token has expired
        if datetime.now(timezone.utc) - cached_data["created_at"] > timedelta(seconds=self.token_lifetime):
            del self.token_cache[session_id]
            return False
        
        # Check if token was already used (for one-time use)
        if one_time_use and cached_data.get("used", False):
            return False
        
        # Mark as used if one-time use
        if one_time_use:
            cached_data["used"] = True
        
        return True
    
    def clean_expired_tokens(self):
        """Clean up expired tokens"""
        current_time = datetime.now(timezone.utc)
        expired_sessions = []
        
        for session_id, data in self.token_cache.items():
            if current_time - data["created_at"] > timedelta(seconds=self.token_lifetime):
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self.token_cache[session_id]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive security headers middleware
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.headers_manager = SecurityHeadersManager()
        self.csrf_protection = CSRFProtection()
        
        # Paths that require CSRF protection
        self.csrf_protected_paths = {
            "/admin",
            "/api/v1/admin",
            "/api/v1/auth/login",
            "/api/v1/auth/password-reset",
            "/api/v1/projects",
            "/api/v1/users"
        }
        
        # Methods that require CSRF protection
        self.csrf_protected_methods = {"POST", "PUT", "PATCH", "DELETE"}
    
    async def dispatch(self, request: Request, call_next):
        """Apply security headers and CSRF protection"""
        # Check if this is an admin route
        is_admin = self._is_admin_route(request)
        
        # CSRF Protection for state-changing operations
        if self._requires_csrf_protection(request):
            if not await self._validate_csrf_token(request):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "CSRF token missing or invalid"}
                )
        
        # Process request
        response = await call_next(request)
        
        # Apply security headers
        security_headers = self.headers_manager.get_security_headers(request, response, is_admin)
        
        for header_name, header_value in security_headers.items():
            response.headers[header_name] = header_value
        
        # Add CSRF token to response for subsequent requests
        if self._should_add_csrf_token(request, response):
            await self._add_csrf_token(request, response)
        
        # Set secure cookie attributes
        self._secure_cookies(response)
        
        return response
    
    def _is_admin_route(self, request: Request) -> bool:
        """Check if request is for admin route"""
        path = request.url.path
        return path.startswith("/admin") or path.startswith("/api/v1/admin")
    
    def _requires_csrf_protection(self, request: Request) -> bool:
        """Check if request requires CSRF protection"""
        # Skip GET, HEAD, OPTIONS requests
        if request.method not in self.csrf_protected_methods:
            return False
        
        # Skip API endpoints with API key authentication
        if request.headers.get("X-API-Key"):
            return False
        
        # Check if path requires CSRF protection
        path = request.url.path
        return any(path.startswith(protected_path) for protected_path in self.csrf_protected_paths)
    
    async def _validate_csrf_token(self, request: Request) -> bool:
        """Validate CSRF token from request"""
        # Get session ID
        session_id = request.cookies.get("session_id")
        if not session_id:
            return False
        
        # Get CSRF token from header or form data
        csrf_token = request.headers.get("X-CSRF-Token")
        
        if not csrf_token:
            # Try to get from form data
            if request.method == "POST":
                try:
                    form = await request.form()
                    csrf_token = form.get("csrf_token")
                except:
                    pass
        
        if not csrf_token:
            return False
        
        # Validate token
        return self.csrf_protection.validate_csrf_token(session_id, csrf_token)
    
    def _should_add_csrf_token(self, request: Request, response: Response) -> bool:
        """Check if CSRF token should be added to response"""
        # Add to login responses and admin pages
        path = request.url.path
        return (
            path.startswith("/admin") or
            path.startswith("/api/v1/auth/login") or
            (response.status_code == 200 and request.cookies.get("session_id"))
        )
    
    async def _add_csrf_token(self, request: Request, response: Response):
        """Add CSRF token to response"""
        session_id = request.cookies.get("session_id")
        if not session_id:
            return
        
        # Generate new token
        csrf_token = self.csrf_protection.generate_csrf_token(session_id)
        
        # Add as header for API responses
        response.headers["X-CSRF-Token"] = csrf_token
        
        # Add as cookie for form-based requests
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            max_age=3600,  # 1 hour
            httponly=True,
            secure=settings.ENVIRONMENT == "production",
            samesite="strict"
        )
    
    def _secure_cookies(self, response: Response):
        """Apply secure attributes to cookies"""
        # This is handled in the session middleware, but we can add additional security here
        if "set-cookie" in response.headers:
            cookies = response.headers.getlist("set-cookie")
            new_cookies = []
            
            for cookie in cookies:
                # Ensure session cookies have security attributes
                if any(name in cookie.lower() for name in ["session", "csrf", "auth"]):
                    # Add HttpOnly if not present
                    if "HttpOnly" not in cookie and "httponly" not in cookie.lower():
                        cookie += "; HttpOnly"
                    
                    # Add Secure in production
                    if settings.ENVIRONMENT == "production" and "Secure" not in cookie and "secure" not in cookie.lower():
                        cookie += "; Secure"
                    
                    # Add SameSite if not present
                    if "SameSite" not in cookie and "samesite" not in cookie.lower():
                        cookie += "; SameSite=Strict"
                
                new_cookies.append(cookie)
            
            # Replace cookies
            response.headers._list = [
                (name, value) for name, value in response.headers._list
                if name.lower() != "set-cookie"
            ]
            
            for cookie in new_cookies:
                response.headers.append("set-cookie", cookie)


class CSPViolationHandler:
    """
    Handle Content Security Policy violation reports
    """
    
    def __init__(self):
        self.violations: List[Dict] = []
        self.violation_counts: Dict[str, int] = {}
    
    async def handle_csp_violation(self, request: Request) -> JSONResponse:
        """Handle CSP violation report"""
        try:
            violation_report = await request.json()
            
            # Extract violation details
            csp_report = violation_report.get("csp-report", {})
            
            violation_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "document_uri": csp_report.get("document-uri"),
                "referrer": csp_report.get("referrer"),
                "blocked_uri": csp_report.get("blocked-uri"),
                "violated_directive": csp_report.get("violated-directive"),
                "effective_directive": csp_report.get("effective-directive"),
                "original_policy": csp_report.get("original-policy"),
                "disposition": csp_report.get("disposition"),
                "status_code": csp_report.get("status-code"),
                "source_file": csp_report.get("source-file"),
                "line_number": csp_report.get("line-number"),
                "column_number": csp_report.get("column-number")
            }
            
            # Store violation
            self.violations.append(violation_data)
            
            # Count violations by type
            directive = violation_data.get("violated_directive", "unknown")
            self.violation_counts[directive] = self.violation_counts.get(directive, 0) + 1
            
            # Log violation
            print(f"CSP Violation: {violation_data['violated_directive']} - {violation_data['blocked_uri']}")
            
            # In production, you might want to:
            # 1. Store in database for analysis
            # 2. Alert security team if critical violations
            # 3. Auto-update CSP policy based on legitimate violations
            
            return JSONResponse(content={"status": "received"}, status_code=204)
            
        except Exception as e:
            print(f"Error processing CSP violation report: {e}")
            return JSONResponse(content={"error": "Invalid report"}, status_code=400)
    
    def get_violation_statistics(self) -> Dict:
        """Get CSP violation statistics"""
        return {
            "total_violations": len(self.violations),
            "violations_by_directive": self.violation_counts,
            "recent_violations": self.violations[-10:] if self.violations else []
        }


class SecurityPolicyManager:
    """
    Manage security policies dynamically based on threat level and context
    """
    
    def __init__(self):
        self.policy_templates = {
            "strict": {
                "csp": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'",
                "frame_options": "DENY",
                "referrer_policy": "no-referrer",
                "permissions_policy": "geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=(), speaker=()"
            },
            "moderate": {
                "csp": "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: https:; font-src 'self' https://fonts.gstatic.com; connect-src 'self' wss:; form-action 'self'; base-uri 'self'; frame-ancestors 'self'; object-src 'none'",
                "frame_options": "SAMEORIGIN",
                "referrer_policy": "strict-origin-when-cross-origin",
                "permissions_policy": "geolocation=(), microphone=(), camera=()"
            },
            "relaxed": {
                "csp": "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: https:; frame-ancestors 'self'",
                "frame_options": "SAMEORIGIN",
                "referrer_policy": "origin-when-cross-origin",
                "permissions_policy": "geolocation=()"
            }
        }
    
    def get_policy_for_threat_level(self, threat_level: str) -> Dict[str, str]:
        """Get security policy based on threat level"""
        if threat_level in ["high", "critical"]:
            return self.policy_templates["strict"]
        elif threat_level == "medium":
            return self.policy_templates["moderate"]
        else:
            return self.policy_templates["relaxed"]
    
    def get_policy_for_user_type(self, is_admin: bool, is_authenticated: bool) -> Dict[str, str]:
        """Get security policy based on user type"""
        if is_admin:
            return self.policy_templates["strict"]
        elif is_authenticated:
            return self.policy_templates["moderate"]
        else:
            return self.policy_templates["relaxed"]