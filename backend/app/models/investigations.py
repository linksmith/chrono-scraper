"""
OSINT investigation management models for Phase 8
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text, Integer, ForeignKey, Relationship, JSON
from sqlalchemy import func
from enum import Enum

if TYPE_CHECKING:
    from .user import User
    from .project import Page


class InvestigationStatus(str, Enum):
    """Investigation status enumeration"""
    DRAFT = "draft"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    CANCELLED = "cancelled"


class InvestigationPriority(str, Enum):
    """Investigation priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class EvidenceType(str, Enum):
    """Evidence type enumeration"""
    WEBPAGE = "webpage"
    DOCUMENT = "document"
    IMAGE = "image"
    VIDEO = "video"
    SOCIAL_MEDIA = "social_media"
    DATABASE_RECORD = "database_record"
    NETWORK_DATA = "network_data"
    METADATA = "metadata"
    COMMUNICATION = "communication"
    FINANCIAL = "financial"
    LEGAL = "legal"
    OTHER = "other"


class EvidenceStatus(str, Enum):
    """Evidence verification status"""
    UNVERIFIED = "unverified"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    COMPROMISED = "compromised"
    ARCHIVED = "archived"


class InvestigationBase(SQLModel):
    """Base investigation model"""
    title: str = Field(sa_column=Column(String(300)))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Investigation metadata
    case_number: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    investigation_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    classification: Optional[str] = Field(default="internal", sa_column=Column(String(50)))
    
    # Target information
    target_entities: List[str] = Field(default=[], sa_column=Column(JSON))
    target_domains: List[str] = Field(default=[], sa_column=Column(JSON))
    target_keywords: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Investigation scope
    geographical_scope: List[str] = Field(default=[], sa_column=Column(JSON))
    temporal_scope_start: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    temporal_scope_end: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Investigation settings
    is_confidential: bool = Field(default=False)
    is_collaborative: bool = Field(default=False)
    auto_archive_days: Optional[int] = Field(default=None)
    
    # Progress tracking
    completion_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    estimated_hours: Optional[int] = Field(default=None)
    actual_hours: float = Field(default=0.0)
    
    # Tags and categorization
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    custom_fields: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class Investigation(InvestigationBase, table=True):
    """Investigation model for database"""
    __tablename__ = "investigations"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    
    status: InvestigationStatus = Field(default=InvestigationStatus.DRAFT, sa_column=Column(String(50)))
    priority: InvestigationPriority = Field(default=InvestigationPriority.MEDIUM, sa_column=Column(String(50)))
    
    # Assignment and collaboration
    assigned_users: List[int] = Field(default=[], sa_column=Column(JSON))
    lead_investigator_id: Optional[int] = Field(default=None, foreign_key="users.id")
    
    # Timeline tracking
    started_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    deadline: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Analytics
    evidence_count: int = Field(default=0)
    timeline_events_count: int = Field(default=0)
    findings_count: int = Field(default=0)
    
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
    user: "User" = Relationship(
        back_populates="investigations",
        sa_relationship_kwargs={"foreign_keys": "[Investigation.user_id]"}
    )
    lead_investigator: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Investigation.lead_investigator_id]"}
    )
    evidence: List["Evidence"] = Relationship(back_populates="investigation")
    timeline_events: List["InvestigationTimeline"] = Relationship(back_populates="investigation")
    findings: List["InvestigationFinding"] = Relationship(back_populates="investigation")
    page_comparisons: List["PageComparison"] = Relationship(back_populates="investigation")


class EvidenceBase(SQLModel):
    """Base evidence model"""
    title: str = Field(sa_column=Column(String(300)))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Evidence source information
    source_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    source_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    collection_method: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    
    # Evidence content
    content_hash: Optional[str] = Field(default=None, sa_column=Column(String(128)))
    file_path: Optional[str] = Field(default=None, sa_column=Column(Text))
    file_size: Optional[int] = Field(default=None)
    mime_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    
    # Evidence metadata
    evidence_metadata: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    extracted_entities: List[str] = Field(default=[], sa_column=Column(JSON))
    keywords: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Chain of custody
    custody_log: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSON))
    
    # Relevance and importance
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    
    # Tags and notes
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))


class Evidence(EvidenceBase, table=True):
    """Evidence model for database"""
    __tablename__ = "evidence"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    investigation_id: int = Field(foreign_key="investigations.id")
    user_id: int = Field(foreign_key="users.id")
    page_id: Optional[int] = Field(default=None, foreign_key="pages.id")
    
    evidence_type: EvidenceType = Field(sa_column=Column(String(50)))
    status: EvidenceStatus = Field(default=EvidenceStatus.UNVERIFIED, sa_column=Column(String(50)))
    
    # Verification information
    verified_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    verified_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    verification_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Discovery information
    discovered_at: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=True)))
    discovery_method: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    
    # Location and temporal data
    geographical_location: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    temporal_reference: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    
    # Relationships
    investigation: Investigation = Relationship(back_populates="evidence")
    user: "User" = Relationship(
        back_populates="evidence",
        sa_relationship_kwargs={"foreign_keys": "[Evidence.user_id]"}
    )
    page: Optional["Page"] = Relationship()
    verified_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Evidence.verified_by_user_id]"}
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


