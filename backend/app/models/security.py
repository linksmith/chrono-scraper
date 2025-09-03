"""
Security-related database models for enhanced admin security
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column, String, DateTime, Text, JSON, Integer
from sqlalchemy import func, Index
from enum import Enum


class SecurityEventType(str, Enum):
    """Types of security events"""
    LOGIN_ATTEMPT = "login_attempt"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    PASSWORD_CHANGE = "password_change"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    THREAT_DETECTED = "threat_detected"
    IP_BLOCKED = "ip_blocked"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    ADMIN_ACCESS = "admin_access"
    PERMISSION_ESCALATION = "permission_escalation"
    DATA_EXPORT = "data_export"
    BULK_OPERATION = "bulk_operation"


class ThreatLevel(str, Enum):
    """Threat severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MitigationAction(str, Enum):
    """Automated mitigation actions"""
    IP_BLOCK = "ip_block"
    ACCOUNT_LOCK = "account_lock"
    RATE_LIMIT_INCREASE = "rate_limit_increase"
    ALERT_SENT = "alert_sent"
    SESSION_TERMINATE = "session_terminate"
    ACCESS_DENY = "access_deny"


class SecurityEventBase(SQLModel):
    """Base model for security events"""
    event_type: SecurityEventType = Field(sa_column=Column(String(50), index=True))
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    session_id: Optional[str] = Field(default=None, sa_column=Column(String(255), index=True))
    ip_address: str = Field(sa_column=Column(String(45), index=True))
    user_agent: Optional[str] = Field(default=None, sa_column=Column(String(512)))
    
    # Event details
    success: bool = Field(default=True, index=True)
    error_code: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Request context
    request_method: Optional[str] = Field(default=None, sa_column=Column(String(10)))
    request_path: Optional[str] = Field(default=None, sa_column=Column(String(2048)))
    request_headers: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Additional context
    details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Geolocation
    country_code: Optional[str] = Field(default=None, sa_column=Column(String(2)))
    city: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    
    # Risk assessment
    risk_score: int = Field(default=0, sa_column=Column(Integer, index=True))
    threat_indicators: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))


class SecurityEvent(SecurityEventBase, table=True):
    """Security events tracking table"""
    __tablename__ = "security_events"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), index=True)
    )
    
    # Database indexes for performance
    __table_args__ = (
        Index('ix_security_events_type_time', 'event_type', 'created_at'),
        Index('ix_security_events_user_time', 'user_id', 'created_at'),
        Index('ix_security_events_ip_time', 'ip_address', 'created_at'),
        Index('ix_security_events_success_time', 'success', 'created_at'),
        Index('ix_security_events_risk_time', 'risk_score', 'created_at'),
    )


class IPBlocklistBase(SQLModel):
    """Base model for IP blocklist entries"""
    ip_address: str = Field(sa_column=Column(String(45), index=True))
    ip_range: Optional[str] = Field(default=None, sa_column=Column(String(50)))  # CIDR notation
    block_type: str = Field(sa_column=Column(String(20), index=True))  # manual, automatic, temporary
    
    # Block details
    reason: str = Field(sa_column=Column(String(255)))
    blocked_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    threat_level: ThreatLevel = Field(default=ThreatLevel.MEDIUM, sa_column=Column(String(20), index=True))
    
    # Validity period
    expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), index=True))
    is_active: bool = Field(default=True, index=True)
    
    # Context
    first_detected: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    incident_count: int = Field(default=1)
    last_activity: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Additional info
    country_code: Optional[str] = Field(default=None, sa_column=Column(String(2)))
    organization: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))


class IPBlocklist(IPBlocklistBase, table=True):
    """IP blocklist table"""
    __tablename__ = "ip_blocklist"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), index=True)
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )
    
    __table_args__ = (
        Index('ix_ip_blocklist_ip_active', 'ip_address', 'is_active'),
        Index('ix_ip_blocklist_expires', 'expires_at'),
        Index('ix_ip_blocklist_threat_level', 'threat_level', 'is_active'),
    )


