"""
Security module initialization and configuration
Central import point for all security components
"""
from app.core.security_modules.types import (
    ThreatType, ThreatSeverity, ThreatEvent, 
    RateLimitAlgorithm, ThreatLevel, RateLimitConfig
)
from app.core.security_modules.ip_access_control import IPAccessControl, AdminIPWhitelistMiddleware
from app.core.security_modules.advanced_rate_limiting import AdvancedRateLimit, AdvancedRateLimitMiddleware
from app.core.security_modules.security_headers import (
    SecurityHeadersManager, CSRFProtection, SecurityHeadersMiddleware,
    CSPViolationHandler, SecurityPolicyManager
)
from app.core.security_modules.threat_detection import (
    ThreatDetectionEngine, ThreatResponseEngine, ThreatDetectionMiddleware
)

# Import 2FA components with graceful fallback for missing dependencies
try:
    from app.core.security_modules.two_factor_auth import TwoFactorAuth, TwoFactorService, TwoFactorMiddleware
    _2FA_AVAILABLE = True
except ImportError as e:
    print(f"Warning: 2FA components not available due to missing dependency: {e}")
    TwoFactorAuth = None
    TwoFactorService = None
    TwoFactorMiddleware = None
    _2FA_AVAILABLE = False

# Base exports
_base_exports = [
    # Shared Types
    "ThreatType",
    "ThreatSeverity", 
    "ThreatEvent",
    "RateLimitAlgorithm",
    "ThreatLevel",
    "RateLimitConfig",
    
    # IP Access Control
    "IPAccessControl",
    "AdminIPWhitelistMiddleware",
    
    # Advanced Rate Limiting
    "AdvancedRateLimit",
    "AdvancedRateLimitMiddleware",
    
    # Security Headers
    "SecurityHeadersManager",
    "CSRFProtection",
    "SecurityHeadersMiddleware",
    "CSPViolationHandler",
    "SecurityPolicyManager",
    
    # Threat Detection
    "ThreatDetectionEngine",
    "ThreatResponseEngine",
    "ThreatDetectionMiddleware"
]

# Conditional exports
_conditional_exports = []
if _2FA_AVAILABLE:
    _conditional_exports.extend([
        "TwoFactorAuth",
        "TwoFactorService", 
        "TwoFactorMiddleware"
    ])

__all__ = _base_exports + _conditional_exports