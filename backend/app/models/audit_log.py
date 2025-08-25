"""
Enterprise audit logging model for tracking admin operations and user activities with advanced security features
"""
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List
from sqlmodel import SQLModel, Field, Column, String, DateTime, Text, JSON, Integer, Boolean
from sqlalchemy import func, Index
from enum import Enum
import json
import hashlib
import hmac
from uuid import uuid4


class AuditCategory(str, Enum):
    """Audit log categories for better organization and compliance"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    USER_MANAGEMENT = "user_management"
    CONTENT_MANAGEMENT = "content_management"
    SYSTEM_CONFIG = "system_config"
    SECURITY_EVENT = "security_event"
    BULK_OPERATION = "bulk_operation"
    API_ACCESS = "api_access"
    DATA_EXPORT = "data_export"
    COMPLIANCE = "compliance"


class SeverityLevel(str, Enum):
    """Severity levels for audit events"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditLogBase(SQLModel):
    """Enhanced base audit log model with advanced security fields"""
    # Core identification
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    admin_user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    session_id: Optional[str] = Field(default=None, sa_column=Column(String(255), index=True))
    request_id: Optional[str] = Field(default=None, sa_column=Column(String(100), index=True))
    
    # Action details
    action: str = Field(sa_column=Column(String(100), index=True))
    resource_type: str = Field(sa_column=Column(String(50), index=True))
    resource_id: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    category: AuditCategory = Field(sa_column=Column(String(50), index=True))
    severity: SeverityLevel = Field(default=SeverityLevel.MEDIUM, sa_column=Column(String(20), index=True))
    
    # Request context
    ip_address: Optional[str] = Field(default=None, sa_column=Column(String(45), index=True))
    user_agent: Optional[str] = Field(default=None, sa_column=Column(String(512)))
    request_method: Optional[str] = Field(default=None, sa_column=Column(String(10)))
    request_url: Optional[str] = Field(default=None, sa_column=Column(String(2048)))
    request_headers: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    request_body: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Response context
    response_status: Optional[int] = Field(default=None, sa_column=Column(Integer))
    response_headers: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    response_body: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Operation details
    success: bool = Field(default=True, index=True)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_code: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    affected_count: int = Field(default=0)
    
    # Change tracking
    before_values: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    after_values: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    changed_fields: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    
    # Additional context
    details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    tags: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    
    # Security and compliance
    compliance_flags: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    sensitive_data_accessed: bool = Field(default=False, index=True)
    gdpr_relevant: bool = Field(default=False, index=True)
    sox_relevant: bool = Field(default=False, index=True)
    hipaa_relevant: bool = Field(default=False, index=True)
    
    # Integrity and security
    checksum: Optional[str] = Field(default=None, sa_column=Column(String(64)))
    signature: Optional[str] = Field(default=None, sa_column=Column(String(512)))
    encrypted: bool = Field(default=False)
    
    # Performance metrics
    processing_time_ms: Optional[int] = Field(default=None)
    database_queries: Optional[int] = Field(default=None)
    memory_usage_mb: Optional[float] = Field(default=None)
    
    # Geolocation and device info
    country_code: Optional[str] = Field(default=None, sa_column=Column(String(2)))
    city: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    device_type: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    browser_info: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    
    
class AuditLog(AuditLogBase, table=True):
    """Enhanced audit log model for database with integrity features"""
    __tablename__ = "audit_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Temporal fields
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), index=True)
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )
    
    # Retention and archival
    retention_until: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    archived: bool = Field(default=False, index=True)
    archived_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Database indexes for performance
    __table_args__ = (
        Index('ix_audit_logs_user_created', 'user_id', 'created_at'),
        Index('ix_audit_logs_admin_created', 'admin_user_id', 'created_at'),
        Index('ix_audit_logs_category_severity', 'category', 'severity'),
        Index('ix_audit_logs_ip_created', 'ip_address', 'created_at'),
        Index('ix_audit_logs_action_resource', 'action', 'resource_type'),
        Index('ix_audit_logs_session_created', 'session_id', 'created_at'),
        Index('ix_audit_logs_compliance', 'gdpr_relevant', 'sox_relevant', 'hipaa_relevant'),
        Index('ix_audit_logs_sensitive_data', 'sensitive_data_accessed', 'created_at'),
        Index('ix_audit_logs_retention', 'retention_until', 'archived'),
    )
    
    class Config:
        arbitrary_types_allowed = True


class AuditLogCreate(AuditLogBase):
    """Schema for creating audit log entries"""
    pass


