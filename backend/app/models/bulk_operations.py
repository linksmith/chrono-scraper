"""
Bulk operations schemas and models for admin operations
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator


class BulkOperationType(str, Enum):
    """Types of bulk operations"""
    APPROVE = "approve"
    DENY = "deny"
    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"
    DELETE = "delete"
    ASSIGN_ROLE = "assign_role"
    REMOVE_ROLE = "remove_role"
    VERIFY_EMAIL = "verify_email"
    UNVERIFY_EMAIL = "unverify_email"
    SEND_EMAIL = "send_email"
    EXPORT = "export"
    IMPORT = "import"


class BulkOperationStatus(str, Enum):
    """Status of bulk operations"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"


class ExportFormat(str, Enum):
    """Export formats"""
    CSV = "csv"
    JSON = "json"
    XLSX = "xlsx"


class UserBulkOperationRequest(BaseModel):
    """Request schema for bulk user operations"""
    user_ids: List[int] = Field(..., min_items=1, max_items=1000)
    operation: BulkOperationType
    reason: Optional[str] = Field(None, max_length=500)
    
    # Operation-specific parameters
    role: Optional[str] = Field(None)  # For role assignment operations
    email_template_id: Optional[str] = Field(None)  # For email operations
    custom_message: Optional[str] = Field(None, max_length=1000)  # For email operations
    
    # Confirmation for destructive operations
    confirm_destructive: Optional[bool] = Field(False)
    
    @validator('user_ids')
    def validate_user_ids(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("Duplicate user IDs are not allowed")
        return v
    
    @validator('confirm_destructive')
    def validate_destructive_operations(cls, v, values):
        destructive_ops = [BulkOperationType.DELETE]
        if values.get('operation') in destructive_ops and not v:
            raise ValueError(f"Must confirm destructive operation: {values.get('operation')}")
        return v


class UserExportRequest(BaseModel):
    """Request schema for user data export"""
    format: ExportFormat = ExportFormat.CSV
    user_ids: Optional[List[int]] = Field(None)  # If None, export all users
    include_fields: Optional[List[str]] = Field(None)  # If None, include all fields
    filters: Optional[Dict[str, Any]] = Field(None)  # Additional filters
    
    # Export options
    include_inactive: bool = Field(True)
    include_unverified: bool = Field(True)
    date_range_start: Optional[datetime] = Field(None)
    date_range_end: Optional[datetime] = Field(None)


class UserImportRequest(BaseModel):
    """Request schema for user data import"""
    data: List[Dict[str, Any]] = Field(..., min_items=1, max_items=1000)
    update_existing: bool = Field(False)  # Whether to update existing users
    validate_only: bool = Field(False)  # Dry run validation
    send_invitation: bool = Field(False)  # Send invitation emails
    
    # Default values for imported users
    default_approval_status: str = Field("pending")
    default_is_active: bool = Field(True)
    default_is_verified: bool = Field(False)


class BulkEmailRequest(BaseModel):
    """Request schema for bulk email operations"""
    user_ids: List[int] = Field(..., min_items=1, max_items=1000)
    email_type: str = Field(...)  # verification, welcome, notification, custom
    template_id: Optional[str] = Field(None)
    subject: Optional[str] = Field(None, max_length=200)
    message: Optional[str] = Field(None, max_length=5000)
    
    # Email scheduling
    send_immediately: bool = Field(True)
    scheduled_time: Optional[datetime] = Field(None)
    
    @validator('user_ids')
    def validate_user_ids(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("Duplicate user IDs are not allowed")
        return v


class BulkOperationResult(BaseModel):
    """Result schema for bulk operations"""
    operation_id: str
    operation_type: BulkOperationType
    status: BulkOperationStatus
    total_requested: int
    total_processed: int
    total_successful: int
    total_failed: int
    
    # Detailed results
    successful_ids: List[int] = Field(default_factory=list)
    failed_ids: List[int] = Field(default_factory=list)
    failed_reasons: Dict[int, str] = Field(default_factory=dict)
    
    # Timing information
    started_at: datetime
    completed_at: Optional[datetime] = Field(None)
    duration_seconds: Optional[float] = Field(None)
    
    # Additional metadata
    performed_by: int  # Admin user ID
    reason: Optional[str] = Field(None)
    audit_log_ids: List[int] = Field(default_factory=list)


class UserAnalyticsRequest(BaseModel):
    """Request schema for user analytics"""
    date_range_start: Optional[datetime] = Field(None)
    date_range_end: Optional[datetime] = Field(None)
    group_by: str = Field("day")  # day, week, month
    metrics: List[str] = Field(default_factory=lambda: ["registrations", "approvals", "logins"])
    
    # Filters
    approval_status: Optional[List[str]] = Field(None)
    user_type: Optional[List[str]] = Field(None)
    include_inactive: bool = Field(False)


class UserAnalyticsResponse(BaseModel):
    """Response schema for user analytics"""
    summary: Dict[str, Any]
    time_series: List[Dict[str, Any]]
    breakdowns: Dict[str, Dict[str, Any]]
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class BulkOperationProgress(BaseModel):
    """Progress tracking for bulk operations"""
    operation_id: str
    status: BulkOperationStatus
    progress_percentage: float = Field(0.0, ge=0.0, le=100.0)
    current_step: str
    total_steps: int
    completed_steps: int
    estimated_remaining_seconds: Optional[int] = Field(None)
    
    # Current processing info
    current_batch: int = Field(0)
    total_batches: int = Field(0)
    items_processed: int = Field(0)
    items_total: int = Field(0)
    
    # Error tracking
    errors_count: int = Field(0)
    warnings_count: int = Field(0)
    last_error: Optional[str] = Field(None)


class UserActivitySummary(BaseModel):
    """Summary of user activity for reporting"""
    user_id: int
    email: str
    full_name: Optional[str] = Field(None)
    
    # Activity metrics
    login_count: int = Field(0)
    last_login: Optional[datetime] = Field(None)
    projects_created: int = Field(0)
    pages_scraped: int = Field(0)
    searches_performed: int = Field(0)
    
    # Account status
    approval_status: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    # Engagement score (calculated)
    engagement_score: float = Field(0.0, ge=0.0, le=100.0)


class InvitationBulkRequest(BaseModel):
    """Request schema for bulk invitation generation"""
    count: int = Field(..., ge=1, le=100)
    expires_in_days: int = Field(7, ge=1, le=365)
    max_uses: int = Field(1, ge=1, le=1000)
    
    # Default user settings for invited users
    default_approval_status: str = Field("pending")
    default_role: str = Field("user")
    notes: Optional[str] = Field(None, max_length=500)
    
    # Email settings
    send_invitation_emails: bool = Field(False)
    invitation_message: Optional[str] = Field(None, max_length=1000)
    invitee_emails: Optional[List[str]] = Field(None)  # If sending emails
    
    @validator('invitee_emails')
    def validate_invitee_emails(cls, v, values):
        if values.get('send_invitation_emails') and not v:
            raise ValueError("Must provide invitee emails when send_invitation_emails is True")
        if v and len(v) != values.get('count', 0):
            raise ValueError("Number of invitee emails must match the count")
        return v