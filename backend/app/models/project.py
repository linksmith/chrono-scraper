"""
Project and related models
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text, Integer, ForeignKey, Relationship
from sqlalchemy import func
from enum import Enum

if TYPE_CHECKING:
    from .library import StarredItem, SearchHistory
    from .entities import ExtractedEntity
    from .extraction_schemas import ContentExtraction


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


class ProjectBase(SQLModel):
    """Base project model"""
    name: str = Field(sa_column=Column(String(200)))
    description: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    index_name: Optional[str] = Field(default=None, sa_column=Column(String(200)))
    process_documents: bool = Field(default=True)


class Project(ProjectBase, table=True):
    """Project model for database"""
    __tablename__ = "projects"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    
    # Meilisearch configuration
    index_search_key: Optional[str] = Field(default=None, sa_column=Column(String(256)))
    index_search_key_uid: Optional[str] = Field(default=None, sa_column=Column(String(256)))
    
    # Status
    status: ProjectStatus = Field(
        default=ProjectStatus.NO_INDEX,
        sa_column=Column(String(16))
    )
    
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
    
    # Scraping statistics
    total_pages: int = Field(default=0)
    scraped_pages: int = Field(default=0)
    failed_pages: int = Field(default=0)
    last_scraped: Optional[datetime] = Field(
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
    """Base page model"""
    original_url: str = Field(sa_column=Column(Text))
    wayback_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    title: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    content: Optional[str] = Field(default=None, sa_column=Column(Text))
    unix_timestamp: Optional[int] = Field(default=None)
    mime_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    status_code: Optional[int] = Field(default=None)
    
    # Content extraction fields
    extracted_title: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    extracted_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    extracted_content: Optional[str] = Field(default=None, sa_column=Column(Text))
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


class Page(PageBase, table=True):
    """Page model for database"""
    __tablename__ = "pages"
    
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
    
    # Relationships
    starred_by: List["StarredItem"] = Relationship(back_populates="page")
    extracted_entities: List["ExtractedEntity"] = Relationship(back_populates="page")
    content_extractions: List["ContentExtraction"] = Relationship(back_populates="page")


# Pydantic schemas for API
class ProjectCreate(ProjectBase):
    """Schema for creating projects"""
    pass


class ProjectUpdate(SQLModel):
    """Schema for updating projects"""
    name: Optional[str] = None
    description: Optional[str] = None
    process_documents: Optional[bool] = None


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


class DomainCreate(DomainBase):
    """Schema for creating domains"""
    pass


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