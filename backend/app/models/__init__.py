"""Database models module"""

# Import all models for Alembic to discover them
from .user import User, UserCreate, UserUpdate, UserRead, UserReadWithStats
from .project import (
    Project,
    Domain, 
    ScrapeSession,
    Page,
    ProjectCreate,
    ProjectUpdate,
    ProjectRead,
    ProjectReadWithStats,
    DomainCreate,
    DomainUpdate,
    DomainRead,
    ProjectStatus,
    DomainStatus,
    MatchType,
    ScrapeSessionStatus
)
from .api_config import (
    APIConfig,
    APIKey,
    APIConfigCreate,
    APIConfigUpdate,
    APIConfigRead,
    APIKeyCreate,
    APIKeyRead,
    APIKeyCreateResponse,
    APIServiceType
)

__all__ = [
    # User models
    "User",
    "UserCreate", 
    "UserUpdate",
    "UserRead",
    "UserReadWithStats",
    
    # Project models
    "Project",
    "Domain",
    "ScrapeSession", 
    "Page",
    "ProjectCreate",
    "ProjectUpdate", 
    "ProjectRead",
    "ProjectReadWithStats",
    "DomainCreate",
    "DomainUpdate",
    "DomainRead",
    
    # API Config models
    "APIConfig",
    "APIKey",
    "APIConfigCreate",
    "APIConfigUpdate", 
    "APIConfigRead",
    "APIKeyCreate",
    "APIKeyRead",
    "APIKeyCreateResponse",
    
    # Enums
    "ProjectStatus",
    "DomainStatus", 
    "MatchType",
    "ScrapeSessionStatus",
    "APIServiceType"
]