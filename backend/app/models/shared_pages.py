"""
Shared pages architecture models with many-to-many relationships
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING, Dict, Any
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text, Integer, ForeignKey, Relationship, JSON
from sqlalchemy import func, UniqueConstraint, BigInteger, Numeric
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import uuid
from enum import Enum

if TYPE_CHECKING:
    from .project import Project, Domain
    from .user import User


class ScrapeStatus(str, Enum):
    """CDX scraping status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class PageReviewStatus(str, Enum):
    """Page review status enumeration"""
    PENDING = "pending"
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


class PageV2Base(SQLModel):
    """Base model for shared pages"""
    url: str = Field(sa_column=Column(Text))
    unix_timestamp: int = Field(sa_column=Column(BigInteger))
    content_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    content: Optional[str] = Field(default=None, sa_column=Column(Text))
    markdown_content: Optional[str] = Field(default=None, sa_column=Column(Text))
    extracted_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    quality_score: Optional[float] = Field(default=None, sa_column=Column(Numeric(3, 2)))
    
    # Enhanced metadata fields
    title: Optional[str] = Field(default=None, sa_column=Column(String(500)))
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
    mime_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    status_code: Optional[int] = Field(default=None)
    capture_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class PageV2(PageV2Base, table=True):
    """Independent pages table for shared content"""
    __tablename__ = "pages_v2"
    __table_args__ = (
        UniqueConstraint('url', 'unix_timestamp', name='uq_pages_v2_url_timestamp'),
    )
    
    id: Optional[uuid.UUID] = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True)
    )
    
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
    project_associations: List["ProjectPage"] = Relationship(back_populates="page")
    cdx_registry_entries: List["CDXPageRegistry"] = Relationship(back_populates="page")


class ProjectPageBase(SQLModel):
    """Base model for project-page associations"""
    review_status: PageReviewStatus = Field(
        default=PageReviewStatus.PENDING,
        sa_column=Column(String(50))
    )
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    tags: List[str] = Field(default_factory=list, sa_column=Column(ARRAY(String)))
    is_starred: bool = Field(default=False)
    
    # Page management fields (project-specific)
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
    is_duplicate: bool = Field(default=False)
    duplicate_of_page_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(UUID(as_uuid=True))
    )


class ProjectPage(ProjectPageBase, table=True):
    """Junction table for many-to-many project-page relationship"""
    __tablename__ = "project_pages"
    __table_args__ = (
        UniqueConstraint('project_id', 'page_id', name='uq_project_pages_project_page'),
    )
    
    id: Optional[uuid.UUID] = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True)
    )
    project_id: int = Field(foreign_key="projects.id")
    page_id: uuid.UUID = Field(
        sa_column=Column(UUID(as_uuid=True), ForeignKey("pages_v2.id"))
    )
    domain_id: Optional[int] = Field(default=None, foreign_key="domains.id")
    
    # Metadata
    added_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    added_by: Optional[int] = Field(default=None, foreign_key="users.id")
    
    # Review tracking
    reviewed_by: Optional[int] = Field(default=None, foreign_key="users.id")
    reviewed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Relationships
    project: "Project" = Relationship()
    page: PageV2 = Relationship(back_populates="project_associations")
    domain: Optional["Domain"] = Relationship()
    
    # User relationships with explicit foreign key specification
    # Temporarily commented out to fix SQLAlchemy initialization
    # added_by_user: Optional["User"] = Relationship(
    #     back_populates="added_project_pages",
    #     sa_relationship_kwargs={
    #         "foreign_keys": "ProjectPage.added_by",
    #         "post_update": True
    #     }
    # )
    # reviewed_by_user: Optional["User"] = Relationship(
    #     back_populates="reviewed_project_pages", 
    #     sa_relationship_kwargs={
    #         "foreign_keys": "ProjectPage.reviewed_by",
    #         "post_update": True
    #     }
    # )


class CDXPageRegistryBase(SQLModel):
    """Base model for CDX page registry"""
    url: str = Field(sa_column=Column(Text))
    unix_timestamp: int = Field(sa_column=Column(BigInteger))
    scrape_status: ScrapeStatus = Field(sa_column=Column(String(50)))


class CDXPageRegistry(CDXPageRegistryBase, table=True):
    """Registry for CDX discovery and deduplication"""
    __tablename__ = "cdx_page_registry"
    __table_args__ = (
        UniqueConstraint('url', 'unix_timestamp', name='uq_cdx_registry_url_timestamp'),
    )
    
    id: Optional[uuid.UUID] = Field(
        default_factory=uuid.uuid4,
        sa_column=Column(UUID(as_uuid=True), primary_key=True)
    )
    page_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column(UUID(as_uuid=True), ForeignKey("pages_v2.id"))
    )
    first_seen_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    created_by_project_id: Optional[int] = Field(
        default=None,
        foreign_key="projects.id"
    )
    
    # Relationships
    page: Optional[PageV2] = Relationship(back_populates="cdx_registry_entries")
    created_by_project: Optional["Project"] = Relationship()


# API schemas
class PageV2Create(PageV2Base):
    """Schema for creating pages"""
    pass


class PageV2Read(PageV2Base):
    """Schema for reading pages"""
    id: uuid.UUID
    processed: bool
    indexed: bool
    created_at: datetime
    updated_at: datetime


class PageV2ReadWithProjects(PageV2Read):
    """Page schema with project associations"""
    project_associations: List["ProjectPageRead"] = []


class ProjectPageCreate(ProjectPageBase):
    """Schema for creating project-page associations"""
    project_id: int
    page_id: uuid.UUID
    domain_id: Optional[int] = None
    added_by: Optional[int] = None


class ProjectPageRead(ProjectPageBase):
    """Schema for reading project-page associations"""
    id: uuid.UUID
    project_id: int
    page_id: uuid.UUID
    domain_id: Optional[int] = None
    added_at: datetime
    added_by: Optional[int] = None
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None


class ProjectPageUpdate(SQLModel):
    """Schema for updating project-page associations"""
    review_status: Optional[PageReviewStatus] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    is_starred: Optional[bool] = None
    page_category: Optional[PageCategory] = None
    priority_level: Optional[PagePriority] = None
    review_notes: Optional[str] = None
    quick_notes: Optional[str] = None
    is_duplicate: Optional[bool] = None
    duplicate_of_page_id: Optional[uuid.UUID] = None


class CDXPageRegistryCreate(CDXPageRegistryBase):
    """Schema for creating CDX registry entries"""
    page_id: Optional[uuid.UUID] = None
    created_by_project_id: Optional[int] = None


class CDXPageRegistryRead(CDXPageRegistryBase):
    """Schema for reading CDX registry entries"""
    id: uuid.UUID
    page_id: Optional[uuid.UUID] = None
    first_seen_at: datetime
    created_by_project_id: Optional[int] = None


class ProcessingStats(SQLModel):
    """Statistics for CDX processing operations"""
    pages_linked: int = 0
    pages_to_scrape: int = 0
    pages_already_processing: int = 0
    pages_failed: int = 0
    total_processed: int = 0