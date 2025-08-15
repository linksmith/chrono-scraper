"""
Main FastAPI application
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, ValidationException
from pydantic import ValidationError
import logging

from app.core.config import settings
from app.api.v1.api import api_router
from app.core.middleware import (
    RequestSizeLimitMiddleware,
    RequestTimeoutMiddleware,
    SecurityHeadersMiddleware,
    ValidationErrorMiddleware
)
from app.services.session_store import session_store

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

# Add custom middleware (order matters - last added is first to process)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ValidationErrorMiddleware)
app.add_middleware(RequestTimeoutMiddleware, timeout=60)  # 60 second timeout
app.add_middleware(RequestSizeLimitMiddleware, max_size=10 * 1024 * 1024)  # 10MB limit

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
                    "field": ".".join(str(x) for x in error["loc"]) if error.get("loc") else "unknown",
                    "message": error.get("msg", "Validation failed"),
                    "type": error.get("type", "validation_error"),
                    "input": error.get("input")
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
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "chrono-scraper-api",
            "version": settings.VERSION
        }
    )


# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)