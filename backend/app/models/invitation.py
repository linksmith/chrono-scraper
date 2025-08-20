"""
Invitation token models for user referrals
"""
from datetime import datetime
from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column, DateTime, JSON
from sqlalchemy import func
import secrets


class InvitationTokenBase(SQLModel):
    """Base model for invitation tokens"""
    token: str = Field(unique=True, index=True, description="Unique invitation token")
    creator_user_id: int = Field(foreign_key="users.id", index=True, description="User who created the invitation")
    used_by_email: Optional[str] = Field(default=None, description="Email of user who used this invitation")
    expires_at: datetime = Field(description="When this invitation expires")
    is_used: bool = Field(default=False, description="Whether this invitation has been used")
    used_at: Optional[datetime] = Field(default=None, description="When this invitation was used")
    max_uses: int = Field(default=1, description="Maximum number of times this invitation can be used")
    current_uses: int = Field(default=0, description="Current number of uses")
# Temporarily disabled - SQLModel JSON issue
    # metadata: dict = Field(default={}, sa_column=Column(JSON), description="Additional metadata")


class InvitationToken(InvitationTokenBase, table=True):
    """Invitation tokens for bypassing user approval"""
    __tablename__ = "invitation_tokens"
    
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


# Pydantic schemas for API
class InvitationTokenCreate(SQLModel):
    """Schema for creating invitation tokens"""
    expires_at: Optional[datetime] = None  # Will default to 7 days if not provided
    max_uses: int = Field(default=1, description="Maximum number of uses (1-10)")
# Temporarily disabled - will fix JSON field issue later
    # metadata: dict = Field(default_factory=dict)


class InvitationTokenRead(InvitationTokenBase):
    """Schema for reading invitation tokens"""
    id: int
    created_at: datetime
    updated_at: datetime


class InvitationTokenUpdate(SQLModel):
    """Schema for updating invitation tokens"""
    is_used: Optional[bool] = None
    used_by_email: Optional[str] = None
    used_at: Optional[datetime] = None
    current_uses: Optional[int] = None


class InvitationTokenValidation(SQLModel):
    """Schema for validating invitation tokens"""
    is_valid: bool
    message: str
    creator_name: Optional[str] = None
    uses_remaining: Optional[int] = None
    expires_at: Optional[datetime] = None


def generate_invitation_token() -> str:
    """Generate a secure invitation token"""
    return f"inv_{secrets.token_urlsafe(32)}"