"""
Custom middleware for request handling
"""
import asyncio
from typing import Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to limit request body size"""
    
    def __init__(self, app, max_size: int = 10 * 1024 * 1024):  # 10MB default
        super().__init__(app)
        self.max_size = max_size
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Check Content-Length header
        content_length = request.headers.get("content-length")
        
        if content_length:
            try:
                content_length = int(content_length)
                if content_length > self.max_size:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "detail": f"Request body too large. Maximum size allowed: {self.max_size / 1024 / 1024:.1f}MB",
                            "max_size": self.max_size,
                            "received_size": content_length
                        }
                    )
            except ValueError:
                # Invalid Content-Length header
                pass
        
        # For requests without Content-Length, we'll let FastAPI handle it
        # but we can add streaming size check if needed
        
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Handle any other payload-related errors
            if "too large" in str(e).lower() or "payload" in str(e).lower():
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "detail": "Request payload too large or malformed",
                        "max_size": self.max_size
                    }
                )
            raise


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware to handle request timeouts"""
    
    def __init__(self, app, timeout: int = 30):  # 30 second default
        super().__init__(app)
        self.timeout = timeout
    
    async def dispatch(self, request: Request, call_next: Callable):
        try:
            response = await asyncio.wait_for(
                call_next(request), 
                timeout=self.timeout
            )
            return response
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=status.HTTP_408_REQUEST_TIMEOUT,
                content={
                    "detail": f"Request timeout after {self.timeout} seconds",
                    "timeout": self.timeout
                }
            )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers"""
    
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Remove server header for security
        if "server" in response.headers:
            del response.headers["server"]
        
        return response


class ValidationErrorMiddleware(BaseHTTPMiddleware):
    """Middleware to standardize validation error responses"""
    
    async def dispatch(self, request: Request, call_next: Callable):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Handle Pydantic validation errors
            if "validation error" in str(type(e)).lower():
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={
                        "detail": "Validation error",
                        "errors": str(e)
                    }
                )
            
            # Handle JSON decode errors
            if "json" in str(type(e)).lower() and "decode" in str(e).lower():
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "detail": "Invalid JSON format",
                        "error": "Request body contains invalid JSON"
                    }
                )
            
            raise