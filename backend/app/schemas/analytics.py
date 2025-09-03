"""
Analytics API Schemas for Chrono Scraper FastAPI Application

Comprehensive Pydantic models for analytics requests and responses, supporting
performance optimized analytics with DuckDB integration.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, validator, ConfigDict


class TimeGranularity(str, Enum):
    """Time granularity options for time-series analytics"""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class AnalyticsFormat(str, Enum):
    """Export format options for analytics data"""
    JSON = "json"
    CSV = "csv"
    PARQUET = "parquet"
    EXCEL = "xlsx"
    PDF = "pdf"


class AnalyticsScope(str, Enum):
    """Scope for analytics queries"""
    USER = "user"
    PROJECT = "project"
    DOMAIN = "domain"
    SYSTEM = "system"


class DatabaseTarget(str, Enum):
    """Target database for analytics queries"""
    POSTGRESQL = "postgresql"
    DUCKDB = "duckdb"
    HYBRID = "hybrid"
    AUTO = "auto"


# Base Request/Response Models
class BaseAnalyticsRequest(BaseModel):
    """Base request model for analytics endpoints"""
    model_config = ConfigDict(str_strip_whitespace=True)
    
    start_date: Optional[datetime] = Field(None, description="Start date for analytics period")
    end_date: Optional[datetime] = Field(None, description="End date for analytics period")
    limit: Optional[int] = Field(100, ge=1, le=10000, description="Maximum number of results")
    offset: Optional[int] = Field(0, ge=0, description="Number of results to skip")
    cache: Optional[bool] = Field(True, description="Use cached results when available")
    
    @validator('end_date')
    def end_date_after_start(cls, v, values):
        if v and values.get('start_date') and v <= values['start_date']:
            raise ValueError('end_date must be after start_date')
        return v


class BaseAnalyticsResponse(BaseModel):
    """Base response model for analytics endpoints"""
    model_config = ConfigDict(from_attributes=True)
    
    success: bool = Field(True, description="Request success status")
    data: Any = Field(description="Analytics data")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Query metadata")
    performance: Dict[str, Any] = Field(default_factory=dict, description="Performance metrics")


class PaginatedAnalyticsResponse(BaseAnalyticsResponse):
    """Paginated analytics response"""
    pagination: Dict[str, Any] = Field(default_factory=dict, description="Pagination information")


# Domain Analytics Schemas
class DomainTimelineRequest(BaseAnalyticsRequest):
    """Request for domain timeline analytics"""
    domain: str = Field(..., description="Domain to analyze")
    granularity: TimeGranularity = Field(TimeGranularity.DAY, description="Time granularity")
    include_subdomains: bool = Field(False, description="Include subdomain data")


class DomainTimelineDataPoint(BaseModel):
    """Single data point in domain timeline"""
    timestamp: datetime = Field(description="Timestamp for data point")
    pages_scraped: int = Field(0, description="Number of pages scraped")
    pages_successful: int = Field(0, description="Number of successful extractions")
    pages_failed: int = Field(0, description="Number of failed extractions")
    content_size_mb: float = Field(0.0, description="Total content size in MB")
    unique_urls: int = Field(0, description="Number of unique URLs processed")
    error_rate: float = Field(0.0, description="Error rate percentage")


class DomainTimelineResponse(BaseAnalyticsResponse):
    """Response for domain timeline analytics"""
    data: List[DomainTimelineDataPoint]
    summary: Dict[str, Any] = Field(default_factory=dict, description="Timeline summary statistics")


class DomainStatisticsRequest(BaseAnalyticsRequest):
    """Request for domain statistics"""
    domain: str = Field(..., description="Domain to analyze")
    include_detailed_metrics: bool = Field(True, description="Include detailed performance metrics")


class DomainStatistics(BaseModel):
    """Domain statistics data"""
    domain: str = Field(description="Domain name")
    total_pages: int = Field(0, description="Total pages scraped")
    successful_pages: int = Field(0, description="Successfully extracted pages")
    failed_pages: int = Field(0, description="Failed extraction pages")
    success_rate: float = Field(0.0, description="Success rate percentage")
    avg_content_size: float = Field(0.0, description="Average content size in KB")
    total_content_size: float = Field(0.0, description="Total content size in MB")
    first_scraped: Optional[datetime] = Field(None, description="First scrape timestamp")
    last_scraped: Optional[datetime] = Field(None, description="Last scrape timestamp")
    unique_urls: int = Field(0, description="Number of unique URLs")
    avg_scrape_duration: float = Field(0.0, description="Average scrape duration in seconds")
    popular_paths: List[Dict[str, Any]] = Field(default_factory=list, description="Most popular paths")
    content_types: Dict[str, int] = Field(default_factory=dict, description="Content type distribution")
    error_distribution: Dict[str, int] = Field(default_factory=dict, description="Error type distribution")


class DomainStatisticsResponse(BaseAnalyticsResponse):
    """Response for domain statistics"""
    data: DomainStatistics


class TopDomainsRequest(BaseAnalyticsRequest):
    """Request for top domains analytics"""
    metric: str = Field("total_pages", description="Metric to rank by (total_pages, success_rate, content_size)")
    include_inactive: bool = Field(False, description="Include domains with no recent activity")


class TopDomainEntry(BaseModel):
    """Entry in top domains list"""
    domain: str = Field(description="Domain name")
    rank: int = Field(description="Rank based on selected metric")
    total_pages: int = Field(0, description="Total pages scraped")
    success_rate: float = Field(0.0, description="Success rate percentage")
    content_size_mb: float = Field(0.0, description="Total content size in MB")
    last_activity: Optional[datetime] = Field(None, description="Last scraping activity")
    projects_count: int = Field(0, description="Number of projects using this domain")


class TopDomainsResponse(BaseAnalyticsResponse):
    """Response for top domains analytics"""
    data: List[TopDomainEntry]


# Project Analytics Schemas
class ProjectPerformanceRequest(BaseAnalyticsRequest):
    """Request for project performance analytics"""
    project_id: UUID = Field(..., description="Project ID to analyze")
    include_domain_breakdown: bool = Field(True, description="Include per-domain breakdown")
    include_time_series: bool = Field(False, description="Include time series data")


class ProjectDomainMetrics(BaseModel):
    """Performance metrics for a domain within a project"""
    domain: str = Field(description="Domain name")
    total_pages: int = Field(0, description="Total pages scraped")
    successful_pages: int = Field(0, description="Successfully extracted pages")
    error_rate: float = Field(0.0, description="Error rate percentage")
    avg_response_time: float = Field(0.0, description="Average response time in seconds")
    content_size_mb: float = Field(0.0, description="Total content size in MB")


class ProjectPerformanceData(BaseModel):
    """Project performance analytics data"""
    project_id: UUID = Field(description="Project ID")
    project_name: str = Field(description="Project name")
    total_pages: int = Field(0, description="Total pages across all domains")
    successful_pages: int = Field(0, description="Successfully extracted pages")
    failed_pages: int = Field(0, description="Failed extraction pages")
    overall_success_rate: float = Field(0.0, description="Overall success rate percentage")
    avg_scrape_duration: float = Field(0.0, description="Average scraping duration")
    total_content_size: float = Field(0.0, description="Total content size in MB")
    scraping_efficiency: float = Field(0.0, description="Pages per hour rate")
    domain_breakdown: List[ProjectDomainMetrics] = Field(default_factory=list)
    time_series: List[Dict[str, Any]] = Field(default_factory=list, description="Time series data if requested")


class ProjectPerformanceResponse(BaseAnalyticsResponse):
    """Response for project performance analytics"""
    data: ProjectPerformanceData


class ProjectContentQualityRequest(BaseAnalyticsRequest):
    """Request for project content quality analytics"""
    project_id: UUID = Field(..., description="Project ID to analyze")
    quality_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Quality score threshold")


class ContentQualityMetrics(BaseModel):
    """Content quality metrics"""
    project_id: UUID = Field(description="Project ID")
    total_pages: int = Field(0, description="Total pages analyzed")
    high_quality_pages: int = Field(0, description="Pages above quality threshold")
    medium_quality_pages: int = Field(0, description="Pages with medium quality")
    low_quality_pages: int = Field(0, description="Pages below quality threshold")
    avg_quality_score: float = Field(0.0, description="Average quality score")
    content_completeness: float = Field(0.0, description="Content completeness percentage")
    extraction_accuracy: float = Field(0.0, description="Extraction accuracy percentage")
    duplicate_content_rate: float = Field(0.0, description="Duplicate content percentage")
    quality_by_domain: Dict[str, float] = Field(default_factory=dict)
    quality_trends: List[Dict[str, Any]] = Field(default_factory=list)


class ProjectContentQualityResponse(BaseAnalyticsResponse):
    """Response for project content quality analytics"""
    data: ContentQualityMetrics


# Content Analytics Schemas
class ContentQualityDistributionRequest(BaseAnalyticsRequest):
    """Request for content quality distribution analytics"""
    projects: Optional[List[UUID]] = Field(None, description="Specific projects to analyze")
    domains: Optional[List[str]] = Field(None, description="Specific domains to analyze")


class QualityDistributionBucket(BaseModel):
    """Quality distribution bucket"""
    quality_range: str = Field(description="Quality score range (e.g., '0.8-0.9')")
    count: int = Field(0, description="Number of pages in this range")
    percentage: float = Field(0.0, description="Percentage of total pages")
    avg_content_size: float = Field(0.0, description="Average content size in KB")
    top_domains: List[str] = Field(default_factory=list, description="Top domains in this bucket")


class ContentQualityDistributionData(BaseModel):
    """Content quality distribution data"""
    total_pages_analyzed: int = Field(0, description="Total pages analyzed")
    distribution: List[QualityDistributionBucket] = Field(description="Quality distribution buckets")
    overall_avg_quality: float = Field(0.0, description="Overall average quality score")
    quality_improvement_trend: float = Field(0.0, description="Quality improvement trend percentage")


class ContentQualityDistributionResponse(BaseAnalyticsResponse):
    """Response for content quality distribution"""
    data: ContentQualityDistributionData


# System Analytics Schemas
class SystemPerformanceRequest(BaseAnalyticsRequest):
    """Request for system performance overview"""
    include_resource_usage: bool = Field(True, description="Include resource usage metrics")
    include_database_metrics: bool = Field(True, description="Include database performance metrics")


class DatabaseMetrics(BaseModel):
    """Database performance metrics"""
    database_type: str = Field(description="Database type (postgresql/duckdb)")
    total_queries: int = Field(0, description="Total queries executed")
    avg_query_time: float = Field(0.0, description="Average query execution time")
    slow_queries_count: int = Field(0, description="Number of slow queries (>1s)")
    error_rate: float = Field(0.0, description="Query error rate percentage")
    connection_pool_usage: float = Field(0.0, description="Connection pool usage percentage")
    cache_hit_rate: float = Field(0.0, description="Cache hit rate percentage")


class SystemPerformanceData(BaseModel):
    """System performance overview data"""
    uptime_hours: float = Field(0.0, description="System uptime in hours")
    total_requests: int = Field(0, description="Total API requests")
    avg_response_time: float = Field(0.0, description="Average API response time")
    error_rate: float = Field(0.0, description="Overall error rate percentage")
    active_users: int = Field(0, description="Active users count")
    active_projects: int = Field(0, description="Active projects count")
    total_pages_scraped: int = Field(0, description="Total pages scraped")
    scraping_throughput: float = Field(0.0, description="Pages per hour throughput")
    database_metrics: List[DatabaseMetrics] = Field(default_factory=list)
    resource_usage: Dict[str, float] = Field(default_factory=dict, description="Resource usage metrics")


class SystemPerformanceResponse(BaseAnalyticsResponse):
    """Response for system performance overview"""
    data: SystemPerformanceData


# Time Series Analytics Schemas
class TimeSeriesRequest(BaseAnalyticsRequest):
    """Request for time series analytics"""
    metric: str = Field(..., description="Metric to analyze (e.g., 'domain_growth', 'content_quality')")
    granularity: TimeGranularity = Field(TimeGranularity.DAY, description="Time granularity")
    aggregation: str = Field("sum", description="Aggregation function (sum, avg, max, min, count)")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Additional filters")


class TimeSeriesDataPoint(BaseModel):
    """Single data point in time series"""
    timestamp: datetime = Field(description="Timestamp")
    value: Union[float, int] = Field(description="Metric value")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class TimeSeriesResponse(BaseAnalyticsResponse):
    """Response for time series analytics"""
    data: List[TimeSeriesDataPoint]
    forecast: Optional[List[TimeSeriesDataPoint]] = Field(None, description="Forecast data if requested")
    trends: Dict[str, Any] = Field(default_factory=dict, description="Trend analysis")


# Comparative Analytics Schemas
class ProjectComparisonRequest(BaseModel):
    """Request for project comparison analytics"""
    project_ids: List[UUID] = Field(..., min_items=2, max_items=10, description="Projects to compare")
    metrics: List[str] = Field(default_factory=lambda: ["success_rate", "content_quality", "throughput"])
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class ProjectComparisonEntry(BaseModel):
    """Single project entry in comparison"""
    project_id: UUID = Field(description="Project ID")
    project_name: str = Field(description="Project name")
    metrics: Dict[str, Union[float, int]] = Field(description="Metric values")
    rank: Dict[str, int] = Field(description="Rank for each metric")


class ProjectComparisonResponse(BaseAnalyticsResponse):
    """Response for project comparison"""
    data: List[ProjectComparisonEntry]
    summary: Dict[str, Any] = Field(default_factory=dict, description="Comparison summary")


# Export Schemas
class AnalyticsExportRequest(BaseModel):
    """Request for analytics data export"""
    query_type: str = Field(..., description="Type of analytics query to export")
    format: AnalyticsFormat = Field(AnalyticsFormat.JSON, description="Export format")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    include_raw_data: bool = Field(True, description="Include raw data in export")
    include_visualizations: bool = Field(False, description="Include chart visualizations")


class ExportJobStatus(str, Enum):
    """Export job status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalyticsExportJob(BaseModel):
    """Analytics export job information"""
    job_id: str = Field(description="Unique job identifier")
    status: ExportJobStatus = Field(description="Job status")
    created_at: datetime = Field(description="Job creation timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")
    file_size: Optional[int] = Field(None, description="Export file size in bytes")
    download_url: Optional[str] = Field(None, description="Download URL when ready")
    expires_at: Optional[datetime] = Field(None, description="Download link expiry")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class AnalyticsExportResponse(BaseModel):
    """Response for export request"""
    job: AnalyticsExportJob = Field(description="Export job information")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")


