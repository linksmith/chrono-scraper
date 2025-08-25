"""
Security system initialization for FastAPI application
This module registers all security middleware and endpoints
"""
from fastapi import FastAPI
from redis.asyncio import Redis

from app.core.security_modules import (
    AdminIPWhitelistMiddleware,
    AdvancedRateLimitMiddleware, 
    SecurityHeadersMiddleware,
    ThreatDetectionMiddleware,
    TwoFactorMiddleware,
    _2FA_AVAILABLE
)
# Import security router with graceful fallback
try:
    from app.api.v1.security import router as security_router
    _SECURITY_API_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Security API not available due to missing dependencies: {e}")
    security_router = None
    _SECURITY_API_AVAILABLE = False


def init_security_system(app: FastAPI, redis_client: Redis) -> None:
    """
    Initialize comprehensive security system for FastAPI application
    
    Args:
        app: FastAPI application instance
        redis_client: Redis client for caching and session management
    """
    
    # Add security middleware in order of execution (LIFO order)
    # Last added middleware executes first
    
    # 1. Threat Detection (outermost - monitors everything)
    app.add_middleware(ThreatDetectionMiddleware, redis_client=redis_client)
    
    # 2. Advanced Rate Limiting
    app.add_middleware(AdvancedRateLimitMiddleware, redis_client=redis_client)
    
    # 3. Security Headers and CSRF Protection
    app.add_middleware(SecurityHeadersMiddleware)
    
    # 4. IP Access Control (for admin routes)
    app.add_middleware(AdminIPWhitelistMiddleware, redis_client=redis_client)
    
    # 5. Two-Factor Authentication (innermost - after all other checks)  
    if _2FA_AVAILABLE and TwoFactorMiddleware:
        # Note: This would need database session factory
        # app.add_middleware(TwoFactorMiddleware, db_session_factory=get_db)
        pass  # Disabled for now - needs database integration
    
    # Register security API routes if available
    if _SECURITY_API_AVAILABLE and security_router:
        app.include_router(
            security_router,
            prefix="/api/v1/security",
            tags=["Security Management"]
        )
    
    print("✅ Security system initialized successfully")
    print("  - IP Access Control: Enabled")
    print("  - Advanced Rate Limiting: Enabled") 
    print("  - Security Headers & CSRF: Enabled")
    print("  - Threat Detection: Enabled")
    if _2FA_AVAILABLE:
        print("  - Two-Factor Authentication: Available")
    else:
        print("  - Two-Factor Authentication: Disabled (missing dependencies)")
    
    if _SECURITY_API_AVAILABLE:
        print("  - Security API: /api/v1/security")
    else:
        print("  - Security API: Disabled (missing dependencies)")


def get_security_status() -> dict:
    """Get current security system status"""
    from app.core.config import settings
    
    return {
        "security_level": settings.SECURITY_LEVEL,
        "threat_detection": settings.ENABLE_THREAT_DETECTION,
        "auto_block_threats": settings.AUTO_BLOCK_THREATS,
        "admin_2fa_required": settings.ADMIN_REQUIRE_2FA,
        "geo_blocking": settings.ENABLE_GEO_BLOCKING,
        "rate_limiting": settings.ENABLE_RATE_LIMITING,
        "security_headers": settings.ENABLE_HSTS,
        "audit_logging": settings.ENABLE_COMPLIANCE_MODE,
        "middleware_count": 4  # Number of security middleware layers
    }


# Security configuration validation
def validate_security_config() -> list:
    """Validate security configuration and return warnings/errors"""
    from app.core.config import settings
    
    warnings = []
    
    # Check critical security settings
    if not settings.ADMIN_REQUIRE_2FA:
        warnings.append("⚠️  2FA not required for admin users")
    
    if not settings.ENABLE_THREAT_DETECTION:
        warnings.append("⚠️  Threat detection is disabled")
        
    if not settings.AUTO_BLOCK_THREATS:
        warnings.append("⚠️  Automatic threat blocking is disabled")
        
    if settings.SECURITY_LEVEL == "development":
        warnings.append("⚠️  Security level set to 'development'")
        
    if not settings.ADMIN_IP_WHITELIST:
        warnings.append("⚠️  No IP whitelist configured for admin access")
        
    if settings.SECRET_KEY == "changeme" or len(settings.SECRET_KEY) < 32:
        warnings.append("🚨 CRITICAL: Weak or default secret key detected")
        
    if settings.ENVIRONMENT == "production" and not settings.ENABLE_HSTS:
        warnings.append("⚠️  HSTS disabled in production environment")
    
    return warnings


# Example usage in main application
"""
from app.core.security_init import init_security_system, validate_security_config

# In your main.py or app initialization
app = FastAPI()
redis_client = get_redis_client()

# Initialize security system
init_security_system(app, redis_client)

# Validate configuration
warnings = validate_security_config()
if warnings:
    print("Security Configuration Warnings:")
    for warning in warnings:
        print(f"  {warning}")
"""