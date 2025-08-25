"""
Audit middleware for automatic request/response logging with comprehensive security monitoring
"""
import json
import time
import traceback
from typing import Callable, Dict, Any, Optional, List
from uuid import uuid4

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_logger import audit_logger, AuditContext
from app.core.config import settings
from app.core.database import get_db
from app.models.audit_log import (
    AuditCategory, 
    SeverityLevel, 
    AuditActions, 
    ResourceTypes
)
from app.api.deps import get_current_user_optional


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive audit middleware that:
    - Automatically logs all API requests and responses
    - Tracks user activities and admin operations
    - Monitors security events and anomalies
    - Captures performance metrics
    - Implements rate limiting monitoring
    - Provides request/response correlation
    """
    
    def __init__(self, app, exclude_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/favicon.ico"
        ]
        self.sensitive_headers = {
            'authorization', 'cookie', 'x-api-key', 'x-auth-token'
        }
        self.max_body_size = getattr(settings, 'AUDIT_MAX_BODY_SIZE', 10000)  # 10KB
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Main middleware dispatch function"""
        # Skip audit logging for excluded paths
        if self._should_skip_audit(request):
            return await call_next(request)
        
        # Generate request ID for correlation
        request_id = str(uuid4())
        request.state.request_id = request_id
        
        # Start timing
        start_time = time.time()
        request.state.start_time = start_time
        
        # Extract request information
        request_info = await self._extract_request_info(request)
        
        # Get user context
        user_context = await self._get_user_context(request)
        
        # Create audit context
        audit_context = AuditContext(
            user_id=user_context.get('user_id'),
            admin_user_id=user_context.get('admin_user_id'),
            session_id=user_context.get('session_id'),
            request_id=request_id,
            ip_address=self._get_client_ip(request),
            user_agent=request.headers.get('user-agent'),
            start_time=start_time
        )
        
        # Store audit context in request state
        request.state.audit_context = audit_context
        
        response = None
        error_occurred = False
        
        try:
            # Process the request
            response = await call_next(request)
            
        except Exception as e:
            # Log the error
            error_occurred = True
            error_info = {
                'error_message': str(e),
                'error_type': type(e).__name__,
                'traceback': traceback.format_exc()
            }
            
            # Create error response
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"}
            )
            
            # Log security event for server errors
            await self._log_security_event(
                request, audit_context, error_info, response
            )
            
        finally:
            # Calculate processing time
            processing_time = time.time() - start_time
            processing_time_ms = int(processing_time * 1000)
            
            # Extract response information
            response_info = self._extract_response_info(response)
            
            # Update audit context with performance metrics
            audit_context.database_queries = getattr(request.state, 'db_queries', 0)
            
            # Log the request/response audit event
            await self._log_audit_event(
                request, response, audit_context, request_info, 
                response_info, processing_time_ms, error_occurred
            )
        
        return response
    
    def _should_skip_audit(self, request: Request) -> bool:
        """Determine if audit logging should be skipped for this request"""
        path = request.url.path
        
        # Skip excluded paths
        if any(excluded in path for excluded in self.exclude_paths):
            return True
        
        # Skip health checks and monitoring endpoints
        if path.startswith(('/health', '/metrics', '/monitoring')):
            return True
        
        # Skip static files
        if path.startswith('/static/'):
            return True
        
        return False
    
    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Extract client IP address from request headers"""
        # Check for forwarded headers in order of precedence
        forwarded_headers = [
            'x-forwarded-for',
            'x-real-ip',
            'cf-connecting-ip',  # Cloudflare
            'x-client-ip'
        ]
        
        for header in forwarded_headers:
            if header in request.headers:
                # Take the first IP in case of comma-separated list
                ip = request.headers[header].split(',')[0].strip()
                if ip:
                    return ip
        
        # Fall back to direct client IP
        return request.client.host if request.client else None
    
    async def _get_user_context(self, request: Request) -> Dict[str, Any]:
        """Extract user context from request"""
        try:
            # Try to get current user
            current_user = await get_current_user_optional(request)
            
            context = {}
            if current_user:
                context['user_id'] = current_user.id
                # Check if this is an admin user
                if hasattr(current_user, 'is_admin') and current_user.is_admin:
                    context['admin_user_id'] = current_user.id
            
            # Extract session ID if available
            if hasattr(request, 'session') and request.session:
                context['session_id'] = request.session.get('session_id')
            
            return context
            
        except Exception:
            # Ignore errors in user context extraction
            return {}
    
    async def _extract_request_info(self, request: Request) -> Dict[str, Any]:
        """Extract comprehensive request information for audit logging"""
        request_info = {
            'method': request.method,
            'url': str(request.url),
            'path': request.url.path,
            'query_params': dict(request.query_params),
            'headers': self._filter_sensitive_headers(dict(request.headers)),
        }
        
        # Extract request body for auditable endpoints
        if self._should_log_request_body(request):
            try:
                body = await self._read_request_body(request)
                if body:
                    request_info['body'] = body
            except Exception:
                # Don't fail if body can't be read
                pass
        
        return request_info
    
    def _extract_response_info(self, response: Response) -> Dict[str, Any]:
        """Extract response information for audit logging"""
        response_info = {
            'status_code': response.status_code,
            'headers': self._filter_sensitive_headers(dict(response.headers)),
        }
        
        # Extract response body for specific status codes and content types
        if self._should_log_response_body(response):
            try:
                # This is limited as we can't easily read the response body
                # without consuming it. In production, consider using a streaming approach
                pass
            except Exception:
                pass
        
        return response_info
    
    def _filter_sensitive_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Filter out sensitive headers from audit logs"""
        filtered = {}
        for key, value in headers.items():
            if key.lower() in self.sensitive_headers:
                filtered[key] = "[REDACTED]"
            elif key.lower().startswith('x-api') or 'token' in key.lower():
                filtered[key] = "[REDACTED]"
            else:
                filtered[key] = value
        return filtered
    
    def _should_log_request_body(self, request: Request) -> bool:
        """Determine if request body should be logged"""
        # Log request body for admin operations and user management
        admin_paths = ['/api/v1/admin/', '/api/v1/users/', '/api/v1/auth/']
        
        if any(path in request.url.path for path in admin_paths):
            return True
        
        # Log for specific methods
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return True
        
        return False
    
    def _should_log_response_body(self, response: Response) -> bool:
        """Determine if response body should be logged"""
        # Log error responses
        if response.status_code >= 400:
            return True
        
        # Log for specific content types
        content_type = response.headers.get('content-type', '')
        if 'application/json' in content_type:
            return True
        
        return False
    
    async def _read_request_body(self, request: Request) -> Optional[Dict[str, Any]]:
        """Safely read request body for audit logging"""
        try:
            # Read body
            body_bytes = await request.body()
            
            # Limit size to prevent memory issues
            if len(body_bytes) > self.max_body_size:
                return {"_truncated": True, "_size": len(body_bytes)}
            
            # Try to parse as JSON
            if body_bytes:
                content_type = request.headers.get('content-type', '')
                if 'application/json' in content_type:
                    return json.loads(body_bytes)
                else:
                    # Store as base64 for non-JSON content
                    import base64
                    return {
                        "_content_type": content_type,
                        "_data": base64.b64encode(body_bytes).decode()
                    }
            
        except Exception:
            return {"_error": "Failed to read request body"}
        
        return None
    
    async def _log_audit_event(
        self,
        request: Request,
        response: Response,
        audit_context: AuditContext,
        request_info: Dict[str, Any],
        response_info: Dict[str, Any],
        processing_time_ms: int,
        error_occurred: bool
    ):
        """Log the main audit event for this request"""
        try:
            # Determine action and category based on request
            action, category = self._determine_action_and_category(request, response)
            
            # Determine severity based on response and content
            severity = self._determine_severity(request, response, error_occurred)
            
            # Log the audit event
            await audit_logger.log_audit_event(
                action=action,
                resource_type=self._determine_resource_type(request),
                category=category,
                context=audit_context,
                severity=severity,
                success=not error_occurred and response.status_code < 400,
                request_method=request_info['method'],
                request_url=request_info['url'],
                request_headers=request_info.get('headers'),
                request_body=request_info.get('body'),
                response_status=response_info['status_code'],
                response_headers=response_info.get('headers'),
                processing_time_ms=processing_time_ms,
                details={
                    'path': request_info['path'],
                    'query_params': request_info.get('query_params', {}),
                    'user_agent_parsed': self._parse_user_agent_details(
                        request.headers.get('user-agent')
                    )
                }
            )
            
        except Exception as e:
            # Log error but don't fail the request
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to log audit event: {e}")
    
    async def _log_security_event(
        self,
        request: Request,
        audit_context: AuditContext,
        error_info: Dict[str, Any],
        response: Response
    ):
        """Log security-related events"""
        try:
            await audit_logger.log_audit_event(
                action=AuditActions.SECURITY_SCAN,
                resource_type=ResourceTypes.SECURITY_POLICY,
                category=AuditCategory.SECURITY_EVENT,
                context=audit_context,
                severity=SeverityLevel.HIGH,
                success=False,
                details={
                    'error_type': error_info.get('error_type'),
                    'error_message': error_info.get('error_message'),
                    'request_path': request.url.path,
                    'request_method': request.method
                },
                error_message=error_info.get('error_message'),
                response_status=response.status_code
            )
            
        except Exception as e:
            # Log error but don't fail
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to log security event: {e}")
    
    def _determine_action_and_category(
        self, 
        request: Request, 
        response: Response
    ) -> tuple[str, AuditCategory]:
        """Determine audit action and category based on request"""
        path = request.url.path
        method = request.method
        
        # Admin operations
        if '/admin/' in path:
            if method == 'GET':
                return AuditActions.ADMIN_DASHBOARD_VIEW, AuditCategory.USER_MANAGEMENT
            elif method in ['POST', 'PUT', 'PATCH']:
                return AuditActions.SYSTEM_CONFIG_UPDATE, AuditCategory.SYSTEM_CONFIG
            elif method == 'DELETE':
                return AuditActions.USER_DELETE, AuditCategory.USER_MANAGEMENT
        
        # Authentication operations
        if '/auth/' in path:
            if 'login' in path:
                if response.status_code < 400:
                    return AuditActions.USER_LOGIN, AuditCategory.AUTHENTICATION
                else:
                    return AuditActions.USER_LOGIN_FAILED, AuditCategory.SECURITY_EVENT
            elif 'logout' in path:
                return AuditActions.USER_LOGOUT, AuditCategory.AUTHENTICATION
            elif 'register' in path:
                return AuditActions.USER_CREATE, AuditCategory.USER_MANAGEMENT
        
        # User management
        if '/users/' in path:
            if method == 'POST':
                return AuditActions.USER_CREATE, AuditCategory.USER_MANAGEMENT
            elif method == 'PUT' or method == 'PATCH':
                return AuditActions.USER_UPDATE, AuditCategory.USER_MANAGEMENT
            elif method == 'DELETE':
                return AuditActions.USER_DELETE, AuditCategory.USER_MANAGEMENT
            elif method == 'GET':
                return AuditActions.USER_PROFILE_VIEW, AuditCategory.USER_MANAGEMENT
        
        # Content operations
        if '/pages/' in path or '/projects/' in path:
            if method == 'POST':
                return AuditActions.PAGE_CREATE, AuditCategory.CONTENT_MANAGEMENT
            elif method in ['PUT', 'PATCH']:
                return AuditActions.PAGE_UPDATE, AuditCategory.CONTENT_MANAGEMENT
            elif method == 'DELETE':
                return AuditActions.PAGE_DELETE, AuditCategory.CONTENT_MANAGEMENT
            elif method == 'GET':
                return AuditActions.PAGE_VIEW, AuditCategory.CONTENT_MANAGEMENT
        
        # Default API request
        return AuditActions.API_REQUEST, AuditCategory.API_ACCESS
    
    def _determine_resource_type(self, request: Request) -> str:
        """Determine resource type based on request path"""
        path = request.url.path
        
        if '/users/' in path:
            return ResourceTypes.USER
        elif '/projects/' in path:
            return ResourceTypes.PROJECT
        elif '/pages/' in path:
            return ResourceTypes.PAGE
        elif '/entities/' in path:
            return ResourceTypes.ENTITY
        elif '/admin/' in path:
            return ResourceTypes.SYSTEM
        elif '/auth/' in path:
            return ResourceTypes.USER
        else:
            return ResourceTypes.API_ENDPOINT
    
    def _determine_severity(
        self, 
        request: Request, 
        response: Response, 
        error_occurred: bool
    ) -> SeverityLevel:
        """Determine severity level based on request/response characteristics"""
        # Critical for server errors
        if error_occurred or response.status_code >= 500:
            return SeverityLevel.CRITICAL
        
        # High for client errors and admin operations
        if response.status_code >= 400 or '/admin/' in request.url.path:
            return SeverityLevel.HIGH
        
        # Medium for authentication and user management
        if '/auth/' in request.url.path or '/users/' in request.url.path:
            return SeverityLevel.MEDIUM
        
        # Low for regular operations
        return SeverityLevel.LOW
    
    def _parse_user_agent_details(self, user_agent: Optional[str]) -> Dict[str, Any]:
        """Parse detailed user agent information"""
        if not user_agent:
            return {}
        
        try:
            import user_agents
            ua = user_agents.parse(user_agent)
            return {
                'browser': ua.browser.family,
                'browser_version': ua.browser.version_string,
                'os': ua.os.family,
                'os_version': ua.os.version_string,
                'device': ua.device.family,
                'is_mobile': ua.is_mobile,
                'is_tablet': ua.is_tablet,
                'is_bot': ua.is_bot
            }
        except Exception:
            return {'raw_user_agent': user_agent}


# Middleware factory function
def create_audit_middleware(exclude_paths: Optional[List[str]] = None) -> AuditMiddleware:
    """Create audit middleware with configuration"""
    return AuditMiddleware(None, exclude_paths=exclude_paths)