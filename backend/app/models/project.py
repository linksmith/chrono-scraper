"""
Project and related models
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING, Dict, Any, Tuple
from sqlmodel import SQLModel, Field, Column, String, DateTime, Text, Relationship, JSON
from sqlalchemy import func, Index
from enum import Enum
from pydantic import validator, field_validator, field_serializer

if TYPE_CHECKING:
    from .library import StarredItem, SearchHistory
    from .entities import ExtractedEntity
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


class IncrementalMode(str, Enum):
    """Incremental scraping mode enumeration"""
    TIME_BASED = "time_based"  # Scrape based on date ranges and gaps
    CONTENT_BASED = "content_based"  # Scrape based on content changes/additions
    HYBRID = "hybrid"  # Combine both time and content-based approaches


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


class ArchiveSource(str, Enum):
    """Archive source enumeration - matches frontend TypeScript interface"""
    WAYBACK_MACHINE = "wayback"
    COMMON_CRAWL = "commoncrawl"
    HYBRID = "hybrid"








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
    
    # Archive Source Configuration
    archive_source: ArchiveSource = Field(default=ArchiveSource.COMMON_CRAWL, sa_column=Column(String(20)))
    fallback_enabled: bool = Field(default=True)  # Enable fallback behavior for hybrid mode
    archive_config: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))  # Source-specific configuration
    
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
    
    @field_validator('archive_source', mode='before')
    @classmethod
    def validate_archive_source(cls, v):
        """Convert string values to ArchiveSource enum"""
        if v is None:
            return ArchiveSource.WAYBACK_MACHINE
        elif isinstance(v, str):
            try:
                return ArchiveSource(v)
            except ValueError:
                # If invalid string, return default
                return ArchiveSource.COMMON_CRAWL
        elif isinstance(v, ArchiveSource):
            return v
        return ArchiveSource.WAYBACK_MACHINE
    
    @field_serializer('archive_source')
    def serialize_archive_source(self, value):
        """Serialize ArchiveSource enum to string"""
        if isinstance(value, ArchiveSource):
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
    
    # Key rotation tracking fields
    key_created_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    key_last_rotated: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    key_rotation_enabled: bool = Field(default=True)
    
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
    __table_args__ = (
        Index('ix_domains_incremental_enabled', 'incremental_enabled'),
        Index('ix_domains_next_incremental_check', 'next_incremental_check'),
        Index('ix_domains_last_incremental_check', 'last_incremental_check'),
        Index('ix_domains_project_incremental', 'project_id', 'incremental_enabled'),
    )
    
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
    
    @field_validator('incremental_mode', mode='before')
    @classmethod
    def validate_incremental_mode(cls, v):
        """Convert string values to IncrementalMode enum"""
        if isinstance(v, str):
            try:
                return IncrementalMode(v)
            except ValueError:
                return IncrementalMode.TIME_BASED
        return v
    
    @field_serializer('incremental_mode')
    def serialize_incremental_mode(self, value):
        """Serialize IncrementalMode enum to string"""
        if isinstance(value, IncrementalMode):
            return value.value
        return value
    
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
    
    # Incremental scraping configuration
    incremental_enabled: bool = Field(default=False)
    incremental_mode: IncrementalMode = Field(
        default=IncrementalMode.TIME_BASED,
        sa_column=Column(String(20))
    )
    overlap_days: int = Field(default=7)  # Days of overlap to ensure no gaps
    max_gap_days: int = Field(default=30)  # Maximum gap size before flagging
    backfill_enabled: bool = Field(default=True)  # Automatically fill detected gaps
    
    # Coverage tracking fields (stored as JSON)
    scraped_date_ranges: List[Tuple[str, str]] = Field(
        default_factory=list, 
        sa_column=Column(JSON),
        description="List of [start_date, end_date] tuples in YYYY-MM-DD format"
    )
    coverage_percentage: Optional[float] = Field(
        default=None,
        description="Estimated coverage percentage of available content"
    )
    known_gaps: List[Dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="List of detected gaps with metadata"
    )
    last_incremental_check: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last time incremental check was performed"
    )
    next_incremental_check: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Next scheduled incremental check"
    )
    
    # Incremental statistics
    total_incremental_runs: int = Field(default=0)
    successful_incremental_runs: int = Field(default=0)
    failed_incremental_runs: int = Field(default=0)
    gaps_detected: int = Field(default=0)
    gaps_filled: int = Field(default=0)
    new_content_discovered: int = Field(default=0)
    
    # Performance tracking for incremental scraping
    avg_incremental_runtime: Optional[float] = Field(
        default=None,
        description="Average runtime for incremental checks in seconds"
    )
    last_incremental_runtime: Optional[float] = Field(
        default=None,
        description="Runtime of last incremental check in seconds"
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
    
    # Archive Source Configuration
    archive_source: ArchiveSource = Field(default=ArchiveSource.COMMON_CRAWL)
    fallback_enabled: bool = Field(default=True)
    archive_config: Optional[Dict[str, Any]] = Field(default=None)
    
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
    
    @field_validator('archive_source', mode='before')
    @classmethod
    def validate_archive_source(cls, v):
        """Convert string values to ArchiveSource enum"""
        if v is None:
            return ArchiveSource.WAYBACK_MACHINE
        elif isinstance(v, str):
            try:
                return ArchiveSource(v)
            except ValueError:
                # If invalid string, return default
                return ArchiveSource.COMMON_CRAWL
        elif isinstance(v, ArchiveSource):
            return v
        return ArchiveSource.WAYBACK_MACHINE
    
    @field_serializer('archive_source')
    def serialize_archive_source(self, value):
        """Serialize ArchiveSource enum to string"""
        if isinstance(value, ArchiveSource):
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
    
    # LangExtract Configuration (for updates)
    langextract_enabled: Optional[bool] = None
    langextract_provider: Optional[LangExtractProvider] = None
    langextract_model: Optional[str] = None
    langextract_estimated_cost_per_1k: Optional[float] = None
    
    # Archive Source Configuration (for updates)
    archive_source: Optional[ArchiveSource] = None
    fallback_enabled: Optional[bool] = None
    archive_config: Optional[Dict[str, Any]] = None


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


class TagSuggestion(SQLModel):
    """Schema for tag suggestions"""
    tag: str
    frequency: int
    category: Optional[str] = None
    confidence: float = 0.0


# DEPRECATED: Legacy Page model has been removed
# Import enums from shared pages for backward compatibility

# This is a placeholder to prevent import errors during transition
# Use the shared pages system (PageV2, ProjectPage) instead
class Page:
    """
    DEPRECATED: This is a placeholder for the removed legacy Page model.
    
    The legacy Page model has been completely removed in favor of the shared pages system.
    This placeholder exists only to prevent import errors during the transition period.
    
    For page functionality, use:
    - PageV2: The new shared page model
    - ProjectPage: Many-to-many relationship between projects and shared pages
    - /api/v1/shared-pages/ endpoints: API for shared pages functionality
    """
    
    def __init__(self, *args, **kwargs):
        raise DeprecationWarning(
            "The legacy Page model has been removed. "
            "Use the shared pages system (PageV2, ProjectPage) instead."
        )
    
    @classmethod
    def __class_getitem__(cls, item):
        # Allow type annotations to work without errors
        return cls


class ArchiveSourceChangeLog(SQLModel, table=True):
    """Archive source change audit log for tracking configuration changes"""
    __tablename__ = "archive_source_change_logs"
    __table_args__ = (
        Index('ix_archive_changes_project_user', 'project_id', 'user_id'),
        Index('ix_archive_changes_timestamp', 'change_timestamp'),
        Index('ix_archive_changes_success', 'success'),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="projects.id")
    user_id: int = Field(foreign_key="users.id")
    
    # Archive source change details
    old_archive_source: ArchiveSource = Field(sa_column=Column(String(20)))
    new_archive_source: ArchiveSource = Field(sa_column=Column(String(20)))
    old_fallback_enabled: bool = Field(default=True)
    new_fallback_enabled: bool = Field(default=True)
    old_config: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    new_config: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Change metadata
    change_reason: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    impact_acknowledged: bool = Field(default=False)
    change_timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    
    # Result tracking
    success: bool = Field(default=True)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Rollback tracking
    rollback_available: bool = Field(default=True)
    rollback_deadline: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    rollback_applied: bool = Field(default=False)
    rollback_timestamp: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    rollback_reason: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    
    # Additional context
    session_id: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    ip_address: Optional[str] = Field(default=None, sa_column=Column(String(45)))
    user_agent: Optional[str] = Field(default=None, sa_column=Column(String(512)))
    
    @field_validator('old_archive_source', 'new_archive_source', mode='before')
    @classmethod
    def validate_archive_sources(cls, v):
        """Convert string values to ArchiveSource enum"""
        if isinstance(v, str):
            try:
                return ArchiveSource(v)
            except ValueError:
                return ArchiveSource.COMMON_CRAWL
        elif isinstance(v, ArchiveSource):
            return v
        return ArchiveSource.WAYBACK_MACHINE
    
    @field_serializer('old_archive_source', 'new_archive_source')
    def serialize_archive_sources(self, value):
        """Serialize ArchiveSource enum to string"""
        if isinstance(value, ArchiveSource):
            return value.value
        return value