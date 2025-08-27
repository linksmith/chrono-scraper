"""
Pydantic models for ScrapePage API endpoints
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, validator

from app.models.scraping import ScrapePageStatus


class ScrapePageFilterBy(str, Enum):
    """Filter options for scrape pages"""
    ALL = "all"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"
    FILTERED = "filtered"
    MANUAL_REVIEW = "manual_review"
    MANUALLY_OVERRIDDEN = "manually_overridden"


class ScrapePageSortBy(str, Enum):
    """Sort options for scrape pages"""
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    PRIORITY_SCORE = "priority_score"
    CONTENT_LENGTH = "content_length"
    RETRY_COUNT = "retry_count"
    STATUS = "status"
    FILTER_CONFIDENCE = "filter_confidence"


class SortOrder(str, Enum):
    """Sort order options"""
    ASC = "asc"
    DESC = "desc"


class ScrapePageQueryParams(BaseModel):
    """Query parameters for listing scrape pages"""
    page: int = Field(default=1, ge=1, description="Page number")
    limit: int = Field(default=50, ge=1, le=500, description="Items per page")
    filter_by: ScrapePageFilterBy = Field(default=ScrapePageFilterBy.ALL, description="Filter by status")
    sort_by: ScrapePageSortBy = Field(default=ScrapePageSortBy.CREATED_AT, description="Sort by field")
    order: SortOrder = Field(default=SortOrder.DESC, description="Sort order")
    
    # Advanced filters
    domain_id: Optional[int] = Field(default=None, description="Filter by domain ID")
    scrape_session_id: Optional[int] = Field(default=None, description="Filter by scrape session ID")
    priority_min: Optional[int] = Field(default=None, ge=0, le=10, description="Minimum priority score")
    priority_max: Optional[int] = Field(default=None, ge=0, le=10, description="Maximum priority score")
    confidence_min: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Minimum filter confidence")
    confidence_max: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Maximum filter confidence")
    
    # Content filters
    has_content: Optional[bool] = Field(default=None, description="Filter by presence of extracted content")
    is_pdf: Optional[bool] = Field(default=None, description="Filter by PDF status")
    is_duplicate: Optional[bool] = Field(default=None, description="Filter by duplicate status")
    is_list_page: Optional[bool] = Field(default=None, description="Filter by list page status")
    
    # Date range filters
    created_after: Optional[datetime] = Field(default=None, description="Created after date")
    created_before: Optional[datetime] = Field(default=None, description="Created before date")
    completed_after: Optional[datetime] = Field(default=None, description="Completed after date")
    completed_before: Optional[datetime] = Field(default=None, description="Completed before date")
    
    # Text search
    search_query: Optional[str] = Field(default=None, max_length=500, description="Search in title, URL, or content")
    
    # Manual processing filters
    can_be_manually_processed: Optional[bool] = Field(default=None, description="Filter by manual processing eligibility")
    is_manually_overridden: Optional[bool] = Field(default=None, description="Filter by manual override status")


class ScrapePageSummary(BaseModel):
    """Summary view of a scrape page"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    original_url: str
    content_url: str
    title: Optional[str] = None
    status: ScrapePageStatus
    mime_type: str
    content_length: Optional[int] = None
    priority_score: Optional[int] = None
    
    # Filtering information
    filter_reason: Optional[str] = None
    filter_category: Optional[str] = None
    filter_confidence: Optional[float] = None
    is_manually_overridden: bool = False
    can_be_manually_processed: bool = True
    
    # Processing flags
    is_pdf: bool = False
    is_duplicate: bool = False
    is_list_page: bool = False
    
    # Timestamps
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    # Relationships
    domain_id: int
    scrape_session_id: Optional[int] = None
    page_id: Optional[int] = None
    
    # Error information
    error_message: Optional[str] = None
    retry_count: int = 0


