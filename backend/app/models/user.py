"""
User model
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text, Relationship
from sqlalchemy import func

if TYPE_CHECKING:
    from .plans import UserPlan, UserRateLimit, UserPlanUsage
    from .library import StarredItem, SavedSearch, SearchHistory, SearchSuggestion, UserCollection
    from .entities import CanonicalEntity, ExtractedEntity, EntityResolution
    from .extraction_schemas import ContentExtractionSchema, ContentExtraction, ExtractionTemplate, ExtractionJob
    from .investigations import Investigation, Evidence


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
    orcid_id: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    professional_title: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    organization_website: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    research_purpose: Optional[str] = Field(default=None, sa_column=Column(Text))
    expected_usage: Optional[str] = Field(default=None, sa_column=Column(Text))
    data_handling_agreement: bool = Field(default=False)
    ethics_agreement: bool = Field(default=False)


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
    
    # Relationships
    plan: Optional["UserPlan"] = Relationship(back_populates="user")
    rate_limit: Optional["UserRateLimit"] = Relationship(back_populates="user")
    usage_records: List["UserPlanUsage"] = Relationship(back_populates="user")
    starred_items: List["StarredItem"] = Relationship(back_populates="user")
    saved_searches: List["SavedSearch"] = Relationship(back_populates="user")
    search_history: List["SearchHistory"] = Relationship(back_populates="user")
    search_suggestions: List["SearchSuggestion"] = Relationship(back_populates="user")
    collections: List["UserCollection"] = Relationship(back_populates="user")
    extraction_schemas: List["ContentExtractionSchema"] = Relationship(back_populates="user")
    content_extractions: List["ContentExtraction"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "[ContentExtraction.user_id]"}
    )
    extraction_templates: List["ExtractionTemplate"] = Relationship(
        back_populates="created_by",
        sa_relationship_kwargs={"foreign_keys": "[ExtractionTemplate.created_by_user_id]"}
    )
    extraction_jobs: List["ExtractionJob"] = Relationship(back_populates="user")
    investigations: List["Investigation"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "[Investigation.user_id]"}
    )
    evidence: List["Evidence"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "[Evidence.user_id]"}
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