class PageComparisonBase(SQLModel):
    """Base page comparison model for tracking website changes"""
    comparison_title: str = Field(sa_column=Column(String(300)))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Comparison configuration
    comparison_fields: List[str] = Field(default=[], sa_column=Column(JSON))
    ignore_fields: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # Comparison results
    differences_found: bool = Field(default=False)
    similarity_score: float = Field(default=1.0, ge=0.0, le=1.0)
    change_summary: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    detailed_diff: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Analysis metadata
    analysis_method: Optional[str] = Field(default="automated", sa_column=Column(String(100)))
    analysis_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    
    # Significance indicators
    is_significant_change: bool = Field(default=False)
    significance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    change_categories: List[str] = Field(default=[], sa_column=Column(JSON))


class PageComparison(PageComparisonBase, table=True):
    """Page comparison model for tracking website changes over time"""
    __tablename__ = "page_comparisons"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    investigation_id: int = Field(foreign_key="investigations.id")
    user_id: int = Field(foreign_key="users.id")
    
    # Pages being compared
    baseline_page_id: int = Field(foreign_key="pages.id")
    target_page_id: int = Field(foreign_key="pages.id")
    
    # Comparison execution
    comparison_date: datetime = Field(default_factory=datetime.utcnow, sa_column=Column(DateTime(timezone=True)))
    execution_time_ms: Optional[int] = Field(default=None)
    
    # Review status
    is_reviewed: bool = Field(default=False)
    reviewed_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    reviewed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    review_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    
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
    investigation: Investigation = Relationship(back_populates="page_comparisons")
    user: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[PageComparison.user_id]"}
    )
    baseline_page: "Page" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[PageComparison.baseline_page_id]"}
    )
    target_page: "Page" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[PageComparison.target_page_id]"}
    )
    reviewed_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[PageComparison.reviewed_by_user_id]"}
    )


class InvestigationTimelineBase(SQLModel):
    """Base investigation timeline model"""
    event_title: str = Field(sa_column=Column(String(300)))
    event_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Event temporal data
    event_date: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    event_end_date: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    is_estimated_date: bool = Field(default=False)
    date_precision: Optional[str] = Field(default="exact", sa_column=Column(String(50)))  # exact, day, month, year
    
    # Event categorization
    event_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    event_category: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    significance_level: int = Field(default=3, ge=1, le=5)  # 1=low, 5=critical
    
    # Event location and context
    location: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    geographical_coordinates: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    
    # Event sources and verification
    source_urls: List[str] = Field(default=[], sa_column=Column(JSON))
    source_reliability: float = Field(default=0.5, ge=0.0, le=1.0)
    verification_status: Optional[str] = Field(default="unverified", sa_column=Column(String(50)))
    
    # Associated data
    associated_entities: List[str] = Field(default=[], sa_column=Column(JSON))
    event_metadata: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Display and organization
    display_color: Optional[str] = Field(default=None, sa_column=Column(String(20)))
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    is_milestone: bool = Field(default=False)
    is_public: bool = Field(default=False)


class InvestigationTimeline(InvestigationTimelineBase, table=True):
    """Investigation timeline model for tracking events and milestones"""
    __tablename__ = "investigation_timelines"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    investigation_id: int = Field(foreign_key="investigations.id")
    user_id: int = Field(foreign_key="users.id")
    
    # Evidence connections
    evidence_ids: List[int] = Field(default=[], sa_column=Column(JSON))
    page_id: Optional[int] = Field(default=None, foreign_key="pages.id")
    
    # Analysis and correlation
    correlation_score: float = Field(default=0.0, ge=0.0, le=1.0)
    correlation_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Timeline ordering
    sequence_number: Optional[int] = Field(default=None)
    parent_event_id: Optional[int] = Field(default=None, foreign_key="investigation_timelines.id")
    
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
    investigation: Investigation = Relationship(back_populates="timeline_events")
    user: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[InvestigationTimeline.user_id]"}
    )
    page: Optional["Page"] = Relationship()
    parent_event: Optional["InvestigationTimeline"] = Relationship(
        back_populates="child_events",
        sa_relationship_kwargs={"remote_side": "InvestigationTimeline.id"}
    )
    child_events: List["InvestigationTimeline"] = Relationship(
        back_populates="parent_event",
        sa_relationship_kwargs={"remote_side": "InvestigationTimeline.parent_event_id"}
    )