class ScrapePageDetail(ScrapePageSummary):
    """Detailed view of a scrape page with full content"""
    
    # Full content fields
    extracted_text: Optional[str] = None
    extracted_content: Optional[str] = None
    markdown_content: Optional[str] = None
    
    # Additional metadata
    unix_timestamp: str
    status_code: int = 200
    digest_hash: Optional[str] = None
    extraction_method: Optional[str] = None
    
    # Enhanced filtering details
    filter_details: Optional[Dict[str, Any]] = None
    original_filter_decision: Optional[str] = None
    matched_pattern: Optional[str] = None
    related_page_id: Optional[int] = None
    
    # Error details
    error_type: Optional[str] = None
    max_retries: int = 3
    
    # Performance metrics
    fetch_time: Optional[float] = None
    extraction_time: Optional[float] = None
    total_processing_time: Optional[float] = None
    
    # Timestamps
    first_seen_at: datetime
    last_attempt_at: Optional[datetime] = None


class ScrapePageListResponse(BaseModel):
    """Response model for paginated scrape page lists"""
    pages: List[ScrapePageSummary]
    total: int
    page: int
    limit: int
    total_pages: int
    has_next: bool
    has_previous: bool


class ManualProcessingRequest(BaseModel):
    """Request model for manual processing operations"""
    page_ids: List[int] = Field(..., min_length=1, max_length=1000, description="List of scrape page IDs")
    reason: Optional[str] = Field(default=None, max_length=500, description="Reason for manual processing")
    priority_override: Optional[int] = Field(default=None, ge=0, le=10, description="Override priority score")
    force_reprocess: bool = Field(default=False, description="Force reprocessing even if already completed")


class ManualProcessingResponse(BaseModel):
    """Response model for manual processing operations"""
    success: bool
    message: str
    processed_count: int
    failed_count: int
    failed_page_ids: List[int] = Field(default_factory=list)
    task_id: Optional[str] = None


class ScrapePageStatistics(BaseModel):
    """Statistics for scrape pages"""
    total_pages: int
    status_counts: Dict[str, int]
    filter_category_counts: Dict[str, int]
    priority_distribution: Dict[int, int]
    
    # Performance metrics
    average_processing_time: Optional[float] = None
    average_content_length: Optional[float] = None
    
    # Quality metrics
    success_rate: float  # percentage of completed pages
    retry_rate: float    # percentage of pages that needed retries
    filter_rate: float   # percentage of filtered pages
    
    # Manual processing stats
    manual_review_pending: int
    manually_overridden: int
    can_be_manually_processed: int
    
    # Time-based stats
    pages_last_24h: int
    pages_last_week: int
    pages_last_month: int


class FilterAnalysis(BaseModel):
    """Analysis of filtering effectiveness"""
    total_filtered: int
    filter_categories: Dict[str, int]
    filter_reasons: Dict[str, int]
    confidence_distribution: Dict[str, int]  # Ranges like "0.0-0.2", "0.8-1.0"
    manual_overrides: int
    override_success_rate: float  # % of manual overrides that resulted in successful processing


class ScrapePageAnalytics(BaseModel):
    """Comprehensive analytics for scrape pages"""
    basic_stats: ScrapePageStatistics
    filter_analysis: FilterAnalysis
    
    # Time series data (last 30 days)
    daily_stats: List[Dict[str, Any]]  # [{date: "2024-01-15", completed: 150, failed: 10, filtered: 85}, ...]
    
    # Domain-specific stats
    domain_performance: Dict[int, Dict[str, Any]]  # {domain_id: {success_rate: 0.85, avg_time: 2.3}}


class BulkScrapePageAction(str, Enum):
    """Actions available for bulk scrape page operations"""
    MARK_FOR_PROCESSING = "mark_for_processing"
    APPROVE_ALL = "approve_all"
    SKIP_ALL = "skip_all"
    DELETE = "delete"
    RETRY = "retry"
    RESET_STATUS = "reset_status"
    UPDATE_PRIORITY = "update_priority"


