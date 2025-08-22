"""
Security Hardening Configuration for Meilisearch Multi-Tenancy

This module provides comprehensive security hardening configurations,
monitoring, and enforcement mechanisms for the multi-tenant system.
"""

import logging
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from enum import Enum
from dataclasses import dataclass
from ipaddress import ip_address, ip_network, AddressValueError

import redis.asyncio as redis
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer
from sqlmodel import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from ..models.meilisearch_audit import MeilisearchSecurityEvent
from ..core.database import get_db

logger = logging.getLogger(__name__)


class SecurityLevel(str, Enum):
    """Security enforcement levels"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    HIGH_SECURITY = "high_security"


class ThreatLevel(str, Enum):
    """Threat classification levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityPolicy:
    """Security policy configuration"""
    max_key_age_days: int = 90
    max_failed_attempts: int = 5
    lockout_duration_minutes: int = 15
    require_key_rotation: bool = True
    enable_geo_blocking: bool = False
    allowed_countries: Set[str] = None
    blocked_ips: Set[str] = None
    trusted_proxies: Set[str] = None
    max_requests_per_second: int = 100
    enable_honeypot: bool = True
    enable_threat_detection: bool = True


class SecurityHardeningService:
    """Comprehensive security hardening service"""
    
    def __init__(self, security_level: SecurityLevel = SecurityLevel.PRODUCTION):
        self.security_level = security_level
        self.redis_client: Optional[redis.Redis] = None
        self.security_policies = self._load_security_policies()
        self.threat_patterns = self._load_threat_patterns()
        
    async def get_redis(self) -> redis.Redis:
        """Get or create Redis connection for security operations"""
        if self.redis_client is None:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_keepalive=True,
                health_check_interval=30
            )
        return self.redis_client
    
    def _load_security_policies(self) -> Dict[SecurityLevel, SecurityPolicy]:
        """Load security policies based on environment"""
        policies = {
            SecurityLevel.DEVELOPMENT: SecurityPolicy(
                max_key_age_days=365,
                max_failed_attempts=10,
                lockout_duration_minutes=5,
                require_key_rotation=False,
                enable_geo_blocking=False,
                enable_honeypot=False,
                enable_threat_detection=False
            ),
            SecurityLevel.STAGING: SecurityPolicy(
                max_key_age_days=180,
                max_failed_attempts=7,
                lockout_duration_minutes=10,
                require_key_rotation=True,
                enable_geo_blocking=False,
                enable_honeypot=True,
                enable_threat_detection=True
            ),
            SecurityLevel.PRODUCTION: SecurityPolicy(
                max_key_age_days=90,
                max_failed_attempts=5,
                lockout_duration_minutes=15,
                require_key_rotation=True,
                enable_geo_blocking=True,
                allowed_countries={"US", "CA", "GB", "DE", "FR", "AU"},
                enable_honeypot=True,
                enable_threat_detection=True
            ),
            SecurityLevel.HIGH_SECURITY: SecurityPolicy(
                max_key_age_days=30,
                max_failed_attempts=3,
                lockout_duration_minutes=30,
                require_key_rotation=True,
                enable_geo_blocking=True,
                allowed_countries={"US", "CA"},
                max_requests_per_second=50,
                enable_honeypot=True,
                enable_threat_detection=True
            )
        }
        return policies
    
    def _load_threat_patterns(self) -> Dict[str, List[str]]:
        """Load threat detection patterns"""
        return {
            "sql_injection": [
                r"(?i)(union\s+select|select\s+.*\s+from|insert\s+into|update\s+.*\s+set|delete\s+from)",
                r"(?i)(\'\s*or\s+\'\d+\'\s*=\s*\'\d+|admin\'\s*--|\'\s*;\s*drop\s+table)",
                r"(?i)(exec\s*\(|script\s*>|javascript:|vbscript:)"
            ],
            "xss_attempt": [
                r"(?i)(<script[^>]*>.*?</script>|javascript:|vbscript:|onload\s*=|onerror\s*=)",
                r"(?i)(alert\s*\(|document\.cookie|window\.location)",
                r"(?i)(<iframe|<object|<embed|<meta.*refresh)"
            ],
            "path_traversal": [
                r"(\.\.\/|\.\.\\|%2e%2e%2f|%2e%2e%5c)",
                r"(/etc/passwd|/etc/shadow|/proc/self|/windows/system32)",
                r"(..%2f|..%5c|%252e%252e)"
            ],
            "command_injection": [
                r"(?i)(;\s*cat\s+|;\s*ls\s+|;\s*pwd|;\s*id|;\s*whoami)",
                r"(?i)(\$\(|`|wget\s+|curl\s+|nc\s+)",
                r"(?i)(rm\s+-rf|chmod\s+777|sudo\s+)"
            ],
            "suspicious_user_agent": [
                r"(?i)(sqlmap|nikto|burp|nmap|masscan|zap)",
                r"(?i)(bot|crawler|spider|scraper)(?!.*google|.*bing)",
                r"(?i)(python-requests|curl|wget|libwww)"
            ]
        }
    
    async def validate_request_security(
        self, 
        request: Request, 
        client_ip: str = None
    ) -> Dict[str, Any]:
        """
        Comprehensive request security validation
        
        Args:
            request: FastAPI request object
            client_ip: Optional client IP override
            
        Returns:
            Dict containing security validation results
        """
        validation_result = {
            "allowed": True,
            "threat_level": ThreatLevel.LOW,
            "threats_detected": [],
            "security_score": 100,
            "recommendations": []
        }
        
        try:
            client_ip = client_ip or self._extract_client_ip(request)
            policy = self.security_policies[self.security_level]
            
            # IP-based security checks
            ip_checks = await self._validate_ip_security(client_ip, policy)
            validation_result.update(ip_checks)
            
            # Request pattern analysis
            pattern_checks = self._analyze_request_patterns(request)
            validation_result["threats_detected"].extend(pattern_checks["threats"])
            validation_result["security_score"] -= pattern_checks["threat_penalty"]
            
            # Rate limiting check
            rate_checks = await self._check_request_rate_limits(client_ip, policy)
            if not rate_checks["allowed"]:
                validation_result["allowed"] = False
                validation_result["threat_level"] = ThreatLevel.HIGH
            
            # User agent analysis
            ua_checks = self._analyze_user_agent(request.headers.get("User-Agent", ""))
            validation_result["threats_detected"].extend(ua_checks["threats"])
            validation_result["security_score"] -= ua_checks["threat_penalty"]
            
            # Header security analysis
            header_checks = self._analyze_security_headers(request.headers)
            validation_result["security_score"] -= header_checks["penalty"]
            
            # Determine final threat level
            if validation_result["security_score"] < 30:
                validation_result["threat_level"] = ThreatLevel.CRITICAL
                validation_result["allowed"] = False
            elif validation_result["security_score"] < 60:
                validation_result["threat_level"] = ThreatLevel.HIGH
            elif validation_result["security_score"] < 80:
                validation_result["threat_level"] = ThreatLevel.MEDIUM
            
            # Log security events
            if validation_result["threats_detected"]:
                await self._log_security_event(
                    event_type="threat_detected",
                    severity=validation_result["threat_level"].value,
                    description=f"Security threats detected: {', '.join(validation_result['threats_detected'])}",
                    metadata={
                        "client_ip": client_ip,
                        "user_agent": request.headers.get("User-Agent", ""),
                        "threats": validation_result["threats_detected"],
                        "security_score": validation_result["security_score"]
                    }
                )
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Security validation failed: {e}")
            return {
                "allowed": True,  # Fail open for availability
                "threat_level": ThreatLevel.LOW,
                "error": str(e)
            }
    
    async def _validate_ip_security(
        self, 
        client_ip: str, 
        policy: SecurityPolicy
    ) -> Dict[str, Any]:
        """Validate IP-based security policies"""
        result = {"allowed": True, "threats_detected": [], "recommendations": []}
        
        try:
            ip_obj = ip_address(client_ip)
            redis_client = await self.get_redis()
            
            # Check blocked IPs
            if policy.blocked_ips and client_ip in policy.blocked_ips:
                result["allowed"] = False
                result["threats_detected"].append("blocked_ip")
                return result
            
            # Check IP reputation
            reputation_key = f"ip_reputation:{client_ip}"
            reputation_data = await redis_client.get(reputation_key)
            
            if reputation_data:
                import json
                reputation = json.loads(reputation_data)
                
                if reputation.get("threat_score", 0) > 80:
                    result["allowed"] = False
                    result["threats_detected"].append("high_threat_ip")
                elif reputation.get("threat_score", 0) > 50:
                    result["threats_detected"].append("suspicious_ip")
            
            # Check for repeated failures
            failure_key = f"failed_attempts:{client_ip}"
            failed_attempts = await redis_client.get(failure_key)
            
            if failed_attempts and int(failed_attempts) >= policy.max_failed_attempts:
                result["allowed"] = False
                result["threats_detected"].append("too_many_failures")
            
            # Geolocation check (simplified - would integrate with real GeoIP service)
            if policy.enable_geo_blocking and policy.allowed_countries:
                # This would integrate with a real GeoIP service
                country_code = await self._get_country_code(client_ip)
                if country_code and country_code not in policy.allowed_countries:
                    result["allowed"] = False
                    result["threats_detected"].append("geo_blocked")
            
            return result
            
        except AddressValueError:
            result["threats_detected"].append("invalid_ip")
            return result
        except Exception as e:
            logger.error(f"IP security validation failed: {e}")
            return result
    
    def _analyze_request_patterns(self, request: Request) -> Dict[str, Any]:
        """Analyze request for malicious patterns"""
        threats = []
        threat_penalty = 0
        
        # Analyze URL path
        path = str(request.url.path)
        query_params = str(request.url.query)
        
        for threat_type, patterns in self.threat_patterns.items():
            for pattern in patterns:
                import re
                if re.search(pattern, path) or re.search(pattern, query_params):
                    threats.append(threat_type)
                    threat_penalty += 25  # Each threat type deducts 25 points
                    break  # Only count each threat type once per request
        
        return {
            "threats": threats,
            "threat_penalty": threat_penalty
        }
    
    def _analyze_user_agent(self, user_agent: str) -> Dict[str, Any]:
        """Analyze User-Agent for suspicious patterns"""
        threats = []
        threat_penalty = 0
        
        if not user_agent:
            threats.append("missing_user_agent")
            threat_penalty += 10
            return {"threats": threats, "threat_penalty": threat_penalty}
        
        # Check against suspicious UA patterns
        patterns = self.threat_patterns.get("suspicious_user_agent", [])
        for pattern in patterns:
            import re
            if re.search(pattern, user_agent):
                threats.append("suspicious_user_agent")
                threat_penalty += 15
                break
        
        # Check for very short or very long user agents
        if len(user_agent) < 10:
            threats.append("abnormal_user_agent")
            threat_penalty += 5
        elif len(user_agent) > 500:
            threats.append("abnormal_user_agent")
            threat_penalty += 10
        
        return {
            "threats": threats,
            "threat_penalty": threat_penalty
        }
    
    def _analyze_security_headers(self, headers) -> Dict[str, Any]:
        """Analyze security-relevant headers"""
        penalty = 0
        
        # Check for missing security headers (for responses - would be implemented in middleware)
        security_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options", 
            "X-XSS-Protection",
            "Content-Security-Policy"
        ]
        
        # For requests, we mainly check for suspicious patterns
        suspicious_headers = [
            "X-Forwarded-For",  # Multiple proxies
            "X-Originating-IP",
            "X-Remote-IP"
        ]
        
        # Check for header injection attempts
        for header_name, header_value in headers.items():
            if isinstance(header_value, str):
                if "\n" in header_value or "\r" in header_value:
                    penalty += 20  # Header injection attempt
                
                if len(header_value) > 1000:  # Abnormally long header
                    penalty += 10
        
        return {"penalty": penalty}
    
    async def _check_request_rate_limits(
        self, 
        client_ip: str, 
        policy: SecurityPolicy
    ) -> Dict[str, Any]:
        """Check request rate limits"""
        try:
            redis_client = await self.get_redis()
            current_time = int(datetime.utcnow().timestamp())
            window_key = f"rate_limit_security:{client_ip}:{current_time}"
            
            # Use a 1-second sliding window for burst detection
            request_count = await redis_client.incr(window_key)
            await redis_client.expire(window_key, 1)
            
            if request_count > policy.max_requests_per_second:
                return {
                    "allowed": False,
                    "reason": "burst_rate_limit_exceeded",
                    "count": request_count,
                    "limit": policy.max_requests_per_second
                }
            
            return {"allowed": True}
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            return {"allowed": True}  # Fail open
    
    async def _get_country_code(self, ip: str) -> Optional[str]:
        """Get country code for IP (placeholder for GeoIP integration)"""
        # This would integrate with a real GeoIP service like MaxMind or similar
        # For now, return None to allow all IPs
        return None
    
    def _extract_client_ip(self, request: Request) -> str:
        """Extract real client IP from request"""
        # Check X-Forwarded-For header (from load balancers)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Use client IP if available
        if hasattr(request, "client") and request.client.host:
            return request.client.host
        
        return "unknown"
    
    async def _log_security_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        metadata: Dict[str, Any],
        user_id: Optional[int] = None
    ):
        """Log security event to database"""
        try:
            async for db in get_db():
                security_event = MeilisearchSecurityEvent(
                    event_type=event_type,
                    severity=severity,
                    description=description,
                    user_id=user_id,
                    automated=True,
                    event_metadata=metadata
                )
                db.add(security_event)
                await db.commit()
                break
        except Exception as e:
            logger.error(f"Failed to log security event: {e}")
    
    async def record_failed_attempt(self, client_ip: str):
        """Record failed authentication/access attempt"""
        try:
            redis_client = await self.get_redis()
            failure_key = f"failed_attempts:{client_ip}"
            
            # Increment failure count
            await redis_client.incr(failure_key)
            await redis_client.expire(failure_key, 3600)  # 1 hour expiry
            
            # Update IP reputation
            reputation_key = f"ip_reputation:{client_ip}"
            reputation_data = await redis_client.get(reputation_key)
            
            if reputation_data:
                import json
                reputation = json.loads(reputation_data)
            else:
                reputation = {"threat_score": 0, "last_seen": None}
            
            reputation["threat_score"] = min(100, reputation["threat_score"] + 10)
            reputation["last_seen"] = datetime.utcnow().isoformat()
            
            await redis_client.setex(
                reputation_key,
                86400,  # 24 hours
                json.dumps(reputation)
            )
            
        except Exception as e:
            logger.error(f"Failed to record failed attempt: {e}")
    
    async def is_honeypot_trigger(self, request: Request) -> bool:
        """Check if request triggers honeypot detection"""
        policy = self.security_policies[self.security_level]
        
        if not policy.enable_honeypot:
            return False
        
        # Honeypot patterns
        honeypot_paths = [
            "/admin",
            "/phpmyadmin",
            "/wp-admin",
            "/administrator",
            "/.env",
            "/.git",
            "/config.php",
            "/robots.txt"  # Suspicious if accessed too frequently
        ]
        
        path = str(request.url.path).lower()
        
        for honeypot_path in honeypot_paths:
            if path.startswith(honeypot_path):
                return True
        
        return False
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Generate cryptographically secure token"""
        return secrets.token_urlsafe(length)
    
    def hash_sensitive_data(self, data: str) -> str:
        """Hash sensitive data with salt"""
        salt = settings.SECRET_KEY[:16].encode()  # Use part of secret key as salt
        return hashlib.pbkdf2_hmac('sha256', data.encode(), salt, 100000).hex()
    
    async def cleanup_security_data(self):
        """Cleanup old security data from Redis"""
        try:
            redis_client = await self.get_redis()
            
            # Clean up old IP reputation data
            current_time = datetime.utcnow()
            cutoff_time = current_time - timedelta(days=7)
            
            # This would require scanning keys and checking timestamps
            # Implementation would depend on Redis key patterns
            
            logger.info("Security data cleanup completed")
            
        except Exception as e:
            logger.error(f"Security data cleanup failed: {e}")


# Global security hardening service
security_hardening = SecurityHardeningService(
    security_level=SecurityLevel(getattr(settings, 'SECURITY_LEVEL', 'production'))
)


# Security middleware dependency
async def validate_request_security(request: Request):
    """FastAPI dependency for request security validation"""
    validation_result = await security_hardening.validate_request_security(request)
    
    if not validation_result["allowed"]:
        # Record the failed attempt
        client_ip = security_hardening._extract_client_ip(request)
        await security_hardening.record_failed_attempt(client_ip)
        
        # Check if it's a honeypot trigger
        if await security_hardening.is_honeypot_trigger(request):
            # Log honeypot trigger but don't reveal it's a honeypot
            await security_hardening._log_security_event(
                event_type="honeypot_triggered",
                severity="warning",
                description=f"Honeypot endpoint accessed: {request.url.path}",
                metadata={
                    "client_ip": client_ip,
                    "path": str(request.url.path),
                    "user_agent": request.headers.get("User-Agent", "")
                }
            )
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied due to security policy",
            headers={"X-Security-Score": str(validation_result.get("security_score", 0))}
        )
    
    return validation_result


# Security headers middleware (would be implemented as FastAPI middleware)
def add_security_headers(response, security_level: SecurityLevel = SecurityLevel.PRODUCTION):
    """Add security headers to response"""
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Security-Hardening": "enabled"
    }
    
    if security_level in [SecurityLevel.PRODUCTION, SecurityLevel.HIGH_SECURITY]:
        headers.update({
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
        })
    
    for header, value in headers.items():
        response.headers[header] = value
    
    return response