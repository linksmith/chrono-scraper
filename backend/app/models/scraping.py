"""
Scraping-related models for Wayback Machine integration
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column, String, DateTime, Boolean, Text, Integer, ForeignKey, JSON
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum
from pydantic import field_validator


class ScrapePageStatus(str, Enum):
    """Scrape page status enumeration"""
    # Core processing statuses
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"
    
    # Enhanced filtering statuses with specificity
    FILTERED_LIST_PAGE = "filtered_list_page"           # Blog, category, pagination pages
    FILTERED_ALREADY_PROCESSED = "filtered_already_processed"  # Same digest exists
    FILTERED_ATTACHMENT_DISABLED = "filtered_attachment_disabled"  # PDFs/docs when disabled
    FILTERED_FILE_EXTENSION = "filtered_file_extension"  # CSS, JS, images (never shown)
    FILTERED_SIZE_TOO_SMALL = "filtered_size_too_small"  # Below minimum size threshold
    FILTERED_SIZE_TOO_LARGE = "filtered_size_too_large"  # Above maximum size threshold
    FILTERED_LOW_PRIORITY = "filtered_low_priority"      # Low priority score
    FILTERED_CUSTOM_RULE = "filtered_custom_rule"        # Custom filtering rules
    
    # Manual override statuses
    MANUALLY_SKIPPED = "manually_skipped"                # User chose to skip
    MANUALLY_APPROVED = "manually_approved"              # User overrode filter
    AWAITING_MANUAL_REVIEW = "awaiting_manual_review"    # Needs human decision


class CDXResumeStatus(str, Enum):
    """CDX resume status enumeration"""
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ScrapePageBase(SQLModel):
    """Base scrape page model"""
    original_url: str = Field(sa_column=Column(Text))
    content_url: str = Field(sa_column=Column(Text))
    unix_timestamp: str = Field(sa_column=Column(String(14)))
    mime_type: str = Field(sa_column=Column(String(100)))
    status_code: int = Field(default=200)
    content_length: Optional[int] = Field(default=None)
    digest_hash: Optional[str] = Field(default=None, sa_column=Column(String(32)))
    
    # Content extraction fields
    title: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    extracted_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    extracted_content: Optional[str] = Field(default=None, sa_column=Column(Text))
    markdown_content: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Processing flags
    is_pdf: bool = Field(default=False)
    is_duplicate: bool = Field(default=False)
    is_list_page: bool = Field(default=False)
    extraction_method: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    
    # Enhanced filtering system fields with structured data
    filter_reason: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    filter_category: Optional[str] = Field(default=None, sa_column=Column(String(50)))
    # JSONB field for structured filter details - stores specific patterns, rules, etc.
    filter_details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    is_manually_overridden: bool = Field(default=False)
    original_filter_decision: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    priority_score: Optional[int] = Field(default=5)
    can_be_manually_processed: bool = Field(default=True)
    
    # Additional fields for individual filtering reasons
    matched_pattern: Optional[str] = Field(default=None, sa_column=Column(String(200)))  # Specific regex/pattern that matched
    filter_confidence: Optional[float] = Field(default=None)  # 0.0-1.0 confidence score
    related_page_id: Optional[int] = Field(default=None)  # For duplicates, reference to original page
    

class ScrapePage(ScrapePageBase, table=True):
    """Scrape page model for database"""
    __tablename__ = "scrape_pages"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    domain_id: int = Field(foreign_key="domains.id")
    scrape_session_id: Optional[int] = Field(default=None, foreign_key="scrape_sessions.id")
    page_id: Optional[int] = Field(default=None, foreign_key="pages.id")
    
    status: ScrapePageStatus = Field(
        default=ScrapePageStatus.PENDING,
        sa_column=Column(String(30))
    )
    
    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        """Convert string values to ScrapePageStatus enum"""
        if isinstance(v, str):
            try:
                return ScrapePageStatus(v)
            except ValueError:
                # If invalid string, return default
                return ScrapePageStatus.PENDING
        return v
    
    # Error tracking
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_type: Optional[str] = Field(default=None, sa_column=Column(String(100)))
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    
    # Performance metrics
    fetch_time: Optional[float] = Field(default=None)  # Time to fetch content
    extraction_time: Optional[float] = Field(default=None)  # Time to extract content
    total_processing_time: Optional[float] = Field(default=None)
    
    # Timestamps
    first_seen_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    last_attempt_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    completed_at: Optional[datetime] = Field(
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


class CDXResumeStateBase(SQLModel):
    """Base CDX resume state model"""
    domain_name: str = Field(sa_column=Column(String(255)))
    from_date: str = Field(sa_column=Column(String(8)))  # YYYYMMDD
    to_date: str = Field(sa_column=Column(String(8)))    # YYYYMMDD
    match_type: str = Field(sa_column=Column(String(20)))
    url_path: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    min_size: int = Field(default=200)
    page_size: int = Field(default=3000)
    max_pages: Optional[int] = Field(default=None)


class CDXResumeState(CDXResumeStateBase, table=True):
    """CDX resume state for pagination and crash recovery"""
    __tablename__ = "cdx_resume_states"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    domain_id: int = Field(foreign_key="domains.id")
    scrape_session_id: Optional[int] = Field(default=None, foreign_key="scrape_sessions.id")
    
    status: CDXResumeStatus = Field(
        default=CDXResumeStatus.ACTIVE,
        sa_column=Column(String(20))
    )
    
    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        """Convert string values to CDXResumeStatus enum"""
        if isinstance(v, str):
            try:
                return CDXResumeStatus(v)
            except ValueError:
                # If invalid string, return default
                return CDXResumeStatus.ACTIVE
        return v
    
    # Progress tracking
    current_page: int = Field(default=0)
    total_pages: Optional[int] = Field(default=None)
    pages_processed: int = Field(default=0)
    total_results_found: int = Field(default=0)
    total_results_processed: int = Field(default=0)
    estimated_total_results: Optional[int] = Field(default=None)
    
    # Resume key for CDX API pagination
    resume_key: Optional[str] = Field(default=None, sa_column=Column(Text))
    cdx_api_url: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    
    # Error tracking
    error_count: int = Field(default=0)
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text))
    last_error_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    
    # Timestamps
    last_processed_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now())
    )
    completed_at: Optional[datetime] = Field(
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
    
    def can_resume(self) -> bool:
        """Check if this state can be used for resuming"""
        return (
            self.status in [CDXResumeStatus.ACTIVE, CDXResumeStatus.FAILED] and
            self.current_page > 0 and
            self.resume_key is not None
        )
    
    def update_progress(self, current_page: int, resume_key: Optional[str] = None, 
                       results_found: int = 0, results_processed: int = 0):
        """Update progress tracking"""
        self.current_page = current_page
        if resume_key:
            self.resume_key = resume_key
        self.total_results_found += results_found
        self.total_results_processed += results_processed
        self.pages_processed += 1
        self.last_processed_at = datetime.utcnow()
    
    def mark_completed(self):
        """Mark the CDX fetch as completed"""
        self.status = CDXResumeStatus.COMPLETED
        self.completed_at = datetime.utcnow()
    
    def mark_failed(self, error_message: str):
        """Mark the CDX fetch as failed"""
        self.status = CDXResumeStatus.FAILED
        self.error_count += 1
        self.last_error = error_message
        self.last_error_at = datetime.utcnow()


class ScrapeMonitoringLogBase(SQLModel):
    """Base scrape monitoring log model"""
    # Archive.org health data
    archive_available: Optional[bool] = Field(default=None)
    archive_response_time: Optional[float] = Field(default=None)
    archive_error: Optional[str] = Field(default=None, sa_column=Column(Text))
    
    # Progress data
    progress_percentage: int = Field(default=0)
    completed_urls: int = Field(default=0)
    total_urls: int = Field(default=0)
    failed_urls: int = Field(default=0)
    
    # Performance metrics
    pages_per_minute: Optional[float] = Field(default=None)
    avg_fetch_time: Optional[float] = Field(default=None)
    success_rate: Optional[float] = Field(default=None)
    
    # Raw monitoring data
    raw_monitoring_data: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


class ScrapeMonitoringLog(ScrapeMonitoringLogBase, table=True):
    """Monitoring log for scraping operations"""
    __tablename__ = "scrape_monitoring_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    scrape_session_id: int = Field(foreign_key="scrape_sessions.id")
    
    # Timestamps
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )


class PageErrorLogBase(SQLModel):
    """Base page error log model"""
    error_type: str = Field(sa_column=Column(String(100)))
    error_message: str = Field(sa_column=Column(Text))
    error_details: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    
    # Request details
    wayback_url: str = Field(sa_column=Column(Text))
    original_url: str = Field(sa_column=Column(Text))
    
    # Recovery information
    is_recoverable: bool = Field(default=True)
    suggested_retry_delay: Optional[int] = Field(default=None)  # seconds


class PageErrorLog(PageErrorLogBase, table=True):
    """Error log for failed page scrapes"""
    __tablename__ = "page_error_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    scrape_page_id: int = Field(foreign_key="scrape_pages.id")
    scrape_session_id: Optional[int] = Field(default=None, foreign_key="scrape_sessions.id")
    
    # Error timing
    occurred_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    
    # Recovery tracking
    retry_scheduled_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )
    resolved_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True))
    )


# Pydantic schemas for API
class ScrapePageCreate(ScrapePageBase):
    """Schema for creating scrape pages"""
    pass


class ScrapePageRead(ScrapePageBase):
    """Schema for reading scrape pages"""
    id: int
    domain_id: int
    scrape_session_id: Optional[int]
    page_id: Optional[int]
    status: ScrapePageStatus
    error_message: Optional[str]
    retry_count: int
    created_at: datetime
    updated_at: datetime


class CDXResumeStateRead(CDXResumeStateBase):
    """Schema for reading CDX resume state"""
    id: int
    domain_id: int
    status: CDXResumeStatus
    current_page: int
    total_pages: Optional[int]
    total_results_found: int
    created_at: datetime
    updated_at: datetime


class ScrapeProgressUpdate(SQLModel):
    """Schema for WebSocket progress updates"""
    scrape_session_id: int
    total_urls: int
    completed_urls: int
    failed_urls: int
    progress_percentage: float
    current_url: Optional[str] = None
    pages_per_minute: Optional[float] = None
    estimated_completion: Optional[datetime] = None
    error_summary: Optional[Dict[str, int]] = None


class PageProgressEvent(SQLModel):
    """Schema for individual page progress events"""
    scrape_session_id: int
    scrape_page_id: int
    domain_id: int
    domain_name: str
    page_url: str
    content_url: str
    status: ScrapePageStatus
    previous_status: Optional[ScrapePageStatus] = None
    processing_stage: str  # "cdx_discovery", "content_fetch", "content_extract", "entity_recognition", "indexing", "completed"
    stage_progress: Optional[float] = None  # 0.0 to 1.0 for current stage
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0
    processing_time: Optional[float] = None  # Time for current stage in seconds
    total_processing_time: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CDXDiscoveryEvent(SQLModel):
    """Schema for CDX discovery progress events"""
    scrape_session_id: int
    domain_id: int
    domain_name: str
    current_page: int
    total_pages: Optional[int] = None
    results_found: int
    results_processed: int
    duplicates_filtered: int
    list_pages_filtered: int
    high_value_pages: int
    resume_key: Optional[str] = None
    pages_per_minute: Optional[float] = None
    estimated_completion: Optional[datetime] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ProcessingStageEvent(SQLModel):
    """Schema for detailed processing stage events"""
    scrape_session_id: int
    scrape_page_id: int
    domain_id: int
    page_url: str
    stage: str  # "content_fetch", "content_extract", "entity_recognition", "indexing"
    stage_status: str  # "started", "in_progress", "completed", "failed"
    stage_progress: Optional[float] = None  # 0.0 to 1.0
    stage_details: Optional[Dict[str, Any]] = None  # Stage-specific metadata
    processing_time: Optional[float] = None
    error_message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SessionStatsEvent(SQLModel):
    """Schema for session-level statistics events"""
    scrape_session_id: int
    total_urls: int
    pending_urls: int
    in_progress_urls: int
    completed_urls: int
    failed_urls: int
    skipped_urls: int
    progress_percentage: float
    pages_per_minute: Optional[float] = None
    estimated_completion: Optional[datetime] = None
    active_domains: int
    completed_domains: int
    failed_domains: int
    error_summary: Optional[Dict[str, int]] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)