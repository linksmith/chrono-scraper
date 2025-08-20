"""
Project and related models
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING, Union, Dict, Any
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text, Integer, ForeignKey, Relationship, JSON
from sqlalchemy import func, UniqueConstraint
from enum import Enum
from pydantic import validator, field_validator, field_serializer

if TYPE_CHECKING:
    from .library import StarredItem, SearchHistory
    from .entities import ExtractedEntity
    from .extraction_schemas import ContentExtraction
    from .sharing import ProjectShare, PublicSearchConfig


class ProjectStatus(str, Enum):
    """Project status enumeration"""
    NO_INDEX = "no_index"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ERROR = "error"
    PAUSED = "paused"


class DomainStatus(str, Enum):
    """Domain status enumeration"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class MatchType(str, Enum):
    """Domain match type enumeration"""
    EXACT = "exact"
    PREFIX = "prefix"
    DOMAIN = "domain"
    REGEX = "regex"


class ScrapeSessionStatus(str, Enum):
    """Scrape session status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class LangExtractProvider(str, Enum):
    """LangExtract LLM provider enumeration"""
    DISABLED = "disabled"
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class PageReviewStatus(str, Enum):
    """Page review status enumeration"""
    UNREVIEWED = "unreviewed"
    RELEVANT = "relevant"
    IRRELEVANT = "irrelevant"
    NEEDS_REVIEW = "needs_review"
    DUPLICATE = "duplicate"


class PageCategory(str, Enum):
    """Page content category enumeration"""
    GOVERNMENT = "government"
    RESEARCH = "research"
    NEWS = "news"
    BLOG = "blog"
    COMMERCIAL = "commercial"
    PERSONAL = "personal"
    SOCIAL_MEDIA = "social_media"
    ACADEMIC = "academic"
    LEGAL = "legal"
    TECHNICAL = "technical"


class PagePriority(str, Enum):
    """Page review priority enumeration"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectBase(SQLModel):
    """Base project model"""
    name: str = Field(sa_column=Column(String(200)))
    description: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    index_name: Optional[str] = Field(default=None, sa_column=Column(String(200)))
    process_documents: bool = Field(default=True)
    # Project configuration JSON
    config: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    
    # Content filtering options
    enable_attachment_download: bool = Field(default=True)  # Disable PDFs, DOCs, etc.
    
    # LangExtract Configuration
    langextract_enabled: bool = Field(default=False)
    langextract_provider: LangExtractProvider = Field(default=LangExtractProvider.DISABLED, sa_column=Column(String(20)))
    langextract_model: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    langextract_estimated_cost_per_1k: Optional[float] = Field(default=None)  # Cost estimate per 1000 pages
    
    @field_validator('langextract_provider', mode='before')
    @classmethod
    def validate_langextract_provider(cls, v):
        """Convert string values to LangExtractProvider enum"""
        if isinstance(v, str):
            try:
                return LangExtractProvider(v)
            except ValueError:
                # If invalid string, return default
                return LangExtractProvider.DISABLED
        elif isinstance(v, LangExtractProvider):
            return v
        return v
    
    @field_serializer('langextract_provider')
    def serialize_langextract_provider(self, value):
        """Serialize LangExtractProvider enum to string"""
        if isinstance(value, LangExtractProvider):
            return value.value
        return value


