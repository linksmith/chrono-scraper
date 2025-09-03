"""
User model
"""
import re
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Column, String, DateTime, Text, Relationship
from sqlalchemy import func
from pydantic import validator, EmailStr

if TYPE_CHECKING:
    from .plans import UserPlan, UserRateLimit, UserPlanUsage
    from .library import StarredItem, SavedSearch, SearchHistory, SearchSuggestion, UserCollection
    from .extraction_schemas import ContentExtractionSchema, ContentExtraction, ExtractionTemplate, ExtractionJob
    from .investigations import Investigation, Evidence


class UserBase(SQLModel):
    """Base user model with common fields"""
    email: EmailStr = Field(sa_column=Column(String(255), unique=True, index=True))
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
    
    # Enhanced Security Fields
    # Account lockout
    is_locked: bool = Field(default=False)
    locked_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    locked_until: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    failed_login_attempts: int = Field(default=0)
    last_failed_login: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Password security
    password_changed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    force_password_change: bool = Field(default=False)
    password_history: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(String(2048))  # JSON string of hashed previous passwords
    )
    
    # Two-Factor Authentication
    mfa_enabled: bool = Field(default=False)
    mfa_secret: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255))  # Encrypted TOTP secret
    )
    mfa_backup_codes: Optional[List[str]] = Field(
        default=None,
        sa_column=Column(String(2048))  # JSON string of hashed backup codes
    )
    mfa_enabled_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    mfa_last_used: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Email-based 2FA
    mfa_email_code: Optional[str] = Field(
        default=None,
        sa_column=Column(String(10))  # Temporary email verification code
    )
    mfa_email_code_expiry: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Session security
    max_concurrent_sessions: int = Field(default=5)
    require_mfa_for_admin: bool = Field(default=True)
    
    # Risk assessment
    risk_score: int = Field(default=0)  # 0-100, calculated based on behavior
    last_risk_assessment: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Privacy and compliance
    data_retention_days: Optional[int] = Field(default=None)  # Custom retention period
    gdpr_consent_date: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    privacy_settings: Optional[str] = Field(
        default=None,
        sa_column=Column(String(1024))  # JSON string of privacy preferences
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
    
    # Personal API Keys
    openrouter_api_key: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255))  # Encrypted OpenRouter API key
    )
    proxy_server: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255))  # Proxy server URL (e.g., http://gate.smartproxy.com:10001)
    )
    proxy_username: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255))  # Proxy username
    )
    proxy_password: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255))  # Encrypted proxy password
    )
    
    # Plan Information
    current_plan: str = Field(
        default="free",
        sa_column=Column(String(50))  # free, flash, blaze, lightning
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
    # Commented out temporarily to fix SQLAlchemy initialization issue
    # These relationships will be re-added once the circular import is resolved
    # added_project_pages: List["ProjectPage"] = Relationship(
    #     back_populates="added_by_user",
    #     sa_relationship_kwargs={
    #         "foreign_keys": "[ProjectPage.added_by]",
    #         "post_update": True
    #     }
    # )
    # reviewed_project_pages: List["ProjectPage"] = Relationship(
    #     back_populates="reviewed_by_user",
    #     sa_relationship_kwargs={
    #         "foreign_keys": "[ProjectPage.reviewed_by]",
    #         "post_update": True
    #     }
    # )


class UserCreate(UserBase):
    """Schema for creating users"""
    password: str = Field(min_length=8, max_length=128)
    oauth2_provider: Optional[str] = None
    oauth2_id: Optional[str] = None
    
    @validator('password')
    def validate_password(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if len(v) > 128:
            raise ValueError('Password must not exceed 128 characters')
        
        # Check for at least one digit
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        
        # Check for at least one uppercase letter
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        
        # Check for at least one lowercase letter
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        
        # Check for at least one special character
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        
        return v
    
    @validator('full_name')
    def validate_full_name(cls, v):
        """Validate full name"""
        if v and len(v.strip()) < 2:
            raise ValueError('Full name must be at least 2 characters long')
        if v and len(v) > 255:
            raise ValueError('Full name must not exceed 255 characters')
        return v.strip() if v else v
    
    @validator('organization_website')
    def validate_organization_website(cls, v):
        """Validate organization website URL"""
        if v:
            url_pattern = re.compile(
                r'^https?://'  # http:// or https://
                r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
                r'localhost|'  # localhost...
                r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
                r'(?::\d+)?'  # optional port
                r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            
            if not url_pattern.match(v):
                raise ValueError('Invalid URL format for organization website')
        return v
    
    @validator('linkedin_profile')
    def validate_linkedin_profile(cls, v):
        """Validate LinkedIn profile URL"""
        if v:
            linkedin_pattern = re.compile(
                r'^https://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9-]+/?$',
                re.IGNORECASE
            )
            if not linkedin_pattern.match(v):
                raise ValueError('Invalid LinkedIn profile URL format')
        return v
    
    @validator('orcid_id')
    def validate_orcid_id(cls, v):
        """Validate ORCID ID format"""
        if v:
            orcid_pattern = re.compile(r'^\d{4}-\d{4}-\d{4}-\d{4}$')
            if not orcid_pattern.match(v):
                raise ValueError('Invalid ORCID ID format. Expected: 0000-0000-0000-0000')
        return v
    
    @validator('research_purpose')
    def validate_research_purpose(cls, v):
        """Validate research purpose for professional users"""
        if v and len(v.strip()) < 20:
            raise ValueError('Research purpose must be at least 20 characters to demonstrate legitimate use')
        if v and len(v) > 2000:
            raise ValueError('Research purpose must not exceed 2000 characters')
        return v.strip() if v else v
    
    @validator('expected_usage')
    def validate_expected_usage(cls, v):
        """Validate expected usage description"""
        if v and len(v.strip()) < 10:
            raise ValueError('Expected usage must be at least 10 characters')
        if v and len(v) > 1000:
            raise ValueError('Expected usage must not exceed 1000 characters')
        return v.strip() if v else v


class UserUpdate(SQLModel):
    """Schema for updating users"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    institutional_email: Optional[EmailStr] = None
    linkedin_profile: Optional[str] = None
    research_interests: Optional[str] = None
    academic_affiliation: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    openrouter_api_key: Optional[str] = None
    proxy_server: Optional[str] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    professional_title: Optional[str] = None
    organization_website: Optional[str] = None
    
    @validator('password')
    def validate_password(cls, v):
        """Validate password strength when updating"""
        if v is None:
            return v
        return UserCreate.validate_password(v)


class UserRead(UserBase):
    """Schema for reading users"""
    id: int
    approval_status: str
    approval_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    login_count: int
    current_plan: str
    openrouter_api_key: Optional[str] = None
    proxy_server: Optional[str] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None
    is_admin: bool = False  # Frontend compatibility field mapping is_superuser
    
    # Security status (public fields only)
    is_locked: bool = False
    mfa_enabled: bool = False
    force_password_change: bool = False
    risk_score: int = 0
    failed_login_attempts: int = 0


class UserReadWithStats(UserRead):
    """User schema with additional statistics"""
    project_count: int = 0
    total_pages_scraped: int = 0