class AuditLogRead(AuditLogBase):
    """Schema for reading audit log entries"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime]
    retention_until: Optional[datetime]
    archived: bool
    archived_at: Optional[datetime]


class AuditLogFilter(SQLModel):
    """Advanced filtering schema for audit log queries"""
    user_id: Optional[int] = None
    admin_user_id: Optional[int] = None
    session_id: Optional[str] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    category: Optional[AuditCategory] = None
    severity: Optional[SeverityLevel] = None
    ip_address: Optional[str] = None
    success: Optional[bool] = None
    
    # Date range filters
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    
    # Compliance filters
    gdpr_relevant: Optional[bool] = None
    sox_relevant: Optional[bool] = None
    hipaa_relevant: Optional[bool] = None
    sensitive_data_accessed: Optional[bool] = None
    
    # Text search
    search_query: Optional[str] = None
    
    # Pagination
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    
    # Sorting
    sort_by: Optional[str] = Field(default="created_at")
    sort_order: Optional[str] = Field(default="desc")


class AuditLogAnalytics(SQLModel):
    """Analytics and statistics for audit logs"""
    total_events: int
    events_by_category: Dict[str, int]
    events_by_severity: Dict[str, int]
    events_by_action: Dict[str, int]
    top_users: List[Dict[str, Any]]
    top_ip_addresses: List[Dict[str, Any]]
    failed_operations: int
    success_rate: float
    compliance_events: Dict[str, int]
    security_events: int
    anomalous_events: List[Dict[str, Any]]


def create_audit_log(
    action: str,
    resource_type: str,
    category: AuditCategory,
    admin_user_id: Optional[int] = None,
    user_id: Optional[int] = None,
    resource_id: Optional[str] = None,
    severity: SeverityLevel = SeverityLevel.MEDIUM,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    request_method: Optional[str] = None,
    request_url: Optional[str] = None,
    request_headers: Optional[Dict[str, Any]] = None,
    request_body: Optional[Dict[str, Any]] = None,
    response_status: Optional[int] = None,
    response_headers: Optional[Dict[str, Any]] = None,
    response_body: Optional[Dict[str, Any]] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    error_code: Optional[str] = None,
    affected_count: int = 0,
    before_values: Optional[Dict[str, Any]] = None,
    after_values: Optional[Dict[str, Any]] = None,
    changed_fields: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    compliance_flags: Optional[List[str]] = None,
    sensitive_data_accessed: bool = False,
    gdpr_relevant: bool = False,
    sox_relevant: bool = False,
    hipaa_relevant: bool = False,
    processing_time_ms: Optional[int] = None,
    database_queries: Optional[int] = None,
    memory_usage_mb: Optional[float] = None,
    country_code: Optional[str] = None,
    city: Optional[str] = None,
    device_type: Optional[str] = None,
    browser_info: Optional[str] = None
) -> AuditLogCreate:
    """Enhanced helper function to create comprehensive audit log entries"""
    return AuditLogCreate(
        user_id=user_id,
        admin_user_id=admin_user_id,
        session_id=session_id,
        request_id=request_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        category=category,
        severity=severity,
        ip_address=ip_address,
        user_agent=user_agent,
        request_method=request_method,
        request_url=request_url,
        request_headers=request_headers,
        request_body=request_body,
        response_status=response_status,
        response_headers=response_headers,
        response_body=response_body,
        success=success,
        error_message=error_message,
        error_code=error_code,
        affected_count=affected_count,
        before_values=before_values,
        after_values=after_values,
        changed_fields=changed_fields,
        details=details or {},
        tags=tags,
        compliance_flags=compliance_flags,
        sensitive_data_accessed=sensitive_data_accessed,
        gdpr_relevant=gdpr_relevant,
        sox_relevant=sox_relevant,
        hipaa_relevant=hipaa_relevant,
        processing_time_ms=processing_time_ms,
        database_queries=database_queries,
        memory_usage_mb=memory_usage_mb,
        country_code=country_code,
        city=city,
        device_type=device_type,
        browser_info=browser_info
    )


# Enhanced audit actions for comprehensive tracking
class AuditActions:
    """Constants for common audit actions with security focus"""
    # Authentication and session management
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_LOGIN_FAILED = "user_login_failed"
    USER_PASSWORD_RESET = "user_password_reset"
    USER_PASSWORD_CHANGE = "user_password_change"
    USER_EMAIL_VERIFY = "user_email_verify"
    USER_ACCOUNT_LOCKED = "user_account_locked"
    USER_ACCOUNT_UNLOCKED = "user_account_unlocked"
    USER_MFA_ENABLED = "user_mfa_enabled"
    USER_MFA_DISABLED = "user_mfa_disabled"
    USER_SESSION_EXPIRED = "user_session_expired"
    USER_SESSION_TERMINATED = "user_session_terminated"
    
    # User management operations
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    USER_DELETE = "user_delete"
    USER_APPROVE = "user_approve"
    USER_DENY = "user_deny"
    USER_ACTIVATE = "user_activate"
    USER_DEACTIVATE = "user_deactivate"
    USER_ROLE_ASSIGN = "user_role_assign"
    USER_ROLE_REMOVE = "user_role_remove"
    USER_PERMISSION_GRANT = "user_permission_grant"
    USER_PERMISSION_REVOKE = "user_permission_revoke"
    USER_PROFILE_VIEW = "user_profile_view"
    USER_PROFILE_EXPORT = "user_profile_export"
    
    # Bulk operations
    BULK_USER_APPROVE = "bulk_user_approve"
    BULK_USER_DENY = "bulk_user_deny"
    BULK_USER_ACTIVATE = "bulk_user_activate"
    BULK_USER_DEACTIVATE = "bulk_user_deactivate"
    BULK_USER_DELETE = "bulk_user_delete"
    BULK_USER_ROLE_ASSIGN = "bulk_user_role_assign"
    BULK_EMAIL_VERIFY = "bulk_email_verify"
    BULK_EMAIL_SEND = "bulk_email_send"
    BULK_INVITATION_CREATE = "bulk_invitation_create"
    BULK_DATA_EXPORT = "bulk_data_export"
    BULK_DATA_IMPORT = "bulk_data_import"
    
    # Content management
    PAGE_CREATE = "page_create"
    PAGE_UPDATE = "page_update"
    PAGE_DELETE = "page_delete"
    PAGE_VIEW = "page_view"
    PAGE_EXPORT = "page_export"
    PAGE_SHARE = "page_share"
    PAGE_UNSHARE = "page_unshare"
    
    PROJECT_CREATE = "project_create"
    PROJECT_UPDATE = "project_update"
    PROJECT_DELETE = "project_delete"
    PROJECT_SHARE = "project_share"
    PROJECT_EXPORT = "project_export"
    
    ENTITY_CREATE = "entity_create"
    ENTITY_UPDATE = "entity_update"
    ENTITY_DELETE = "entity_delete"
    ENTITY_LINK = "entity_link"
    ENTITY_UNLINK = "entity_unlink"
    
    # System configuration
    SYSTEM_CONFIG_UPDATE = "system_config_update"
    SYSTEM_CONFIG_VIEW = "system_config_view"
    SYSTEM_MAINTENANCE = "system_maintenance"
    SYSTEM_BACKUP = "system_backup"
    SYSTEM_RESTORE = "system_restore"
    SYSTEM_SERVICE_START = "system_service_start"
    SYSTEM_SERVICE_STOP = "system_service_stop"
    SYSTEM_SERVICE_RESTART = "system_service_restart"
    
    # API and programmatic access
    API_KEY_CREATE = "api_key_create"
    API_KEY_DELETE = "api_key_delete"
    API_KEY_ROTATE = "api_key_rotate"
    API_REQUEST = "api_request"
    API_RATE_LIMIT_EXCEEDED = "api_rate_limit_exceeded"
    
    # Security events
    SECURITY_SCAN = "security_scan"
    SECURITY_VULNERABILITY_DETECTED = "security_vulnerability_detected"
    SECURITY_POLICY_VIOLATION = "security_policy_violation"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    BREACH_ATTEMPT = "breach_attempt"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    
    # Data operations and compliance
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"
    DATA_ANONYMIZATION = "data_anonymization"
    DATA_DELETION = "data_deletion"
    GDPR_REQUEST = "gdpr_request"
    GDPR_DATA_EXPORT = "gdpr_data_export"
    GDPR_DATA_DELETION = "gdpr_data_deletion"
    COMPLIANCE_AUDIT = "compliance_audit"
    RETENTION_POLICY_APPLIED = "retention_policy_applied"
    
    # Administrative operations
    ADMIN_LOGIN = "admin_login"
    ADMIN_LOGOUT = "admin_logout"
    ADMIN_DASHBOARD_VIEW = "admin_dashboard_view"
    ADMIN_REPORT_GENERATE = "admin_report_generate"
    ADMIN_ALERT_CREATE = "admin_alert_create"
    ADMIN_ALERT_RESOLVE = "admin_alert_resolve"


class ResourceTypes:
    """Constants for resource types with comprehensive coverage"""
    # Core entities
    USER = "user"
    PROJECT = "project"
    DOMAIN = "domain"
    PAGE = "page"
    ENTITY = "entity"
    
    # System resources
    SYSTEM = "system"
    CONFIGURATION = "configuration"
    DATABASE = "database"
    SERVICE = "service"
    API_KEY = "api_key"
    
    # Bulk operations
    BULK_OPERATION = "bulk_operation"
    BATCH_JOB = "batch_job"
    
    # Security and compliance
    SECURITY_POLICY = "security_policy"
    AUDIT_LOG = "audit_log"
    COMPLIANCE_REPORT = "compliance_report"
    
    # Data and content
    CONTENT = "content"
    ATTACHMENT = "attachment"
    EXPORT = "export"
    BACKUP = "backup"
    
    # Communication
    EMAIL = "email"
    NOTIFICATION = "notification"
    ALERT = "alert"
    
    # Integration
    WEBHOOK = "webhook"
    API_ENDPOINT = "api_endpoint"
    EXTERNAL_SERVICE = "external_service"