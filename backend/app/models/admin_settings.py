"""
Admin settings model for dynamic configuration
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, DateTime
from sqlalchemy import func


class AdminSettings(SQLModel, table=True):
    """Admin settings for dynamic configuration"""
    __tablename__ = "admin_settings"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Signup control flags
    users_open_registration: bool = Field(
        default=True,
        description="Allow new users to register via the standard registration form"
    )
    allow_invitation_tokens: bool = Field(
        default=True, 
        description="Allow creation and use of invitation tokens for user registration"
    )
    
    # Metadata
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now()
        )
    )
    updated_by_id: Optional[int] = Field(default=None, foreign_key="users.id")


class AdminSettingsRead(SQLModel):
    """Schema for reading admin settings"""
    id: int
    users_open_registration: bool
    allow_invitation_tokens: bool
    updated_at: datetime
    updated_by_id: Optional[int]


class AdminSettingsUpdate(SQLModel):
    """Schema for updating admin settings"""
    users_open_registration: Optional[bool] = None
    allow_invitation_tokens: Optional[bool] = None