class TwoFactorAuthBase(SQLModel):
    """Base model for Two-Factor Authentication settings"""
    user_id: int = Field(foreign_key="users.id", index=True)
    
    # TOTP settings
    secret_key: Optional[str] = Field(default=None, sa_column=Column(String(255)))  # Encrypted
    is_enabled: bool = Field(default=False, index=True)
    backup_codes: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))  # Hashed codes
    
    # Usage tracking
    last_used: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    verification_attempts: int = Field(default=0)
    last_failed_attempt: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Email/SMS 2FA
    email_enabled: bool = Field(default=False)
    sms_enabled: bool = Field(default=False)
    phone_number: Optional[str] = Field(default=None, sa_column=Column(String(20)))  # Encrypted
    
    # Recovery
    recovery_email: Optional[str] = Field(default=None, sa_column=Column(String(255)))  # Encrypted
    emergency_codes_generated: int = Field(default=0)
    
    # Temporary codes for email/SMS
    temp_code: Optional[str] = Field(default=None, sa_column=Column(String(10)))  # Hashed
    temp_code_expires: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    temp_code_attempts: int = Field(default=0)


class TwoFactorAuth(TwoFactorAuthBase, table=True):
    """Two-Factor Authentication settings table"""
    __tablename__ = "two_factor_auth"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )
    
    __table_args__ = (
        Index('ix_2fa_user_enabled', 'user_id', 'is_enabled'),
    )


class SecurityIncidentBase(SQLModel):
    """Base model for security incidents"""
    incident_type: str = Field(sa_column=Column(String(50), index=True))
    threat_level: ThreatLevel = Field(sa_column=Column(String(20), index=True))
    
    # Incident details
    title: str = Field(sa_column=Column(String(255)))
    description: str = Field(sa_column=Column(Text))
    
    # Source information
    source_ip: Optional[str] = Field(default=None, sa_column=Column(String(45), index=True))
    affected_user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    reported_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    
    # Status
    status: str = Field(default="open", sa_column=Column(String(20), index=True))  # open, investigating, resolved, false_positive
    priority: str = Field(default="medium", sa_column=Column(String(20), index=True))  # low, medium, high, critical
    
    # Timing
    first_detected: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True)
    )
    last_activity: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    resolved_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Impact assessment
    affected_systems: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    data_compromised: bool = Field(default=False, index=True)
    estimated_impact: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Response
    mitigation_actions: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    automated_response: bool = Field(default=False, index=True)
    
    # Evidence and context
    evidence: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    related_events: Optional[List[int]] = Field(default=None, sa_column=Column(JSON))  # Related SecurityEvent IDs
    
    # External references
    cve_references: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    external_ticket_id: Optional[str] = Field(default=None, sa_column=Column(String(100)))


class SecurityIncident(SecurityIncidentBase, table=True):
    """Security incidents table"""
    __tablename__ = "security_incidents"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), index=True)
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )
    
    __table_args__ = (
        Index('ix_incidents_type_status', 'incident_type', 'status'),
        Index('ix_incidents_threat_priority', 'threat_level', 'priority'),
        Index('ix_incidents_detection_time', 'first_detected'),
        Index('ix_incidents_affected_user', 'affected_user_id', 'status'),
    )


class SecurityConfigBase(SQLModel):
    """Base model for security configuration"""
    config_key: str = Field(sa_column=Column(String(100), index=True))
    config_value: str = Field(sa_column=Column(Text))
    config_type: str = Field(sa_column=Column(String(20)))  # string, integer, boolean, json, encrypted
    
    # Metadata
    category: str = Field(sa_column=Column(String(50), index=True))  # ip_security, rate_limiting, 2fa, etc.
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_sensitive: bool = Field(default=False, index=True)  # Contains sensitive data
    
    # Change tracking
    modified_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    previous_value: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Validation
    validation_regex: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    allowed_values: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    min_value: Optional[float] = Field(default=None)
    max_value: Optional[float] = Field(default=None)
    
    # Environment
    environment: str = Field(default="all", sa_column=Column(String(20), index=True))  # all, development, staging, production


class SecurityConfig(SecurityConfigBase, table=True):
    """Security configuration table"""
    __tablename__ = "security_config"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )
    
    __table_args__ = (
        Index('ix_security_config_key_env', 'config_key', 'environment'),
        Index('ix_security_config_category', 'category'),
    )


