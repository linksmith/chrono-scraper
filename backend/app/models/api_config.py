"""
API Configuration models
"""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, String, DateTime, Text, JSON
from sqlalchemy import func
from enum import Enum


class APIServiceType(str, Enum):
    """API service type enumeration"""
    FIRECRAWL = "firecrawl"
    WAYBACK = "wayback"
    MEILISEARCH = "meilisearch"
    CUSTOM = "custom"


class APIConfigBase(SQLModel):
    """Base API configuration model"""
    service_name: str = Field(sa_column=Column(String(100)))
    service_type: APIServiceType = Field(sa_column=Column(String(20)))
    api_url: str = Field(sa_column=Column(String(500)))
    active: bool = Field(default=True)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))


class APIConfig(APIConfigBase, table=True):
    """API configuration model for database"""
    __tablename__ = "api_configs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    
    # Encrypted credentials
    api_key_encrypted: Optional[str] = Field(default=None, sa_column=Column(Text))
    api_secret_encrypted: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Configuration parameters
    config_params: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Rate limiting
    rate_limit_requests: Optional[int] = Field(default=None)
    rate_limit_window: Optional[int] = Field(default=3600)  # seconds
    
    # Usage tracking
    total_requests: int = Field(default=0)
    successful_requests: int = Field(default=0)
    failed_requests: int = Field(default=0)
    last_used: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Health monitoring
    health_check_url: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    last_health_check: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    health_status: str = Field(default="unknown", sa_column=Column(String(20)))  # healthy, unhealthy, unknown
    
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


class APIKeyBase(SQLModel):
    """Base API key model"""
    key_name: str = Field(sa_column=Column(String(100)))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    active: bool = Field(default=True)


class APIKey(APIKeyBase, table=True):
    """API key model for database"""
    __tablename__ = "api_keys"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    
    # Encrypted key
    key_hash: str = Field(sa_column=Column(String(255)))  # Hashed version
    key_prefix: str = Field(sa_column=Column(String(10)))  # First few chars for identification
    
    # Permissions
    scopes: Optional[list] = Field(default=None, sa_column=Column(JSON))  # List of allowed scopes
    
    # Usage limits
    rate_limit_requests: Optional[int] = Field(default=1000)
    rate_limit_window: Optional[int] = Field(default=3600)  # seconds
    
    # Usage tracking
    total_requests: int = Field(default=0)
    last_used: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Expiration
    expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
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


# Pydantic schemas
class APIConfigCreate(APIConfigBase):
    """Schema for creating API configurations"""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    config_params: Optional[dict] = None


class APIConfigUpdate(SQLModel):
    """Schema for updating API configurations"""
    service_name: Optional[str] = None
    api_url: Optional[str] = None
    active: Optional[bool] = None
    description: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    config_params: Optional[dict] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_window: Optional[int] = None


class APIConfigRead(APIConfigBase):
    """Schema for reading API configurations"""
    id: int
    user_id: Optional[int]
    rate_limit_requests: Optional[int]
    rate_limit_window: Optional[int]
    total_requests: int
    successful_requests: int
    failed_requests: int
    last_used: Optional[datetime]
    health_status: str
    last_health_check: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # Note: Never expose encrypted keys in read schema


class APIKeyCreate(APIKeyBase):
    """Schema for creating API keys"""
    scopes: Optional[list] = None
    rate_limit_requests: Optional[int] = None
    rate_limit_window: Optional[int] = None
    expires_at: Optional[datetime] = None


class APIKeyRead(APIKeyBase):
    """Schema for reading API keys"""
    id: int
    user_id: int
    key_prefix: str
    scopes: Optional[list]
    rate_limit_requests: Optional[int]
    rate_limit_window: Optional[int]
    total_requests: int
    last_used: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # Note: Never expose actual key or hash


class APIKeyCreateResponse(SQLModel):
    """Response schema for created API key"""
    id: int
    key_name: str
    api_key: str  # Only returned once during creation
    key_prefix: str
    scopes: Optional[list]
    expires_at: Optional[datetime]