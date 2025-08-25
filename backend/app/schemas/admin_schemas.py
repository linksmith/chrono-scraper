"""
Comprehensive admin API schemas for all admin operations
"""
from typing import Any, List, Optional, Dict, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator
from app.models.bulk_operations import BulkOperationType, BulkOperationStatus, ExportFormat


# ===== COMMON SCHEMAS =====

class AdminOperationResult(BaseModel):
    """Base result schema for admin operations"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    affected_count: Optional[int] = None
    operation_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginatedResponse(BaseModel):
    """Base paginated response schema"""
    items: List[Dict[str, Any]]
    total: int
    page: int
    per_page: int
    pages: int
    has_next: bool
    has_prev: bool


# ===== USER MANAGEMENT SCHEMAS =====

class AdminUserListParams(BaseModel):
    """Parameters for user list endpoint"""
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)
    search: Optional[str] = Field(None, max_length=100)
    approval_status: Optional[str] = Field(None)
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    is_superuser: Optional[bool] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    last_login_after: Optional[datetime] = None
    sort_by: str = Field("created_at", pattern="^(created_at|last_login|email|full_name)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


class AdminUserRead(BaseModel):
    """Admin user read schema with extended fields"""
    id: int
    email: str
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    is_superuser: bool
    approval_status: str
    created_at: Optional[datetime]
    last_login: Optional[datetime]
    updated_at: Optional[datetime]
    
    # Extended admin fields
    projects_count: int = 0
    pages_count: int = 0
    login_count: int = 0
    last_ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Research fields
    research_interests: Optional[str] = None
    research_purpose: Optional[str] = None
    expected_usage: Optional[str] = None
    
    # Admin metadata
    approved_by_id: Optional[int] = None
    approved_at: Optional[datetime] = None


class AdminUserCreate(BaseModel):
    """Admin user creation schema"""
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    full_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=100)
    is_active: bool = True
    is_verified: bool = False
    is_superuser: bool = False
    approval_status: str = Field("approved", pattern="^(pending|approved|denied)$")
    
    # Research fields
    research_interests: str = Field("Admin created", max_length=500)
    research_purpose: str = Field("Administrative", max_length=500)
    expected_usage: str = Field("Standard usage", max_length=500)
    
    # Send notification
    send_welcome_email: bool = True


class AdminUserUpdate(BaseModel):
    """Admin user update schema"""
    full_name: Optional[str] = Field(None, min_length=1, max_length=100)
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    is_superuser: Optional[bool] = None
    approval_status: Optional[str] = Field(None, pattern="^(pending|approved|denied)$")
    
    # Research fields
    research_interests: Optional[str] = Field(None, max_length=500)
    research_purpose: Optional[str] = Field(None, max_length=500)
    expected_usage: Optional[str] = Field(None, max_length=500)


# ===== SESSION MANAGEMENT SCHEMAS =====

class AdminSessionRead(BaseModel):
    """Admin session read schema"""
    session_id: str
    user_id: int
    user_email: str
    user_full_name: Optional[str]
    created_at: datetime
    last_activity: datetime
    ip_address: Optional[str]
    user_agent: Optional[str]
    is_active: bool
    expires_at: Optional[datetime]


class AdminSessionListParams(BaseModel):
    """Parameters for session list endpoint"""
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=200)
    user_id: Optional[int] = None
    active_only: bool = True
    ip_address: Optional[str] = None
    created_after: Optional[datetime] = None
    sort_by: str = Field("last_activity", pattern="^(created_at|last_activity)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


class AdminBulkSessionRevoke(BaseModel):
    """Bulk session revoke schema"""
    session_ids: Optional[List[str]] = None
    user_ids: Optional[List[int]] = None
    revoke_all_except_current: bool = False
    reason: Optional[str] = Field(None, max_length=200)


# ===== CONTENT MANAGEMENT SCHEMAS =====

class AdminPageListParams(BaseModel):
    """Parameters for page list endpoint"""
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=200)
    search: Optional[str] = Field(None, max_length=200)
    domain: Optional[str] = Field(None, max_length=100)
    user_id: Optional[int] = None
    project_id: Optional[int] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    min_content_length: Optional[int] = None
    max_content_length: Optional[int] = None
    has_errors: Optional[bool] = None
    sort_by: str = Field("created_at", pattern="^(created_at|updated_at|title|domain)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


class AdminPageRead(BaseModel):
    """Admin page read schema"""
    id: int
    url: str
    title: Optional[str]
    domain: str
    content_length: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    # Relations
    user_id: int
    user_email: str
    project_id: int
    project_name: str
    
    # Content metadata
    language: Optional[str]
    has_errors: bool
    extraction_method: Optional[str]
    status: Optional[str]


class AdminPageUpdate(BaseModel):
    """Admin page update schema"""
    title: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, pattern="^(active|archived|flagged|deleted)$")
    notes: Optional[str] = Field(None, max_length=1000)


class AdminEntityListParams(BaseModel):
    """Parameters for entity list endpoint"""
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=200)
    search: Optional[str] = Field(None, max_length=200)
    entity_type: Optional[str] = None
    confidence_min: Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence_max: Optional[float] = Field(None, ge=0.0, le=1.0)
    user_id: Optional[int] = None
    created_after: Optional[datetime] = None
    sort_by: str = Field("created_at", pattern="^(created_at|name|confidence|entity_type)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


# ===== SYSTEM MONITORING SCHEMAS =====

class AdminSystemHealth(BaseModel):
    """System health response schema"""
    status: str = Field(pattern="^(healthy|degraded|unhealthy)$")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Service status
    services: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # System metrics
    system_metrics: Dict[str, Any] = Field(default_factory=dict)
    
    # Database metrics
    database_metrics: Dict[str, Any] = Field(default_factory=dict)
    
    # Queue metrics
    queue_metrics: Dict[str, Any] = Field(default_factory=dict)


class AdminCeleryStatus(BaseModel):
    """Celery status response schema"""
    status: str
    active_tasks: List[Dict[str, Any]]
    scheduled_tasks: List[Dict[str, Any]]
    failed_tasks: List[Dict[str, Any]]
    workers: List[Dict[str, Any]]
    queues: Dict[str, Any]
    stats: Dict[str, Any]


class AdminServiceStatus(BaseModel):
    """Service status schema"""
    service_name: str
    status: str = Field(pattern="^(online|offline|degraded|unknown)$")
    response_time_ms: Optional[float] = None
    last_check: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


# ===== CONFIGURATION SCHEMAS =====

class AdminSettingsRead(BaseModel):
    """Admin settings read schema"""
    id: int
    users_open_registration: bool
    allow_invitation_tokens: bool
    max_projects_per_user: int
    max_pages_per_project: int
    default_scraping_limits: Dict[str, Any]
    email_settings: Dict[str, Any]
    security_settings: Dict[str, Any]
    
    created_at: datetime
    updated_at: Optional[datetime]
    updated_by_id: Optional[int]


class AdminSettingsUpdate(BaseModel):
    """Admin settings update schema"""
    users_open_registration: Optional[bool] = None
    allow_invitation_tokens: Optional[bool] = None
    max_projects_per_user: Optional[int] = Field(None, ge=1, le=1000)
    max_pages_per_project: Optional[int] = Field(None, ge=1, le=100000)
    
    # Scraping limits
    default_scraping_limits: Optional[Dict[str, Any]] = None
    
    # Email settings
    email_settings: Optional[Dict[str, Any]] = None
    
    # Security settings
    security_settings: Optional[Dict[str, Any]] = None


class AdminConfigRead(BaseModel):
    """System configuration read schema"""
    environment: str
    version: str
    features: Dict[str, bool]
    limits: Dict[str, Any]
    integrations: Dict[str, Any]
    security: Dict[str, Any]


# ===== BACKUP AND RECOVERY SCHEMAS =====

class AdminBackupCreate(BaseModel):
    """Backup creation schema"""
    backup_type: str = Field("full", pattern="^(full|incremental|database|files)$")
    include_files: bool = True
    include_database: bool = True
    include_configs: bool = True
    description: Optional[str] = Field(None, max_length=200)
    encryption_enabled: bool = True


class AdminBackupRead(BaseModel):
    """Backup read schema"""
    id: str
    backup_type: str
    status: str = Field(pattern="^(pending|running|completed|failed|expired)$")
    file_path: Optional[str]
    file_size: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]
    expires_at: Optional[datetime]
    description: Optional[str]
    created_by_id: int
    encryption_enabled: bool
    
    # Metadata
    backup_metadata: Dict[str, Any] = Field(default_factory=dict)


class AdminBackupRestore(BaseModel):
    """Backup restore schema"""
    backup_id: str
    restore_database: bool = True
    restore_files: bool = True
    restore_configs: bool = True
    force_restore: bool = False  # Overwrite existing data
    restore_point_name: Optional[str] = Field(None, max_length=100)


# ===== ANALYTICS AND REPORTING SCHEMAS =====

class AdminAnalyticsParams(BaseModel):
    """Parameters for analytics endpoints"""
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    granularity: str = Field("day", pattern="^(hour|day|week|month)$")
    metrics: List[str] = Field(default_factory=lambda: ["users", "projects", "pages"])
    group_by: Optional[List[str]] = None


class AdminAnalyticsResponse(BaseModel):
    """Analytics response schema"""
    summary: Dict[str, Any]
    time_series: List[Dict[str, Any]]
    breakdowns: Dict[str, Any]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    parameters: AdminAnalyticsParams


# ===== AUDIT AND LOGGING SCHEMAS =====

class AdminAuditLogRead(BaseModel):
    """Audit log read schema"""
    id: int
    user_id: Optional[int]
    admin_user_id: int
    action: str
    resource_type: str
    resource_id: Optional[str]
    details: Dict[str, Any]
    ip_address: Optional[str]
    user_agent: Optional[str]
    success: bool
    error_message: Optional[str]
    affected_count: Optional[int]
    created_at: datetime


class AdminAuditLogParams(BaseModel):
    """Parameters for audit log endpoints"""
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=200)
    action: Optional[str] = None
    resource_type: Optional[str] = None
    admin_user_id: Optional[int] = None
    user_id: Optional[int] = None
    success: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    sort_by: str = Field("created_at", pattern="^(created_at|action|resource_type)$")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


# ===== BULK OPERATIONS SCHEMAS =====

class AdminBulkOperation(BaseModel):
    """Extended bulk operation schema"""
    operation_type: BulkOperationType
    target_type: str = Field(pattern="^(users|pages|entities|sessions)$")
    target_ids: List[Union[int, str]] = Field(..., min_items=1, max_items=1000)
    parameters: Optional[Dict[str, Any]] = None
    reason: Optional[str] = Field(None, max_length=500)
    confirm_destructive: bool = False
    dry_run: bool = False
    
    @validator('confirm_destructive')
    def validate_destructive_operations(cls, v, values):
        destructive_ops = [BulkOperationType.DELETE]
        if values.get('operation_type') in destructive_ops and not v and not values.get('dry_run'):
            raise ValueError(f"Must confirm destructive operation: {values.get('operation_type')}")
        return v


# ===== API RESPONSE WRAPPERS =====

class AdminAPIResponse(BaseModel):
    """Standard admin API response wrapper"""
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    errors: Optional[List[str]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    operation_id: Optional[str] = None


class AdminErrorResponse(BaseModel):
    """Admin API error response"""
    success: bool = False
    error: str
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None