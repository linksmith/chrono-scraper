"""
CSRF Protection for Chrono Scraper
"""
import secrets
import hmac
import hashlib
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.status import HTTP_403_FORBIDDEN

from app.core.config import settings
from app.services.session_store import get_session_store


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection middleware"""
    
    def __init__(self, app, secret_key: Optional[str] = None):
        super().__init__(app)
        self.secret_key = secret_key or settings.SECRET_KEY
        
        # Methods that require CSRF protection
        self.protected_methods = {"POST", "PUT", "PATCH", "DELETE"}
        
        # Paths that are exempt from CSRF protection
        self.exempt_paths = {
            "/api/v1/auth/login",  # Login endpoint generates new CSRF token
            "/api/v1/health",      # Health check
            "/docs",               # API documentation
            "/openapi.json"        # OpenAPI schema
        }
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Apply CSRF protection to requests"""
        # In non-production environments, bypass CSRF enforcement for developer ergonomics
        if settings.ENVIRONMENT != "production":
            response = await call_next(request)
            # Still provide CSRF token for clients on GET requests
            if request.method == "GET" and request.url.path.startswith("/api/v1/"):
                csrf_token = await self._generate_csrf_token(request)
                if csrf_token:
                    response.headers["X-CSRF-Token"] = csrf_token
            return response
        
        # Skip CSRF for safe methods and exempt paths
        if (request.method not in self.protected_methods or 
            any(request.url.path.startswith(path) for path in self.exempt_paths)):
            response = await call_next(request)
            
            # For GET requests to API endpoints, include CSRF token in response
            if request.method == "GET" and request.url.path.startswith("/api/v1/"):
                csrf_token = await self._generate_csrf_token(request)
                if csrf_token:
                    response.headers["X-CSRF-Token"] = csrf_token
            
            return response
        
        # Check CSRF token for protected methods
        if not await self._validate_csrf_token(request):
            return JSONResponse(
                status_code=HTTP_403_FORBIDDEN,
                content={
                    "detail": "CSRF token validation failed",
                    "code": "csrf_token_invalid"
                }
            )
        
        response = await call_next(request)
        
        # Regenerate CSRF token after successful protected request
        new_csrf_token = await self._generate_csrf_token(request)
        if new_csrf_token:
            response.headers["X-CSRF-Token"] = new_csrf_token
        
        return response
    
    async def _validate_csrf_token(self, request: Request) -> bool:
        """Validate CSRF token from request"""
        try:
            # Get CSRF token from header or form data
            csrf_token = request.headers.get("X-CSRF-Token")
            
            if not csrf_token:
                # Try to get from form data for POST requests
                if request.method == "POST":
                    form = await request.form()
                    csrf_token = form.get("csrf_token")
            
            if not csrf_token:
                return False
            
            # Get session to verify token
            session_store = await get_session_store()
            session_id = request.cookies.get("session_id")
            
            if not session_id:
                return False
            
            session_data = await session_store.get_session(session_id)
            if not session_data:
                return False
            
            # SessionData is a Pydantic model; use attribute access and correct field name
            user_id = getattr(session_data, "user_id", None)
            if not user_id:
                return False
            
            # Verify CSRF token
            expected_token = self._create_csrf_token(user_id, session_id)
            return hmac.compare_digest(csrf_token, expected_token)
            
        except Exception as e:
            print(f"CSRF validation error: {e}")
            return False
    
    async def _generate_csrf_token(self, request: Request) -> Optional[str]:
        """Generate CSRF token for current session"""
        try:
            session_store = await get_session_store()
            session_id = request.cookies.get("session_id")
            
            if not session_id:
                return None
            
            session_data = await session_store.get_session(session_id)
            if not session_data:
                return None
            
            # SessionData is a Pydantic model; use attribute access and correct field name
            user_id = getattr(session_data, "user_id", None)
            if not user_id:
                return None
            
            return self._create_csrf_token(user_id, session_id)
            
        except Exception as e:
            print(f"CSRF token generation error: {e}")
            return None
    
    def _create_csrf_token(self, user_id: int, session_id: str) -> str:
        """Create CSRF token using HMAC"""
        message = f"{user_id}:{session_id}"
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return f"{user_id}:{signature}"


class DoubleSubmitCookieCSRF:
    """Double Submit Cookie CSRF protection"""
    
    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or settings.SECRET_KEY
    
    def generate_csrf_token(self) -> str:
        """Generate a new CSRF token"""
        return secrets.token_urlsafe(32)
    
    def create_csrf_hash(self, token: str, user_id: int) -> str:
        """Create CSRF token hash"""
        message = f"{token}:{user_id}"
        return hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
    
    def validate_csrf_token(self, token: str, hash_value: str, user_id: int) -> bool:
        """Validate CSRF token against hash"""
        try:
            expected_hash = self.create_csrf_hash(token, user_id)
            return hmac.compare_digest(hash_value, expected_hash)
        except Exception:
            return False


# CSRF protection utility functions
csrf_protection = DoubleSubmitCookieCSRF()


def generate_csrf_token() -> str:
    """Generate CSRF token for forms"""
    return csrf_protection.generate_csrf_token()


def get_csrf_hash(token: str, user_id: int) -> str:
    """Get CSRF hash for validation"""
    return csrf_protection.create_csrf_hash(token, user_id)


def validate_csrf_token(token: str, hash_value: str, user_id: int) -> bool:
    """Validate CSRF token"""
    return csrf_protection.validate_csrf_token(token, hash_value, user_id)


# CSRF token endpoint for frontend
async def get_csrf_token_endpoint(request: Request) -> dict:
    """Endpoint to get CSRF token for frontend"""
    try:
        session_store = await get_session_store()
        session_id = request.cookies.get("session_id")
        
        if not session_id:
            return {"csrf_token": None}
        
        session_data = await session_store.get_session(session_id)
        if not session_data:
            return {"csrf_token": None}
        
        user_id = session_data.get("id")
        if not user_id:
            return {"csrf_token": None}
        
        # Generate token and hash
        token = generate_csrf_token()
        token_hash = get_csrf_hash(token, user_id)
        
        return {
            "csrf_token": token,
            "csrf_hash": token_hash
        }
        
    except Exception as e:
        print(f"CSRF token endpoint error: {e}")
        return {"csrf_token": None}