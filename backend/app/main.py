"""
Main FastAPI application
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, ValidationException
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware
import logging

from app.core.config import settings
from app.api.v1.api import api_router
from app.core.middleware import (
    RequestSizeLimitMiddleware,
    RequestTimeoutMiddleware,
    SecurityHeadersMiddleware,
    ValidationErrorMiddleware
)
from app.core.security_middleware import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware as EnhancedSecurityHeaders,
    RequestLoggingMiddleware,
    SessionSecurityMiddleware
)
from app.core.csrf_protection import CSRFMiddleware
from app.services.session_store import session_store, get_session_store
from app.admin.config import create_admin
from app.admin.views import ADMIN_VIEWS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle
    """
    # Startup
    logger.info("Starting up Chrono Scraper API...")
    logger.info("Initializing Redis session store...")
    
    # Ensure session store is ready; RateLimitMiddleware will lazy-init Redis
    await get_session_store()
    logger.info("Session store ready")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Chrono Scraper API...")
    logger.info("Closing Redis session store...")
    await session_store.close()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Set up CORS with normalized origins (no trailing slashes)
normalized_cors_origins = [
    str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS
]

# Add security middleware (order matters - last added is first to process)
app.add_middleware(EnhancedSecurityHeaders)
app.add_middleware(SessionSecurityMiddleware)
app.add_middleware(RequestLoggingMiddleware, log_sensitive_endpoints=True)
app.add_middleware(CSRFMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(ValidationErrorMiddleware)
app.add_middleware(RequestTimeoutMiddleware, timeout=60)  # 60 second timeout
app.add_middleware(RequestSizeLimitMiddleware, max_size=10 * 1024 * 1024)  # 10MB limit

# Add session middleware for admin panel
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Register RateLimitMiddleware early; it will lazy-init Redis
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=normalized_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": [
                {
                    "field": ".".join(str(x) for x in error.get("loc", [])) if isinstance(error, dict) else "unknown",
                    "message": (error.get("msg") if isinstance(error, dict) else str(error)) or "Validation failed",
                    "type": (error.get("type") if isinstance(error, dict) else "validation_error"),
                }
                for error in exc.errors()
            ]
        }
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    """Handle direct Pydantic validation errors"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation error",
            "errors": [
                {
                    "field": ".".join(str(x) for x in error["loc"]) if error.get("loc") else "unknown",
                    "message": error.get("msg", "Validation failed"),
                    "type": error.get("type", "validation_error")
                }
                for error in exc.errors()
            ]
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url)
        }
    )


@app.exception_handler(500)
async def internal_server_error_handler(request: Request, exc: Exception):
    """Handle internal server errors"""
    logger.error(f"Internal server error: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "status_code": 500,
            "path": str(request.url)
        }
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Chrono Scraper API",
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    # Keep minimal for test compatibility
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.get("/api/v1/csrf-token")
async def get_csrf_token(request: Request):
    """Get CSRF token for frontend"""
    from app.core.csrf_protection import get_csrf_token_endpoint
    return await get_csrf_token_endpoint(request)


# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Configure admin panel
admin = create_admin(app)

# Register admin views
for view_class in ADMIN_VIEWS:
    admin.add_view(view_class)