class InvestigationFindingBase(SQLModel):
    """Base investigation finding model"""
    finding_title: str = Field(sa_column=Column(String(300)))
    finding_description: str = Field(sa_column=Column(Text))
    
    # Finding categorization
    finding_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    severity_level: int = Field(default=3, ge=1, le=5)  # 1=low, 5=critical
    confidence_level: float = Field(default=0.5, ge=0.0, le=1.0)
    
    # Finding content
    key_points: List[str] = Field(default=[], sa_column=Column(JSON))
    implications: Optional[str] = Field(default=None, sa_column=Column(Text))
    recommendations: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Supporting information
    supporting_evidence_ids: List[int] = Field(default=[], sa_column=Column(JSON))
    related_timeline_event_ids: List[int] = Field(default=[], sa_column=Column(JSON))
    
    # Validation and review
    is_validated: bool = Field(default=False)
    validation_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Impact assessment
    impact_score: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_assessment: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Tags and metadata
    tags: List[str] = Field(default=[], sa_column=Column(JSON))
    custom_attributes: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class InvestigationFinding(InvestigationFindingBase, table=True):
    """Investigation finding model for documenting conclusions and insights"""
    __tablename__ = "investigation_findings"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    investigation_id: int = Field(foreign_key="investigations.id")
    user_id: int = Field(foreign_key="users.id")
    
    # Review and approval
    reviewed_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    reviewed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    review_status: Optional[str] = Field(default="pending", sa_column=Column(String(50)))
    
    # Publication and sharing
    is_publishable: bool = Field(default=False)
    publication_restrictions: Optional[str] = Field(default=None, sa_column=Column(Text))
    
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
    investigation: Investigation = Relationship(back_populates="findings")
    user: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[InvestigationFinding.user_id]"}
    )
    reviewed_by: Optional["User"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[InvestigationFinding.reviewed_by_user_id]"}
    )


# Pydantic schemas for API
class InvestigationCreate(InvestigationBase):
    """Schema for creating investigations"""
    pass


class InvestigationUpdate(SQLModel):
    """Schema for updating investigations"""
    title: Optional[str] = None
    description: Optional[str] = None
    investigation_type: Optional[str] = None
    classification: Optional[str] = None
    target_entities: Optional[List[str]] = None
    target_domains: Optional[List[str]] = None
    target_keywords: Optional[List[str]] = None
    geographical_scope: Optional[List[str]] = None
    temporal_scope_start: Optional[datetime] = None
    temporal_scope_end: Optional[datetime] = None
    status: Optional[InvestigationStatus] = None
    priority: Optional[InvestigationPriority] = None
    is_confidential: Optional[bool] = None
    is_collaborative: Optional[bool] = None
    deadline: Optional[datetime] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None


class InvestigationRead(InvestigationBase):
    """Schema for reading investigations"""
    id: int
    user_id: int
    status: InvestigationStatus
    priority: InvestigationPriority
    lead_investigator_id: Optional[int]
    evidence_count: int
    timeline_events_count: int
    findings_count: int
    started_at: Optional[datetime]
    deadline: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class EvidenceCreate(EvidenceBase):
    """Schema for creating evidence"""
    investigation_id: int
    evidence_type: EvidenceType
    page_id: Optional[int] = None


class EvidenceRead(EvidenceBase):
    """Schema for reading evidence"""
    id: int
    investigation_id: int
    user_id: int
    page_id: Optional[int]
    evidence_type: EvidenceType
    status: EvidenceStatus
    verified_by_user_id: Optional[int]
    verified_at: Optional[datetime]
    discovered_at: datetime
    created_at: datetime
    updated_at: datetime


class PageComparisonCreate(PageComparisonBase):
    """Schema for creating page comparisons"""
    investigation_id: int
    baseline_page_id: int
    target_page_id: int


class PageComparisonRead(PageComparisonBase):
    """Schema for reading page comparisons"""
    id: int
    investigation_id: int
    user_id: int
    baseline_page_id: int
    target_page_id: int
    comparison_date: datetime
    execution_time_ms: Optional[int]
    is_reviewed: bool
    reviewed_by_user_id: Optional[int]
    reviewed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class InvestigationTimelineCreate(InvestigationTimelineBase):
    """Schema for creating timeline events"""
    investigation_id: int
    evidence_ids: List[int] = []
    page_id: Optional[int] = None


class InvestigationTimelineRead(InvestigationTimelineBase):
    """Schema for reading timeline events"""
    id: int
    investigation_id: int
    user_id: int
    evidence_ids: List[int]
    page_id: Optional[int]
    sequence_number: Optional[int]
    parent_event_id: Optional[int]
    created_at: datetime
    updated_at: datetime


class InvestigationFindingCreate(InvestigationFindingBase):
    """Schema for creating findings"""
    investigation_id: int


class InvestigationFindingRead(InvestigationFindingBase):
    """Schema for reading findings"""
    id: int
    investigation_id: int
    user_id: int
    reviewed_by_user_id: Optional[int]
    reviewed_at: Optional[datetime]
    review_status: Optional[str]
    created_at: datetime
    updated_at: datetime