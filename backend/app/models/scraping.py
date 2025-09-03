"""
Scraping-related models for Wayback Machine integration
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column, String, DateTime, Text, JSON
from sqlalchemy import func, Index
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum
from pydantic import field_validator, field_serializer


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


class IncrementalRunStatus(str, Enum):
    """Incremental scraping run status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IncrementalRunType(str, Enum):
    """Incremental scraping run type enumeration"""
    SCHEDULED = "scheduled"  # Regular scheduled check
    MANUAL = "manual"  # User-triggered check
    GAP_FILL = "gap_fill"  # Filling detected gaps
    BACKFILL = "backfill"  # Historical backfill
    CONTENT_CHANGE = "content_change"  # Content-based trigger


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
    # Legacy page_id field - no longer references pages table
    page_id: Optional[int] = Field(default=None)
    
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


class IncrementalScrapingHistoryBase(SQLModel):
    """Base incremental scraping history model"""
    run_type: IncrementalRunType = Field(sa_column=Column(String(20)))
    trigger_reason: Optional[str] = Field(
        default=None, 
        sa_column=Column(String(200)),
        description="Reason that triggered this incremental run"
    )
    
    # Date range for this incremental run
    date_range_start: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    date_range_end: datetime = Field(sa_column=Column(DateTime(timezone=True)))
    
    # Configuration snapshot (JSON)
    incremental_config: Dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Configuration used for this run"
    )
    
    # Results and statistics
    pages_discovered: int = Field(default=0)
    pages_processed: int = Field(default=0)
    pages_failed: int = Field(default=0)
    pages_skipped: int = Field(default=0)
    new_content_found: int = Field(default=0)
    duplicates_filtered: int = Field(default=0)
    
    # Gap analysis results
    gaps_detected: List[Dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="List of gaps detected during this run"
    )
    gaps_filled: List[Dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON),
        description="List of gaps filled during this run"
    )
    
    # Coverage analysis
    coverage_before: Optional[float] = Field(
        default=None,
        description="Coverage percentage before this run"
    )
    coverage_after: Optional[float] = Field(
        default=None,
        description="Coverage percentage after this run"
    )
    coverage_improvement: Optional[float] = Field(
        default=None,
        description="Coverage improvement from this run"
    )
    
    # Performance metrics
    runtime_seconds: Optional[float] = Field(default=None)
    avg_processing_time: Optional[float] = Field(default=None)
    success_rate: Optional[float] = Field(default=None)
    
    # Error tracking
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_details: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON)
    )
    
    # Detailed results (JSON)
    detailed_results: Optional[Dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Detailed results and metadata from the run"
    )


class IncrementalScrapingHistory(IncrementalScrapingHistoryBase, table=True):
    """Incremental scraping history model for database"""
    __tablename__ = "incremental_scraping_history"
    __table_args__ = (
        Index('ix_incremental_history_domain_id', 'domain_id'),
        Index('ix_incremental_history_status', 'status'),
        Index('ix_incremental_history_run_type', 'run_type'),
        Index('ix_incremental_history_started_at', 'started_at'),
        Index('ix_incremental_history_date_range', 'date_range_start', 'date_range_end'),
        Index('ix_incremental_history_domain_status', 'domain_id', 'status'),
    )
    
    id: Optional[int] = Field(default=None, primary_key=True)
    domain_id: int = Field(foreign_key="domains.id")
    scrape_session_id: Optional[int] = Field(
        default=None,
        foreign_key="scrape_sessions.id",
        description="Associated scrape session if applicable"
    )
    
    status: IncrementalRunStatus = Field(
        default=IncrementalRunStatus.PENDING,
        sa_column=Column(String(20))
    )
    
    @field_validator('status', mode='before')
    @classmethod
    def validate_status(cls, v):
        """Convert string values to IncrementalRunStatus enum"""
        if isinstance(v, str):
            try:
                return IncrementalRunStatus(v)
            except ValueError:
                return IncrementalRunStatus.PENDING
        return v
    
    @field_validator('run_type', mode='before')
    @classmethod
    def validate_run_type(cls, v):
        """Convert string values to IncrementalRunType enum"""
        if isinstance(v, str):
            try:
                return IncrementalRunType(v)
            except ValueError:
                return IncrementalRunType.SCHEDULED
        return v
    
    @field_serializer('status')
    def serialize_status(self, value):
        """Serialize IncrementalRunStatus enum to string"""
        if isinstance(value, IncrementalRunStatus):
            return value.value
        return value
    
    @field_serializer('run_type')
    def serialize_run_type(self, value):
        """Serialize IncrementalRunType enum to string"""
        if isinstance(value, IncrementalRunType):
            return value.value
        return value
    
    # Timing
    started_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )
    completed_at: Optional[datetime] = Field(
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
    
    def mark_completed(self, pages_processed: int = 0, new_content: int = 0):
        """Mark the incremental run as completed"""
        self.status = IncrementalRunStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.pages_processed = pages_processed
        self.new_content_found = new_content
        if self.started_at:
            self.runtime_seconds = (datetime.utcnow() - self.started_at).total_seconds()
    
    def mark_failed(self, error_message: str, error_details: Optional[Dict[str, Any]] = None):
        """Mark the incremental run as failed"""
        self.status = IncrementalRunStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        if error_details:
            self.error_details = error_details
        if self.started_at:
            self.runtime_seconds = (datetime.utcnow() - self.started_at).total_seconds()
    
    def calculate_success_rate(self) -> float:
        """Calculate and update success rate"""
        total = self.pages_processed + self.pages_failed
        if total > 0:
            self.success_rate = self.pages_processed / total
            return self.success_rate
        return 0.0


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


# Incremental scraping schemas
class IncrementalScrapingHistoryCreate(IncrementalScrapingHistoryBase):
    """Schema for creating incremental scraping history records"""
    pass


class IncrementalScrapingHistoryRead(IncrementalScrapingHistoryBase):
    """Schema for reading incremental scraping history records"""
    id: int
    domain_id: int
    scrape_session_id: Optional[int]
    status: IncrementalRunStatus
    started_at: datetime
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class IncrementalRunSummary(SQLModel):
    """Schema for incremental run summary statistics"""
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    pending_runs: int = 0
    running_runs: int = 0
    
    total_pages_discovered: int = 0
    total_pages_processed: int = 0
    total_new_content: int = 0
    total_gaps_detected: int = 0
    total_gaps_filled: int = 0
    
    avg_runtime_seconds: Optional[float] = None
    avg_success_rate: Optional[float] = None
    latest_run_at: Optional[datetime] = None
    next_scheduled_run: Optional[datetime] = None
    
    coverage_improvement: Optional[float] = None
    current_coverage: Optional[float] = None


class IncrementalConfigUpdate(SQLModel):
    """Schema for updating incremental scraping configuration"""
    incremental_enabled: Optional[bool] = None
    incremental_mode: Optional[str] = None  # Will be validated to IncrementalMode
    overlap_days: Optional[int] = None
    max_gap_days: Optional[int] = None
    backfill_enabled: Optional[bool] = None