class SessionSecurityBase(SQLModel):
    """Base model for session security tracking"""
    session_id: str = Field(sa_column=Column(String(255), index=True))
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    
    # Session details
    ip_address: str = Field(sa_column=Column(String(45), index=True))
    user_agent: Optional[str] = Field(default=None, sa_column=Column(String(512)))
    device_fingerprint: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    
    # Security flags
    is_suspicious: bool = Field(default=False, index=True)
    is_admin_session: bool = Field(default=False, index=True)
    mfa_verified: bool = Field(default=False, index=True)
    
    # Timing
    login_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True)
    )
    last_activity: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), index=True)
    )
    logout_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Activity tracking
    request_count: int = Field(default=0)
    failed_request_count: int = Field(default=0)
    privilege_escalation_attempts: int = Field(default=0)
    
    # Geolocation
    country_code: Optional[str] = Field(default=None, sa_column=Column(String(2)))
    city: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    timezone_offset: Optional[int] = Field(default=None)
    
    # Risk assessment
    risk_score: int = Field(default=0, sa_column=Column(Integer, index=True))
    risk_factors: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    
    # Termination info
    termination_reason: Optional[str] = Field(default=None, sa_column=Column(String(50)))  # timeout, logout, security, admin
    forced_logout: bool = Field(default=False, index=True)


class SessionSecurity(SessionSecurityBase, table=True):
    """Session security tracking table"""
    __tablename__ = "session_security"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )
    
    __table_args__ = (
        Index('ix_session_security_user_time', 'user_id', 'login_at'),
        Index('ix_session_security_ip_time', 'ip_address', 'login_at'),
        Index('ix_session_security_suspicious', 'is_suspicious', 'is_admin_session'),
        Index('ix_session_security_risk', 'risk_score', 'login_at'),
    )


class ThreatIntelligenceBase(SQLModel):
    """Base model for threat intelligence data"""
    indicator_type: str = Field(sa_column=Column(String(20), index=True))  # ip, domain, hash, url, email
    indicator_value: str = Field(sa_column=Column(String(500), index=True))
    
    # Threat classification
    threat_type: str = Field(sa_column=Column(String(50), index=True))
    malware_family: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    confidence: int = Field(sa_column=Column(Integer, index=True))  # 0-100
    
    # Source information
    source: str = Field(sa_column=Column(String(100), index=True))
    source_reliability: str = Field(sa_column=Column(String(20)))  # A, B, C, D, E, F
    
    # Temporal information
    first_seen: datetime = Field(sa_column=Column(DateTime(timezone=True), index=True))
    last_seen: datetime = Field(sa_column=Column(DateTime(timezone=True), index=True))
    expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), index=True))
    
    # Context
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    tags: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    kill_chain_phases: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    
    # STIX/TAXII integration
    stix_id: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    external_references: Optional[List[Dict[str, str]]] = Field(default=None, sa_column=Column(JSON))
    
    # Status
    is_active: bool = Field(default=True, index=True)
    false_positive: bool = Field(default=False, index=True)
    
    # Usage tracking
    hit_count: int = Field(default=0)
    last_hit: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class ThreatIntelligence(ThreatIntelligenceBase, table=True):
    """Threat intelligence data table"""
    __tablename__ = "threat_intelligence"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )
    
    __table_args__ = (
        Index('ix_threat_intel_indicator', 'indicator_type', 'indicator_value'),
        Index('ix_threat_intel_threat_type', 'threat_type', 'is_active'),
        Index('ix_threat_intel_confidence', 'confidence', 'is_active'),
        Index('ix_threat_intel_temporal', 'first_seen', 'last_seen'),
    )


# Data models for API responses
class SecurityEventRead(SecurityEventBase):
    """Schema for reading security events"""
    id: int
    created_at: datetime


class IPBlocklistRead(IPBlocklistBase):
    """Schema for reading IP blocklist entries"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime]


class SecurityIncidentRead(SecurityIncidentBase):
    """Schema for reading security incidents"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime]


class SecurityMetrics(SQLModel):
    """Security metrics summary"""
    total_events: int
    failed_logins: int
    blocked_ips: int
    active_threats: int
    incidents_open: int
    incidents_resolved: int
    high_risk_sessions: int
    mfa_adoption_rate: float
    average_risk_score: float
    events_by_type: Dict[str, int]
    top_threat_ips: List[Dict[str, Any]]
    recent_incidents: List[Dict[str, Any]]