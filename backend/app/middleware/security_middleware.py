"""
Security Middleware for FastAPI Application

Integrates comprehensive security hardening into the FastAPI application,
including request validation, security headers, and threat detection.
"""

import logging
import time
from typing import Callable
from fastapi import Request, Response, HTTPException
from fastapi.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..core.security_hardening import security_hardening, add_security_headers, SecurityLevel
from ..core.config import settings

logger = logging.getLogger(__name__)


class SecurityHardeningMiddleware(BaseHTTPMiddleware):
    """
    Comprehensive security middleware that validates requests and adds security headers
    """
    
    def __init__(self, app, security_level: SecurityLevel = SecurityLevel.PRODUCTION):
        super().__init__(app)
        self.security_level = security_level
        
        # Define paths that should skip security validation
        self.skip_validation_paths = {
            "/docs",
            "/redoc", 
            "/openapi.json",
            "/api/v1/health",
            "/api/v1/monitoring/analytics/health",
            "/api/v1/monitoring/rate-limits/health"
        }
        
        # Define high-security paths that need extra validation
        self.high_security_paths = {
            "/api/v1/sharing/",
            "/api/v1/meilisearch/",
            "/api/v1/monitoring/",
            "/api/v1/admin/"
        }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request through security validation and add security headers to response"""
        start_time = time.time()
        
        try:
            # Skip validation for certain paths
            if self._should_skip_validation(request.url.path):
                response = await call_next(request)
                return self._add_security_headers(response)
            
            # Validate request security
            validation_result = await security_hardening.validate_request_security(request)
            
            if not validation_result["allowed"]:
                return await self._handle_security_violation(request, validation_result)
            
            # Add security context to request state
            request.state.security_validation = validation_result
            
            # Check for honeypot triggers
            if await security_hardening.is_honeypot_trigger(request):
                await self._handle_honeypot_trigger(request)
                # Continue processing but log the trigger
            
            # Process the request
            response = await call_next(request)
            
            # Add security headers to response
            response = self._add_security_headers(response)
            
            # Add performance metrics
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = str(process_time)
            
            # Add security score to response headers
            security_score = validation_result.get("security_score", 100)
            response.headers["X-Security-Score"] = str(security_score)
            
            return response
            
        except HTTPException as e:
            # Re-raise HTTP exceptions
            raise e
        except Exception as e:
            logger.error(f"Security middleware error: {e}")
            
            # Log security middleware failure
            await security_hardening._log_security_event(
                event_type="middleware_error",
                severity="error",
                description=f"Security middleware failed: {str(e)}",
                metadata={
                    "path": str(request.url.path),
                    "method": request.method,
                    "error": str(e)
                }
            )
            
            # Continue processing (fail open for availability)
            response = await call_next(request)
            return self._add_security_headers(response)
    
    def _should_skip_validation(self, path: str) -> bool:
        """Check if path should skip security validation"""
        return any(path.startswith(skip_path) for skip_path in self.skip_validation_paths)
    
    def _is_high_security_path(self, path: str) -> bool:
        """Check if path requires high security validation"""
        return any(path.startswith(secure_path) for secure_path in self.high_security_paths)
    
    async def _handle_security_violation(
        self, 
        request: Request, 
        validation_result: dict
    ) -> JSONResponse:
        """Handle security policy violations"""
        client_ip = security_hardening._extract_client_ip(request)
        
        # Record failed attempt
        await security_hardening.record_failed_attempt(client_ip)
        
        # Log detailed security violation
        await security_hardening._log_security_event(
            event_type="security_violation",
            severity="warning",
            description=f"Security policy violation from {client_ip}",
            metadata={
                "client_ip": client_ip,
                "path": str(request.url.path),
                "method": request.method,
                "user_agent": request.headers.get("User-Agent", ""),
                "threats_detected": validation_result.get("threats_detected", []),
                "security_score": validation_result.get("security_score", 0),
                "threat_level": validation_result.get("threat_level", "unknown")
            }
        )
        
        # Determine response based on threat level
        threat_level = validation_result.get("threat_level", "low")
        
        if threat_level == "critical":
            status_code = 403
            detail = "Access denied due to critical security threats"
            headers = {"Retry-After": "3600"}  # 1 hour
        elif threat_level == "high":
            status_code = 429
            detail = "Access temporarily restricted due to security concerns"
            headers = {"Retry-After": "900"}  # 15 minutes
        else:
            status_code = 403
            detail = "Access denied due to security policy"
            headers = {}
        
        # Add security headers
        headers.update({
            "X-Security-Score": str(validation_result.get("security_score", 0)),
            "X-Threat-Level": threat_level,
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY"
        })
        
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": detail,
                "error_code": "SECURITY_VIOLATION",
                "timestamp": time.time()
            },
            headers=headers
        )
    
    async def _handle_honeypot_trigger(self, request: Request):
        """Handle honeypot triggers"""
        client_ip = security_hardening._extract_client_ip(request)
        
        await security_hardening._log_security_event(
            event_type="honeypot_triggered",
            severity="warning", 
            description=f"Honeypot endpoint accessed: {request.url.path}",
            metadata={
                "client_ip": client_ip,
                "path": str(request.url.path),
                "method": request.method,
                "user_agent": request.headers.get("User-Agent", ""),
                "query_params": str(request.url.query)
            }
        )
        
        # Update threat score for this IP
        await security_hardening.record_failed_attempt(client_ip)
    
    def _add_security_headers(self, response: Response) -> Response:
        """Add security headers to response"""
        return add_security_headers(response, self.security_level)


# Factory functions for creating middleware instances
def create_security_middleware(security_level: SecurityLevel = None):
    """Create security hardening middleware"""
    if security_level is None:
        security_level = SecurityLevel(getattr(settings, 'SECURITY_LEVEL', 'production'))
    
    def middleware_factory(app):
        return SecurityHardeningMiddleware(app, security_level)
    
    return middleware_factory