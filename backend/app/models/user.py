"""
User model
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text
from sqlalchemy import func


class UserBase(SQLModel):
    """Base user model with common fields"""
    email: str = Field(sa_column=Column(String(255), unique=True, index=True))
    full_name: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    is_verified: bool = Field(default=False)
    
    # Profile fields
    institutional_email: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    linkedin_profile: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    research_interests: Optional[str] = Field(default=None, sa_column=Column(Text))
    academic_affiliation: Optional[str] = Field(default=None, sa_column=Column(String(255)))


class User(UserBase, table=True):
    """User model for database"""
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str = Field(sa_column=Column(String(255)))
    
    # Approval system fields
    approval_status: str = Field(
        default="pending",
        sa_column=Column(String(20))  # pending, approved, rejected
    )
    approval_date: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    approved_by_id: Optional[int] = Field(default=None, foreign_key="users.id")
    
    # Timestamps
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
    
    # Login tracking
    last_login: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    login_count: int = Field(default=0)
    
    # Security
    password_reset_token: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255))
    )
    password_reset_expires: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    email_verification_token: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255))
    )
    
    # OAuth2 fields
    oauth2_provider: Optional[str] = Field(
        default=None,
        sa_column=Column(String(50))  # google, github, etc.
    )
    oauth2_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255))  # Provider's user ID
    )


class UserCreate(UserBase):
    """Schema for creating users"""
    password: str
    oauth2_provider: Optional[str] = None
    oauth2_id: Optional[str] = None


class UserUpdate(SQLModel):
    """Schema for updating users"""
    email: Optional[str] = None
    full_name: Optional[str] = None
    institutional_email: Optional[str] = None
    linkedin_profile: Optional[str] = None
    research_interests: Optional[str] = None
    academic_affiliation: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class UserRead(UserBase):
    """Schema for reading users"""
    id: int
    approval_status: str
    approval_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    login_count: int


class UserReadWithStats(UserRead):
    """User schema with additional statistics"""
    project_count: int = 0
    total_pages_scraped: int = 0