class Project(ProjectBase, table=True):
    """Project model for database"""
    __tablename__ = "projects"
    # Allow populating by alias (e.g., owner_id -> user_id) for backward compatibility
    model_config = {"populate_by_name": True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", alias="owner_id")
    
    # Meilisearch configuration
    index_search_key: Optional[str] = Field(default=None, sa_column=Column(String(256)))
    index_search_key_uid: Optional[str] = Field(default=None, sa_column=Column(String(256)))
    
    # Status
    status: ProjectStatus = Field(
        default=ProjectStatus.NO_INDEX,
        sa_column=Column(String(16))
    )
    # Activation flag
    is_active: bool = Field(default=True)
    
    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        """Convert string values to ProjectStatus enum"""
        if isinstance(v, str):
            try:
                return ProjectStatus(v)
            except ValueError:
                # If invalid string, return default
                return ProjectStatus.NO_INDEX
        elif isinstance(v, ProjectStatus):
            return v
        return v
    
    @field_serializer('status')
    def serialize_status(self, value):
        """Serialize ProjectStatus enum to string"""
        if isinstance(value, ProjectStatus):
            return value.value
        return value
    
    # Current scrape session reference (will be added later to avoid circular dependency)
    # current_scrape_session_id: Optional[int] = Field(
    #     default=None,
    #     foreign_key="scrape_sessions.id"
    # )
    
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
    
    # Relationships
    starred_by: List["StarredItem"] = Relationship(back_populates="project")
    search_history: List["SearchHistory"] = Relationship(back_populates="project")
    extracted_entities: List["ExtractedEntity"] = Relationship(back_populates="project")
    shares: List["ProjectShare"] = Relationship(back_populates="project")
    public_search_config: Optional["PublicSearchConfig"] = Relationship(back_populates="project")

    # Backwards-compatible alias for user_id used across tests and older code
    @property
    def owner_id(self) -> int:  # type: ignore[override]
        return self.user_id

    @owner_id.setter
    def owner_id(self, value: int) -> None:  # type: ignore[override]
        self.user_id = value


class DomainBase(SQLModel):
    """Base domain model"""
    domain_name: str = Field(sa_column=Column(String(255)))
    match_type: MatchType = Field(default=MatchType.DOMAIN, sa_column=Column(String(20)))
    url_path: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    max_pages: Optional[int] = Field(default=None)
    active: bool = Field(default=True)


class Domain(DomainBase, table=True):
    """Domain model for database"""
    __tablename__ = "domains"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id")
    
    status: DomainStatus = Field(
        default=DomainStatus.ACTIVE,
        sa_column=Column(String(16))
    )
    
    @field_validator('match_type', mode='before')
    @classmethod
    def validate_match_type(cls, v):
        """Convert string values to MatchType enum for internal consistency"""
        if isinstance(v, str):
            try:
                return MatchType(v)
            except ValueError:
                return MatchType.DOMAIN
        return v
    
    @field_serializer('match_type')
    def serialize_match_type(self, value):
        """Serialize MatchType enum to string for API responses"""
        if isinstance(value, MatchType):
            return value.value
        return value
    
    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        """Convert string values to DomainStatus enum"""
        if isinstance(v, str):
            try:
                return DomainStatus(v)
            except ValueError:
                # If invalid string, return default
                return DomainStatus.ACTIVE
        return v
    
    # Date range for scraping
    from_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    to_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Scraping configuration
    min_page_size: int = Field(default=200)  # Minimum page size in bytes
    page_size: int = Field(default=3000)  # CDX API pagination size
    
    # Scraping statistics
    total_pages: int = Field(default=0)
    scraped_pages: int = Field(default=0)
    failed_pages: int = Field(default=0)
    pending_pages: int = Field(default=0)
    duplicate_pages: int = Field(default=0)
    list_pages_filtered: int = Field(default=0)
    
    # Performance metrics
    avg_fetch_time: Optional[float] = Field(default=None)
    success_rate: Optional[float] = Field(default=None)
    
    # Timing
    last_scraped: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    estimated_completion: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # CDX resume state for pagination
    cdx_resume_key: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    cdx_resume_timestamp: Optional[str] = Field(default=None, sa_column=Column(String(20)))
    cdx_resume_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    
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


class ScrapeSessionBase(SQLModel):
    """Base scrape session model"""
    session_name: Optional[str] = Field(default=None, sa_column=Column(String(255)))


class ScrapeSession(ScrapeSessionBase, table=True):
    """Scrape session model for database"""
    __tablename__ = "scrape_sessions"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id")
    
    status: ScrapeSessionStatus = Field(
        default=ScrapeSessionStatus.PENDING,
        sa_column=Column(String(16))
    )
    
    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        """Convert string values to ScrapeSessionStatus enum"""
        if isinstance(v, str):
            try:
                return ScrapeSessionStatus(v)
            except ValueError:
                # If invalid string, return default
                return ScrapeSessionStatus.PENDING
        return v
    
    # Progress tracking
    total_urls: int = Field(default=0)
    completed_urls: int = Field(default=0)
    failed_urls: int = Field(default=0)
    cancelled_urls: int = Field(default=0)
    
    # Timing
    started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Error tracking
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # External batch integration (e.g., Firecrawl v2)
    external_batch_id: Optional[str] = Field(default=None, sa_column=Column(String(128)))
    external_batch_provider: Optional[str] = Field(default=None, sa_column=Column(String(64)))
    
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


class PageBase(SQLModel):
    """Base page model - optimized for single content source"""
    original_url: str = Field(sa_column=Column(Text))
    wayback_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    title: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    # Removed redundant content fields: content, extracted_content, markdown_content
    unix_timestamp: Optional[str] = Field(default=None, sa_column=Column(String(14)))
    mime_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    status_code: Optional[int] = Field(default=None)
    
    # Content extraction fields - single source of truth
    extracted_title: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    extracted_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    meta_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    meta_keywords: Optional[str] = Field(default=None, sa_column=Column(Text))
    author: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    published_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    language: Optional[str] = Field(default=None, sa_column=Column(String(10)))
    word_count: Optional[int] = Field(default=None)
    character_count: Optional[int] = Field(default=None)
    content_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    content_length: Optional[int] = Field(default=None)
    
    # Capture date from Wayback
    capture_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Page management and review fields
    review_status: PageReviewStatus = Field(
        default=PageReviewStatus.UNREVIEWED,
        sa_column=Column(String(20))
    )
    page_category: Optional[PageCategory] = Field(
        default=None,
        sa_column=Column(String(20))
    )
    priority_level: PagePriority = Field(
        default=PagePriority.MEDIUM,
        sa_column=Column(String(20))
    )
    review_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    quick_notes: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    quality_score: Optional[float] = Field(default=None)  # 0-10 scale
    is_duplicate: bool = Field(default=False)
    duplicate_of_page_id: Optional[int] = Field(default=None)
    tags: List[str] = Field(default=[], sa_column=Column(JSON))


class Page(PageBase, table=True):
    """Page model for database"""
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint('domain_id', 'original_url', 'unix_timestamp', name='uq_pages_domain_url_ts'),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    domain_id: int = Field(foreign_key="domains.id")
    
    # Content processing
    content_hash: Optional[str] = Field(default=None, sa_column=Column(String(64)))
    processed: bool = Field(default=False)
    indexed: bool = Field(default=False)
    
    # Error tracking
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    retry_count: int = Field(default=0)
    last_retry_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Semantic search embeddings
    content_embedding: Optional[str] = Field(default=None, sa_column=Column(Text))
    embedding_updated_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Review tracking fields
    reviewed_by: Optional[int] = Field(default=None, foreign_key="users.id")
    reviewed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Timestamps
    scraped_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
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
    
    # Recommend a composite uniqueness at the DB level to prevent duplicates
    # Note: SQLModel doesn't directly expose __table_args__ via Field. Ensure Alembic migration adds this:
    # UniqueConstraint('domain_id', 'original_url', 'unix_timestamp', name='uq_pages_domain_url_ts')
    
    # Field validators for enums
    @field_validator('review_status', mode='before')
    @classmethod
    def validate_review_status(cls, v):
        """Convert string values to PageReviewStatus enum"""
        if isinstance(v, str):
            try:
                return PageReviewStatus(v)
            except ValueError:
                return PageReviewStatus.UNREVIEWED
        return v
    
    @field_validator('page_category', mode='before')
    @classmethod
    def validate_page_category(cls, v):
        """Convert string values to PageCategory enum"""
        if isinstance(v, str):
            try:
                return PageCategory(v)
            except ValueError:
                return None
        return v
    
    @field_validator('priority_level', mode='before')
    @classmethod
    def validate_priority_level(cls, v):
        """Convert string values to PagePriority enum"""
        if isinstance(v, str):
            try:
                return PagePriority(v)
            except ValueError:
                return PagePriority.MEDIUM
        return v
    
    @field_serializer('review_status')
    def serialize_review_status(self, value):
        """Serialize PageReviewStatus enum to string"""
        if isinstance(value, PageReviewStatus):
            return value.value
        return value
    
    @field_serializer('page_category')
    def serialize_page_category(self, value):
        """Serialize PageCategory enum to string"""
        if isinstance(value, PageCategory):
            return value.value
        return value
    
    @field_serializer('priority_level')
    def serialize_priority_level(self, value):
        """Serialize PagePriority enum to string"""
        if isinstance(value, PagePriority):
            return value.value
        return value
    
    # Relationships
    starred_by: List["StarredItem"] = Relationship(back_populates="page")
    extracted_entities: List["ExtractedEntity"] = Relationship(back_populates="page")
    content_extractions: List["ContentExtraction"] = Relationship(back_populates="page")


# Pydantic schemas for API
class ProjectCreateSimplified(SQLModel):
    """Schema for creating projects with minimal user input"""
    process_documents: bool = Field(default=True)
    enable_attachment_download: bool = Field(default=True)
    
    # LangExtract Configuration
    langextract_enabled: bool = Field(default=False)
    langextract_provider: LangExtractProvider = Field(default=LangExtractProvider.DISABLED)
    langextract_model: Optional[str] = Field(default=None)
    langextract_estimated_cost_per_1k: Optional[float] = Field(default=None)
    
    @field_validator('langextract_provider', mode='before')
    @classmethod
    def validate_langextract_provider(cls, v):
        """Convert string values to LangExtractProvider enum"""
        if isinstance(v, str):
            try:
                return LangExtractProvider(v)
            except ValueError:
                # If invalid string, return default
                return LangExtractProvider.DISABLED
        elif isinstance(v, LangExtractProvider):
            return v
        return v
    
    @field_serializer('langextract_provider')
    def serialize_langextract_provider(self, value):
        """Serialize LangExtractProvider enum to string"""
        if isinstance(value, LangExtractProvider):
            return value.value
        return value


class ProjectCreate(ProjectBase):
    """Schema for creating projects (full)"""
    # Inherits all fields from ProjectBase including LangExtract configuration
    pass


class ProjectUpdate(SQLModel):
    """Schema for updating projects"""
    name: Optional[str] = None
    description: Optional[str] = None
    process_documents: Optional[bool] = None
    enable_attachment_download: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


class ProjectRead(ProjectBase):
    """Schema for reading projects"""
    id: int
    user_id: int
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class ProjectReadWithStats(ProjectRead):
    """Project schema with statistics"""
    domain_count: int = 0
    total_pages: int = 0
    scraped_pages: int = 0
    last_scraped: Optional[datetime] = None


class DomainCreate(SQLModel):
    """Schema for creating domains"""
    # Support both 'domain' and 'domain_name' field names
    domain: Optional[str] = Field(default=None)
    domain_name: Optional[str] = Field(default=None)
    
    match_type: MatchType = Field(default=MatchType.DOMAIN)
    url_path: Optional[str] = Field(default=None)
    max_pages: Optional[int] = Field(default=None)
    active: bool = Field(default=True)
    
    # Date range for scraping (ISO format strings)
    from_date: Optional[str] = Field(default=None, description="Start date for scraping (ISO format: YYYY-MM-DD)")
    to_date: Optional[str] = Field(default=None, description="End date for scraping (ISO format: YYYY-MM-DD)")
    
    # Additional fields for domain creation
    include_subdomains: bool = Field(default=True)
    exclude_patterns: Optional[List[str]] = Field(default_factory=list)
    include_patterns: Optional[List[str]] = Field(default_factory=list)
    
    @validator('domain_name', pre=True, always=True)
    def set_domain_name(cls, v, values):
        """Use 'domain' if 'domain_name' is not provided"""
        if v is None and 'domain' in values and values['domain']:
            return values['domain']
        return v
    
    @validator('domain_name')
    def validate_domain_name(cls, v):
        """Validate domain name is provided"""
        if not v:
            raise ValueError('Either domain or domain_name must be provided')
        return v
    
    model_config = {"populate_by_name": True}


class DomainUpdate(SQLModel):
    """Schema for updating domains"""
    domain_name: Optional[str] = None
    match_type: Optional[MatchType] = None
    url_path: Optional[str] = None
    max_pages: Optional[int] = None
    active: Optional[bool] = None


class DomainRead(DomainBase):
    """Schema for reading domains"""
    id: int
    project_id: int
    status: DomainStatus
    total_pages: int
    scraped_pages: int
    failed_pages: int
    last_scraped: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# Page management schemas
class PageReview(SQLModel):
    """Schema for reviewing pages"""
    review_status: PageReviewStatus
    page_category: Optional[PageCategory] = None
    priority_level: PagePriority = PagePriority.MEDIUM
    review_notes: Optional[str] = None
    quick_notes: Optional[str] = None
    quality_score: Optional[float] = None
    tags: Optional[List[str]] = None


class PageBulkAction(SQLModel):
    """Schema for bulk page actions"""
    page_ids: List[int]
    action: str  # 'star', 'unstar', 'mark_irrelevant', 'mark_relevant', 'set_category', 'add_tags', 'remove_tags'
    review_status: Optional[PageReviewStatus] = None
    page_category: Optional[PageCategory] = None
    priority_level: Optional[PagePriority] = None
    tags: Optional[List[str]] = None
    quick_notes: Optional[str] = None


class PageRead(PageBase):
    """Schema for reading pages with management fields"""
    id: int
    domain_id: int
    processed: bool
    indexed: bool
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Computed fields
    is_starred: bool = False
    star_count: int = 0


class PageReadWithStarring(PageRead):
    """Page schema with starring information for authenticated users"""
    user_starred: bool = False
    user_star_tags: List[str] = []
    user_star_notes: str = ""


class TagSuggestion(SQLModel):
    """Schema for tag suggestions"""
    tag: str
    frequency: int
    category: Optional[str] = None
    confidence: float = 0.0