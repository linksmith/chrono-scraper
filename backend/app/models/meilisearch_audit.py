"""
Meilisearch Key Audit and Tracking Models

This module provides audit trail and lifecycle tracking for Meilisearch API keys,
enabling security monitoring, usage analytics, and key rotation management.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text, Integer, JSON, Relationship
from sqlalchemy import func
from enum import Enum

if TYPE_CHECKING:
    from .project import Project


class MeilisearchKeyType(str, Enum):
    """Types of Meilisearch API keys"""
    PROJECT_OWNER = "project_owner"    # Full access for project owners
    PUBLIC = "public"                  # Read-only for public projects
    TENANT = "tenant"                  # Time-limited sharing tokens
    ADMIN = "admin"                    # Administrative keys (rarely used)


class MeilisearchKeyBase(SQLModel):
    """Base model for Meilisearch key audit tracking"""
    project_id: int = Field(foreign_key="projects.id", index=True)
    key_uid: str = Field(sa_column=Column(String(256), unique=True))
    key_type: MeilisearchKeyType = Field(sa_column=Column(String(50)))
    key_name: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    key_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Key configuration
    actions: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))  # List of allowed actions
    indexes: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))  # List of allowed indexes
    expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Status tracking
    is_active: bool = Field(default=True)
    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    revoked_reason: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    
    # Usage tracking
    usage_count: int = Field(default=0)
    last_used_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class MeilisearchKey(MeilisearchKeyBase, table=True):
    """Audit trail and lifecycle tracking for Meilisearch API keys"""
    __tablename__ = "meilisearch_keys"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now()
        )
    )
    
    # Relationships
    project: "Project" = Relationship()


class MeilisearchUsageLogBase(SQLModel):
    """Base model for Meilisearch API key usage logging"""
    key_id: int = Field(foreign_key="meilisearch_keys.id", index=True)
    operation: str = Field(sa_column=Column(String(100)))  # 'search', 'documents.get', etc.
    index_name: str = Field(sa_column=Column(String(255)))
    query: Optional[str] = Field(default=None, sa_column=Column(Text))
    filters: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    result_count: Optional[int] = Field(default=None)
    response_time_ms: Optional[int] = Field(default=None)
    success: bool = Field(default=True)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Request metadata
    ip_address: Optional[str] = Field(default=None, sa_column=Column(String(45)))  # IPv6 support
    user_agent: Optional[str] = Field(default=None, sa_column=Column(Text))
    request_id: Optional[str] = Field(default=None, sa_column=Column(String(128)))


class MeilisearchUsageLog(MeilisearchUsageLogBase, table=True):
    """Detailed usage logging for Meilisearch API key operations"""
    __tablename__ = "meilisearch_usage_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    
    # Relationships
    key: MeilisearchKey = Relationship()


class MeilisearchSecurityEventBase(SQLModel):
    """Base model for Meilisearch security events"""
    key_id: Optional[int] = Field(default=None, foreign_key="meilisearch_keys.id", index=True)
    event_type: str = Field(sa_column=Column(String(100)))  # 'key_created', 'key_revoked', 'suspicious_usage', etc.
    severity: str = Field(sa_column=Column(String(20)))  # 'info', 'warning', 'critical'
    description: str = Field(sa_column=Column(Text))
    metadata: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Event source
    source_ip: Optional[str] = Field(default=None, sa_column=Column(String(45)))
    user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    automated: bool = Field(default=False)  # True if event was triggered by automation


class MeilisearchSecurityEvent(MeilisearchSecurityEventBase, table=True):
    """Security event logging for Meilisearch operations"""
    __tablename__ = "meilisearch_security_events"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    
    # Relationships
    key: Optional[MeilisearchKey] = Relationship()


# Pydantic schemas for API
class MeilisearchKeyCreate(SQLModel):
    """Schema for creating Meilisearch key audit records"""
    project_id: int
    key_uid: str
    key_type: MeilisearchKeyType
    key_name: Optional[str] = None
    key_description: Optional[str] = None
    actions: Optional[List[str]] = None
    indexes: Optional[List[str]] = None
    expires_at: Optional[datetime] = None


class MeilisearchKeyRead(MeilisearchKeyBase):
    """Schema for reading Meilisearch key audit records"""
    id: int
    created_at: datetime
    updated_at: datetime


class MeilisearchKeyUpdate(SQLModel):
    """Schema for updating Meilisearch key audit records"""
    is_active: Optional[bool] = None
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None
    usage_count: Optional[int] = None
    last_used_at: Optional[datetime] = None


class MeilisearchUsageLogCreate(SQLModel):
    """Schema for creating usage log entries"""
    key_id: int
    operation: str
    index_name: str
    query: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    result_count: Optional[int] = None
    response_time_ms: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None


class MeilisearchUsageLogRead(MeilisearchUsageLogBase):
    """Schema for reading usage log entries"""
    id: int
    created_at: datetime


class MeilisearchSecurityEventCreate(SQLModel):
    """Schema for creating security events"""
    key_id: Optional[int] = None
    event_type: str
    severity: str
    description: str
    metadata: Optional[Dict[str, Any]] = None
    source_ip: Optional[str] = None
    user_id: Optional[int] = None
    automated: bool = False


class MeilisearchSecurityEventRead(MeilisearchSecurityEventBase):
    """Schema for reading security events"""
    id: int
    created_at: datetime


class MeilisearchKeyStats(SQLModel):
    """Statistics for Meilisearch key usage"""
    total_keys: int = 0
    active_keys: int = 0
    expired_keys: int = 0
    revoked_keys: int = 0
    keys_by_type: Dict[str, int] = {}
    total_operations: int = 0
    operations_last_24h: int = 0
    operations_last_7d: int = 0
    avg_response_time_ms: Optional[float] = None
    error_rate_percent: Optional[float] = None


class MeilisearchSecuritySummary(SQLModel):
    """Security summary for Meilisearch operations"""
    total_events: int = 0
    critical_events: int = 0
    warning_events: int = 0
    events_last_24h: int = 0
    suspicious_activity_count: int = 0
    key_rotation_due_count: int = 0
    recent_security_events: List[MeilisearchSecurityEventRead] = []