"""
Shared types and constants for the security module
This module contains types that need to be shared across security modules
to prevent circular import issues.
"""
from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass
from datetime import datetime


class ThreatType(str, Enum):
    """Types of security threats"""
    BRUTE_FORCE = "brute_force"
    SQL_INJECTION = "sql_injection"
    XSS_ATTEMPT = "xss_attempt"
    DDOS = "ddos"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    RECONNAISSANCE = "reconnaissance"
    MALICIOUS_BOT = "malicious_bot"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    ACCOUNT_TAKEOVER = "account_takeover"
    API_ABUSE = "api_abuse"


class ThreatSeverity(str, Enum):
    """Threat severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RateLimitAlgorithm(str, Enum):
    """Rate limiting algorithms"""
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"
    ADAPTIVE = "adaptive"


class ThreatLevel(str, Enum):
    """Threat levels for adaptive rate limiting"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ThreatEvent:
    """Represents a detected threat event"""
    threat_type: ThreatType
    severity: ThreatSeverity
    source_ip: str
    user_id: int | None
    timestamp: datetime
    details: Dict[str, Any]
    confidence_score: float
    request_data: Dict[str, Any]
    mitigation_applied: bool = False
    false_positive: bool = False


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    requests: int
    window: int  # seconds
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW
    burst_multiplier: float = 1.5  # Allow burst up to 1.5x normal rate
    adaptive: bool = False
    threat_reduction_factor: Dict[ThreatLevel, float] = None
    
    def __post_init__(self):
        if self.threat_reduction_factor is None:
            self.threat_reduction_factor = {
                ThreatLevel.LOW: 1.0,
                ThreatLevel.MEDIUM: 0.7,
                ThreatLevel.HIGH: 0.3,
                ThreatLevel.CRITICAL: 0.1
            }