"""
Project sharing and public access models
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text, Integer, Relationship
from sqlalchemy import func
from enum import Enum

if TYPE_CHECKING:
    from .project import Project
    from .user import User


class SharePermission(str, Enum):
    """Permission levels for shared projects"""
    READ = "read"
    LIMITED = "limited"      # Limited access - hides irrelevant pages
    RESTRICTED = "restricted"  # Restricted access - only shows relevant content
    WRITE = "write"
    ADMIN = "admin"


class ShareStatus(str, Enum):
    """Status of shared projects"""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING = "pending"


class PublicAccessLevel(str, Enum):
    """Public access levels"""
    NONE = "none"
    READ_ONLY = "read_only"
    SEARCH_ONLY = "search_only"
    FULL_ACCESS = "full_access"


class ProjectShareBase(SQLModel):
    """Base model for project sharing"""
    project_id: int = Field(foreign_key="projects.id", index=True)
    shared_with_user_id: Optional[int] = Field(foreign_key="users.id", index=True)
    shared_by_user_id: int = Field(foreign_key="users.id", index=True)
    permission: SharePermission = Field(default=SharePermission.READ)
    status: ShareStatus = Field(default=ShareStatus.ACTIVE)
    expires_at: Optional[datetime] = Field(default=None)
    message: Optional[str] = Field(sa_column=Column(Text))
    
    # Public sharing options
    is_public: bool = Field(default=False)
    public_token: Optional[str] = Field(default=None, unique=True, index=True)
    public_access_level: PublicAccessLevel = Field(default=PublicAccessLevel.NONE)
    
    # Access tracking
    access_count: int = Field(default=0)
    last_accessed: Optional[datetime] = Field(default=None)


class ProjectShare(ProjectShareBase, table=True):
    """Project sharing configuration"""
    __tablename__ = "project_shares"
    
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
    project: "Project" = Relationship(back_populates="shares")
    shared_with_user: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ProjectShare.shared_with_user_id]"}
    )
    shared_by_user: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[ProjectShare.shared_by_user_id]"}
    )


class PublicSearchConfigBase(SQLModel):
    """Base model for public search configuration"""
    project_id: int = Field(foreign_key="projects.id", index=True)
    is_enabled: bool = Field(default=False)
    custom_title: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    custom_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    custom_branding: Optional[str] = Field(default=None, sa_column=Column(Text))  # JSON config
    allow_downloads: bool = Field(default=False)
    require_email: bool = Field(default=True)
    analytics_enabled: bool = Field(default=True)
    rate_limit_per_hour: int = Field(default=100)
    allowed_domains: Optional[str] = Field(default=None, sa_column=Column(Text))  # JSON list
    blocked_ips: Optional[str] = Field(default=None, sa_column=Column(Text))  # JSON list
    usage_tracking: bool = Field(default=True)
    
    # Meilisearch public key fields
    search_key: Optional[str] = Field(default=None, sa_column=Column(String(256)))
    search_key_uid: Optional[str] = Field(default=None, sa_column=Column(String(256)))
    key_created_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    key_last_rotated: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class PublicSearchConfig(PublicSearchConfigBase, table=True):
    """Configuration for public search interfaces"""
    __tablename__ = "public_search_configs"
    
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
    project: "Project" = Relationship(back_populates="public_search_config")


class ShareInvitationBase(SQLModel):
    """Base model for share invitations"""
    project_share_id: int = Field(foreign_key="project_shares.id", index=True)
    email: str = Field(sa_column=Column(String(255), index=True))
    invitation_token: str = Field(unique=True, index=True)
    expires_at: datetime
    is_accepted: bool = Field(default=False)
    is_expired: bool = Field(default=False)
    message: Optional[str] = Field(sa_column=Column(Text))


class ShareInvitation(ShareInvitationBase, table=True):
    """Invitations for project sharing"""
    __tablename__ = "share_invitations"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    accepted_at: Optional[datetime] = Field(default=None)
    
    # Relationships
    project_share: ProjectShare = Relationship()


class ShareAccessLogBase(SQLModel):
    """Base model for share access tracking"""
    project_share_id: int = Field(foreign_key="project_shares.id", index=True)
    user_id: Optional[int] = Field(foreign_key="users.id", index=True)
    ip_address: Optional[str] = Field(sa_column=Column(String(45)))  # IPv6 support
    user_agent: Optional[str] = Field(sa_column=Column(Text))
    access_type: str = Field(sa_column=Column(String(50)))  # view, download, search, etc.
    resource_accessed: Optional[str] = Field(sa_column=Column(String(500)))
    success: bool = Field(default=True)
    error_message: Optional[str] = Field(sa_column=Column(Text))


class ShareAccessLog(ShareAccessLogBase, table=True):
    """Log of access to shared projects"""
    __tablename__ = "share_access_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    
    # Relationships
    project_share: ProjectShare = Relationship()
    user: Optional["User"] = Relationship()


# Pydantic schemas for API
class ProjectShareCreate(SQLModel):
    """Schema for creating project shares"""
    project_id: int
    shared_with_user_id: Optional[int] = None
    permission: SharePermission = SharePermission.READ
    expires_at: Optional[datetime] = None
    message: Optional[str] = None
    is_public: bool = False
    public_access_level: PublicAccessLevel = PublicAccessLevel.NONE


class ProjectShareUpdate(SQLModel):
    """Schema for updating project shares"""
    permission: Optional[SharePermission] = None
    status: Optional[ShareStatus] = None
    expires_at: Optional[datetime] = None
    message: Optional[str] = None
    is_public: Optional[bool] = None
    public_access_level: Optional[PublicAccessLevel] = None


class ProjectShareRead(ProjectShareBase):
    """Schema for reading project shares"""
    id: int
    created_at: datetime
    updated_at: datetime


class PublicSearchConfigCreate(SQLModel):
    """Schema for creating public search configs"""
    project_id: int
    is_enabled: bool = False
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    custom_branding: Optional[str] = None
    allow_downloads: bool = False
    require_email: bool = True
    analytics_enabled: bool = True
    rate_limit_per_hour: int = 100
    allowed_domains: Optional[str] = None
    blocked_ips: Optional[str] = None
    usage_tracking: bool = True


class PublicSearchConfigUpdate(SQLModel):
    """Schema for updating public search configs"""
    is_enabled: Optional[bool] = None
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None
    custom_branding: Optional[str] = None
    allow_downloads: Optional[bool] = None
    require_email: Optional[bool] = None
    analytics_enabled: Optional[bool] = None
    rate_limit_per_hour: Optional[int] = None
    allowed_domains: Optional[str] = None
    blocked_ips: Optional[str] = None
    usage_tracking: Optional[bool] = None


class PublicSearchConfigRead(PublicSearchConfigBase):
    """Schema for reading public search configs"""
    id: int
    created_at: datetime
    updated_at: datetime


class ShareInvitationCreate(SQLModel):
    """Schema for creating share invitations"""
    project_share_id: int
    email: str
    expires_at: datetime
    message: Optional[str] = None


class ShareInvitationRead(ShareInvitationBase):
    """Schema for reading share invitations"""
    id: int
    created_at: datetime
    accepted_at: Optional[datetime] = None


class ShareAccessLogCreate(SQLModel):
    """Schema for creating share access logs"""
    project_share_id: int
    user_id: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    access_type: str
    resource_accessed: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class ShareAccessLogRead(ShareAccessLogBase):
    """Schema for reading share access logs"""
    id: int
    created_at: datetime