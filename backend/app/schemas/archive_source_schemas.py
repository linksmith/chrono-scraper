"""
Archive source management schemas for API requests and responses
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from enum import Enum

from app.models.project import ArchiveSource


class ImpactSeverity(str, Enum):
    """Impact severity levels for archive source changes"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConnectivityStatus(str, Enum):
    """Archive source connectivity status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class PerformanceImpact(str, Enum):
    """Performance impact assessment"""
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class ArchiveConfig(BaseModel):
    """Archive source configuration settings"""
    # Wayback Machine specific settings
    wayback_machine: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Wayback Machine configuration")
    
    # Common Crawl specific settings
    common_crawl: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Common Crawl configuration")
    
    # Hybrid mode settings
    fallback_strategy: Optional[str] = Field(default="circuit_breaker", description="Fallback strategy for hybrid mode")
    fallback_delay_seconds: Optional[float] = Field(default=1.0, description="Delay between fallback attempts")
    exponential_backoff: Optional[bool] = Field(default=True, description="Use exponential backoff for retries")
    max_fallback_delay: Optional[float] = Field(default=30.0, description="Maximum delay between fallback attempts")
    
    @field_validator('fallback_strategy')
    @classmethod
    def validate_fallback_strategy(cls, v):
        """Validate fallback strategy values"""
        if v is not None:
            valid_strategies = ["immediate", "retry_then_fallback", "circuit_breaker"]
            if v not in valid_strategies:
                raise ValueError(f"Invalid fallback strategy. Must be one of: {valid_strategies}")
        return v


class ArchiveSourceUpdateRequest(BaseModel):
    """Request schema for updating project archive source settings"""
    archive_source: ArchiveSource = Field(description="New archive source to use")
    fallback_enabled: bool = Field(default=True, description="Enable fallback to other archive sources")
    archive_config: Optional[ArchiveConfig] = Field(default=None, description="Archive-specific configuration")
    confirm_impact: bool = Field(default=False, description="User acknowledges potential impact of the change")
    change_reason: Optional[str] = Field(default=None, max_length=500, description="Reason for the archive source change")


class ArchiveSourceUpdateResponse(BaseModel):
    """Response schema for archive source update operations"""
    success: bool = Field(description="Whether the update was successful")
    message: str = Field(description="Human-readable message about the update")
    project_id: int = Field(description="ID of the updated project")
    old_archive_source: ArchiveSource = Field(description="Previous archive source")
    new_archive_source: ArchiveSource = Field(description="New archive source")
    old_config: Optional[Dict[str, Any]] = Field(default=None, description="Previous archive configuration")
    new_config: Optional[Dict[str, Any]] = Field(default=None, description="New archive configuration")
    warnings: List[str] = Field(default_factory=list, description="Warnings about the change")
    updated_at: datetime = Field(description="When the update was applied")


class ImpactWarning(BaseModel):
    """Individual impact warning"""
    severity: ImpactSeverity = Field(description="Severity of the warning")
    category: str = Field(description="Category of the warning (e.g., 'performance', 'coverage', 'cost')")
    title: str = Field(description="Brief warning title")
    description: str = Field(description="Detailed warning description")
    recommendation: Optional[str] = Field(default=None, description="Recommended action")


class ArchiveSourceImpact(BaseModel):
    """Impact assessment for changing archive sources"""
    current_source: ArchiveSource = Field(description="Current archive source")
    new_source: ArchiveSource = Field(description="Proposed new archive source")
    
    # Coverage analysis
    estimated_coverage_change: float = Field(
        ge=-1.0, le=1.0,
        description="Estimated coverage change (-1.0 = complete loss, 1.0 = complete gain)"
    )
    coverage_explanation: str = Field(description="Explanation of coverage impact")
    
    # Performance analysis
    performance_impact: PerformanceImpact = Field(description="Expected performance impact")
    response_time_change: Optional[float] = Field(
        default=None,
        description="Expected response time change in seconds (negative = faster)"
    )
    
    # Active scraping analysis
    ongoing_scraping_sessions: int = Field(ge=0, description="Number of active scraping sessions")
    affected_domains: List[str] = Field(default_factory=list, description="Domains that will be affected")
    
    # Safety assessment
    safe_to_switch: bool = Field(description="Whether it's safe to switch immediately")
    requires_confirmation: bool = Field(description="Whether user confirmation is required")
    
    # Warnings and recommendations
    warnings: List[ImpactWarning] = Field(default_factory=list, description="Impact warnings")
    recommendations: List[str] = Field(default_factory=list, description="Recommended actions")
    
    # Migration details
    estimated_migration_time: Optional[int] = Field(
        default=None, ge=0,
        description="Estimated time for migration in seconds"
    )
    rollback_window: Optional[int] = Field(
        default=86400, ge=0,
        description="Time window for rollback in seconds (default 24 hours)"
    )


class ArchiveSourceTestResult(BaseModel):
    """Individual test result for an archive source"""
    domain: str = Field(description="Domain that was tested")
    success: bool = Field(description="Whether the test was successful")
    response_time_ms: Optional[float] = Field(default=None, ge=0, description="Response time in milliseconds")
    records_found: Optional[int] = Field(default=None, ge=0, description="Number of CDX records found")
    error_message: Optional[str] = Field(default=None, description="Error message if test failed")
    error_type: Optional[str] = Field(default=None, description="Classification of the error")


class ArchiveSourceTestRequest(BaseModel):
    """Request schema for testing archive source connectivity"""
    archive_source: ArchiveSource = Field(description="Archive source to test")
    test_domains: List[str] = Field(
        default_factory=list,
        max_items=10,
        description="Specific domains to test (uses project domains if empty)"
    )
    timeout_seconds: Optional[int] = Field(default=30, ge=1, le=300, description="Test timeout in seconds")
    
    @field_validator('test_domains')
    @classmethod
    def validate_test_domains(cls, v):
        """Validate test domain format"""
        for domain in v:
            if not domain or len(domain) > 255:
                raise ValueError(f"Invalid domain: {domain}")
        return v


class ArchiveSourceTestResponse(BaseModel):
    """Response schema for archive source testing"""
    archive_source: ArchiveSource = Field(description="Archive source that was tested")
    overall_status: ConnectivityStatus = Field(description="Overall connectivity status")
    
    # Aggregate metrics
    tests_run: int = Field(ge=0, description="Total number of tests run")
    tests_passed: int = Field(ge=0, description="Number of successful tests")
    success_rate: float = Field(ge=0.0, le=1.0, description="Success rate (0.0 to 1.0)")
    
    # Performance metrics
    avg_response_time_ms: Optional[float] = Field(default=None, ge=0, description="Average response time")
    total_records_found: int = Field(ge=0, description="Total CDX records found across all tests")
    
    # Individual test results
    test_results: List[ArchiveSourceTestResult] = Field(description="Individual test results")
    
    # Error summary
    errors: List[str] = Field(default_factory=list, description="List of unique errors encountered")
    error_summary: Dict[str, int] = Field(default_factory=dict, description="Count of each error type")
    
    # Recommendations
    recommendations: List[str] = Field(default_factory=list, description="Recommendations based on test results")
    
    # Test metadata
    test_started_at: datetime = Field(description="When the test started")
    test_completed_at: datetime = Field(description="When the test completed")
    test_duration_seconds: float = Field(ge=0, description="Total test duration")


class ArchiveSourceStats(BaseModel):
    """Statistics for a single archive source"""
    source_name: str = Field(description="Name of the archive source")
    
    # Request statistics
    total_requests: int = Field(ge=0, description="Total number of requests")
    successful_requests: int = Field(ge=0, description="Number of successful requests")
    failed_requests: int = Field(ge=0, description="Number of failed requests")
    
    # Performance metrics
    success_rate: float = Field(ge=0.0, le=100.0, description="Success rate percentage")
    average_response_time_ms: float = Field(ge=0, description="Average response time in milliseconds")
    total_records_retrieved: int = Field(ge=0, description="Total CDX records retrieved")
    
    # Error analysis
    error_rate: float = Field(ge=0.0, le=100.0, description="Error rate percentage")
    error_breakdown: Dict[str, int] = Field(default_factory=dict, description="Count of each error type")
    
    # Circuit breaker status
    circuit_breaker_state: str = Field(description="Circuit breaker state (open/closed/half-open)")
    circuit_breaker_failures: int = Field(ge=0, description="Current failure count")
    
    # Timing
    last_success_at: Optional[datetime] = Field(default=None, description="Last successful request time")
    last_failure_at: Optional[datetime] = Field(default=None, description="Last failed request time")
    last_used_at: Optional[datetime] = Field(default=None, description="Last time this source was used")
    
    # Health status
    is_healthy: bool = Field(description="Whether the source is considered healthy")
    health_score: float = Field(ge=0.0, le=100.0, description="Overall health score")


class ArchiveSourceMetricsResponse(BaseModel):
    """Response schema for archive source performance metrics"""
    project_id: int = Field(description="Project ID these metrics apply to")
    time_period: str = Field(description="Time period covered by these metrics")
    
    # Source-specific metrics
    archive_sources: Dict[str, ArchiveSourceStats] = Field(
        description="Metrics for each archive source"
    )
    
    # Hybrid mode specific metrics
    hybrid_fallback_events: int = Field(ge=0, description="Number of fallback events in hybrid mode")
    primary_source_failures: int = Field(ge=0, description="Number of primary source failures")
    fallback_success_rate: float = Field(ge=0.0, le=100.0, description="Success rate of fallback operations")
    
    # Overall metrics
    total_queries: int = Field(ge=0, description="Total queries across all sources")
    overall_success_rate: float = Field(ge=0.0, le=100.0, description="Overall success rate")
    avg_query_time_ms: float = Field(ge=0, description="Average query time across all sources")
    
    # Recommendations
    recommendations: List[str] = Field(default_factory=list, description="Performance optimization recommendations")
    
    # Circuit breaker summary
    circuit_breaker_status: Dict[str, str] = Field(
        description="Circuit breaker status for each source"
    )
    
    # Report metadata
    generated_at: datetime = Field(description="When this report was generated")
    data_freshness: str = Field(description="How fresh the underlying data is")


class ArchiveSourceChangeLogEntry(BaseModel):
    """Individual archive source change log entry"""
    id: int = Field(description="Unique ID of the change log entry")
    project_id: int = Field(description="Project that was modified")
    user_id: int = Field(description="User who made the change")
    
    # Change details
    old_archive_source: ArchiveSource = Field(description="Previous archive source")
    new_archive_source: ArchiveSource = Field(description="New archive source")
    old_config: Optional[Dict[str, Any]] = Field(default=None, description="Previous configuration")
    new_config: Optional[Dict[str, Any]] = Field(default=None, description="New configuration")
    
    # Metadata
    change_reason: Optional[str] = Field(default=None, description="Reason for the change")
    impact_acknowledged: bool = Field(description="Whether impact was acknowledged")
    change_timestamp: datetime = Field(description="When the change was made")
    
    # Result tracking
    success: bool = Field(description="Whether the change was successful")
    error_message: Optional[str] = Field(default=None, description="Error message if change failed")
    rollback_available: bool = Field(description="Whether rollback is still possible")


class ArchiveSourceRollbackRequest(BaseModel):
    """Request schema for rolling back archive source changes"""
    change_log_entry_id: int = Field(description="ID of the change log entry to rollback")
    confirm_rollback: bool = Field(description="User confirms they want to rollback")
    rollback_reason: Optional[str] = Field(default=None, max_length=500, description="Reason for rollback")


class ArchiveSourceRollbackResponse(BaseModel):
    """Response schema for archive source rollback operations"""
    success: bool = Field(description="Whether the rollback was successful")
    message: str = Field(description="Human-readable message about the rollback")
    project_id: int = Field(description="ID of the project that was rolled back")
    
    # Rollback details
    rolled_back_from: ArchiveSource = Field(description="Archive source rolled back from")
    rolled_back_to: ArchiveSource = Field(description="Archive source rolled back to")
    original_change_timestamp: datetime = Field(description="When the original change was made")
    rollback_timestamp: datetime = Field(description="When the rollback was performed")
    
    # Warnings
    warnings: List[str] = Field(default_factory=list, description="Warnings about the rollback")