# Custom Query Schemas
class CustomQueryRequest(BaseModel):
    """Request for custom DuckDB query"""
    query: str = Field(..., description="SQL query to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    cache_ttl: Optional[int] = Field(None, description="Cache TTL in seconds")
    timeout: Optional[int] = Field(30, description="Query timeout in seconds")


class CustomQueryResponse(BaseAnalyticsResponse):
    """Response for custom query"""
    columns: List[str] = Field(description="Column names")
    query_plan: Optional[Dict[str, Any]] = Field(None, description="Query execution plan")


# WebSocket Real-time Analytics Schemas
class AnalyticsSubscription(BaseModel):
    """WebSocket analytics subscription"""
    subscription_id: str = Field(description="Unique subscription identifier")
    metric_type: str = Field(description="Type of metric to subscribe to")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Subscription filters")
    update_interval: int = Field(5, ge=1, le=300, description="Update interval in seconds")


class AnalyticsUpdate(BaseModel):
    """Real-time analytics update"""
    subscription_id: str = Field(description="Subscription identifier")
    timestamp: datetime = Field(description="Update timestamp")
    data: Any = Field(description="Updated analytics data")
    event_type: str = Field(description="Type of update event")


# Error Response Schemas
class AnalyticsErrorResponse(BaseModel):
    """Error response for analytics endpoints"""
    success: bool = Field(False)
    error_code: str = Field(description="Error code")
    error_message: str = Field(description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    suggestions: List[str] = Field(default_factory=list, description="Suggested fixes")