class BulkScrapePageOperationStatus(str, Enum):
    """Status of bulk operations"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_COMPLETED = "partially_completed"


class BulkManualProcessingRequest(BaseModel):
    """Request model for bulk manual processing operations"""
    # Use filters to select pages instead of specific IDs for bulk operations
    filters: ScrapePageQueryParams
    action: BulkScrapePageAction
    
    # Action-specific parameters
    reason: Optional[str] = Field(default=None, max_length=500, description="Reason for the operation")
    priority_override: Optional[int] = Field(default=None, ge=0, le=10, description="Override priority score")
    force_reprocess: bool = Field(default=False, description="Force reprocessing even if already completed")
    new_status: Optional[ScrapePageStatus] = Field(default=None, description="New status for reset operations")
    
    # Safety limits
    max_pages: int = Field(default=1000, ge=1, le=10000, description="Maximum number of pages to process")
    dry_run: bool = Field(default=False, description="Preview operation without making changes")
    
    # Batch processing
    batch_size: int = Field(default=100, ge=1, le=500, description="Number of pages to process per batch")
    
    @validator('filters')
    def validate_filters(cls, v):
        """Ensure filters are provided for bulk operations"""
        if not v:
            raise ValueError("Filters must be provided for bulk operations")
        return v
    
    @validator('max_pages')
    def validate_max_pages(cls, v, values):
        """Validate maximum pages limit based on action"""
        destructive_actions = [BulkScrapePageAction.DELETE]
        if values.get('action') in destructive_actions and v > 1000:
            raise ValueError("Maximum 1000 pages allowed for destructive operations")
        return v


class BulkOperationProgress(BaseModel):
    """Progress tracking for bulk operations"""
    operation_id: str
    status: BulkScrapePageOperationStatus
    progress_percentage: float = Field(0.0, ge=0.0, le=100.0)
    current_step: str
    total_steps: int
    completed_steps: int
    estimated_remaining_seconds: Optional[int] = Field(None)
    
    # Current processing info
    current_batch: int = Field(0)
    total_batches: int = Field(0)
    items_processed: int = Field(0)
    items_total: int = Field(0)
    
    # Success/failure tracking
    successful_count: int = Field(0)
    failed_count: int = Field(0)
    skipped_count: int = Field(0)
    
    # Error tracking
    errors_count: int = Field(0)
    warnings_count: int = Field(0)
    last_error: Optional[str] = Field(None)
    
    # Timestamps
    started_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = Field(None)


class BulkOperationResult(BaseModel):
    """Result model for bulk operations"""
    operation_id: str
    action: BulkScrapePageAction
    status: BulkScrapePageOperationStatus
    
    # Summary counts
    total_requested: int
    total_processed: int
    successful_count: int
    failed_count: int
    skipped_count: int
    
    # Detailed results
    successful_page_ids: List[int] = Field(default_factory=list)
    failed_page_ids: List[int] = Field(default_factory=list)
    skipped_page_ids: List[int] = Field(default_factory=list)
    failed_reasons: Dict[int, str] = Field(default_factory=dict)
    
    # Task tracking
    task_ids: List[str] = Field(default_factory=list)
    
    # Timing information
    started_at: datetime
    completed_at: Optional[datetime] = Field(None)
    duration_seconds: Optional[float] = Field(None)
    
    # Additional metadata
    dry_run: bool = Field(default=False)
    reason: Optional[str] = Field(None)
    filters_used: Optional[Dict[str, Any]] = Field(None)
    
    # Progress tracking
    progress: Optional[BulkOperationProgress] = Field(None)


class BulkOperationPreview(BaseModel):
    """Preview of what a bulk operation would affect"""
    action: BulkScrapePageAction
    total_pages_affected: int
    pages_by_status: Dict[str, int]
    pages_by_domain: Dict[int, int]
    estimated_processing_time_minutes: Optional[float] = Field(None)
    
    # Sample of pages that would be affected (first 10)
    sample_pages: List[ScrapePageSummary] = Field(default_factory=list)
    
    # Warnings and considerations
    warnings: List[str] = Field(default_factory=list)
    blocked_page_ids: List[int] = Field(default_factory=list)  # Pages that can't be processed
    blocked_reasons: Dict[int, str] = Field(default_factory=dict)