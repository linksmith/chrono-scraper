"""
Analytics API Endpoints for Chrono Scraper FastAPI Application

Comprehensive analytics endpoints leveraging DuckDB for high-performance
OLAP operations and PostgreSQL for OLTP operations.

Features:
- Domain-level analytics and insights
- Project performance analytics
- Content quality analytics
- System-wide analytics and monitoring
- Multi-level caching and performance optimization
- Real-time metrics and WebSocket support
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from ....core.config import settings
from ....api import deps
from ....models.user import User
from ....services.analytics_service import (
    AnalyticsService, 
    get_analytics_service, 
    AnalyticsQueryContext
)
from ....schemas.analytics import (
    # Request schemas
    DomainTimelineRequest, DomainStatisticsRequest, TopDomainsRequest,
    ProjectPerformanceRequest, ProjectContentQualityRequest,
    ContentQualityDistributionRequest, SystemPerformanceRequest,
    TimeSeriesRequest, ProjectComparisonRequest,
    
    # Response schemas  
    DomainTimelineResponse, DomainStatisticsResponse, TopDomainsResponse,
    ProjectPerformanceResponse, ProjectContentQualityResponse,
    ContentQualityDistributionResponse, SystemPerformanceResponse,
    TimeSeriesResponse, ProjectComparisonResponse,
    BaseAnalyticsResponse, AnalyticsErrorResponse,
    
    # Data models
    TimeGranularity, AnalyticsScope, AnalyticsFormat,
    DomainTimelineDataPoint, DomainStatistics, TopDomainEntry,
    ProjectPerformanceData, ContentQualityMetrics, SystemPerformanceData,
    TimeSeriesDataPoint, ProjectComparisonEntry
)

logger = logging.getLogger(__name__)

router = APIRouter()


def create_analytics_context(
    current_user: User,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    use_cache: bool = True
) -> AnalyticsQueryContext:
    """Create analytics query context from request parameters"""
    return AnalyticsQueryContext(
        user_id=current_user.id,
        start_date=start_date,
        end_date=end_date,
        use_cache=use_cache
    )


def handle_analytics_error(e: Exception) -> AnalyticsErrorResponse:
    """Handle analytics errors and return structured error response"""
    if isinstance(e, ValidationError):
        return AnalyticsErrorResponse(
            error_code="VALIDATION_ERROR",
            error_message="Invalid request parameters",
            details={"validation_errors": e.errors()}
        )
    elif isinstance(e, ValueError):
        return AnalyticsErrorResponse(
            error_code="INVALID_REQUEST",
            error_message=str(e),
            suggestions=["Check request parameters and try again"]
        )
    elif "timeout" in str(e).lower():
        return AnalyticsErrorResponse(
            error_code="QUERY_TIMEOUT",
            error_message="Analytics query timed out",
            suggestions=["Try reducing the date range or adding more filters"]
        )
    else:
        logger.error(f"Analytics error: {e}", exc_info=True)
        return AnalyticsErrorResponse(
            error_code="INTERNAL_ERROR",
            error_message="An internal error occurred",
            suggestions=["Please try again later or contact support"]
        )


# Domain Analytics Endpoints
@router.get("/domains/{domain}/timeline", response_model=DomainTimelineResponse)
async def get_domain_timeline(
    domain: str,
    granularity: TimeGranularity = Query(TimeGranularity.DAY, description="Time granularity"),
    start_date: Optional[datetime] = Query(None, description="Start date for analysis"),
    end_date: Optional[datetime] = Query(None, description="End date for analysis"),
    include_subdomains: bool = Query(False, description="Include subdomain data"),
    use_cache: bool = Query(True, description="Use cached results"),
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get domain timeline analytics showing scraping activity over time.
    
    Returns time-series data with configurable granularity showing:
    - Pages scraped over time
    - Success/failure rates
    - Content size trends
    - Unique URL counts
    """
    try:
        context = create_analytics_context(current_user, start_date, end_date, use_cache)
        
        timeline_data = await analytics_service.get_domain_timeline(
            domain=domain,
            granularity=granularity,
            context=context
        )
        
        # Calculate summary statistics
        total_pages = sum(point.pages_scraped for point in timeline_data)
        total_successful = sum(point.pages_successful for point in timeline_data)
        avg_error_rate = sum(point.error_rate for point in timeline_data) / len(timeline_data) if timeline_data else 0
        total_content_mb = sum(point.content_size_mb for point in timeline_data)
        
        summary = {
            "total_pages": total_pages,
            "success_rate": (total_successful / total_pages * 100) if total_pages > 0 else 0,
            "avg_error_rate": avg_error_rate,
            "total_content_mb": total_content_mb,
            "time_span_days": (end_date - start_date).days if start_date and end_date else None
        }
        
        return DomainTimelineResponse(
            data=timeline_data,
            summary=summary,
            metadata={
                "domain": domain,
                "granularity": granularity.value,
                "data_points": len(timeline_data),
                "include_subdomains": include_subdomains
            },
            performance={
                "query_time_ms": 0,  # Would be populated by service
                "cached": False,     # Would be populated by service
                "database_used": "hybrid"
            }
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


@router.get("/domains/{domain}/statistics", response_model=DomainStatisticsResponse)
async def get_domain_statistics(
    domain: str,
    start_date: Optional[datetime] = Query(None, description="Start date for analysis"),
    end_date: Optional[datetime] = Query(None, description="End date for analysis"),
    include_detailed_metrics: bool = Query(True, description="Include detailed performance metrics"),
    use_cache: bool = Query(True, description="Use cached results"),
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get comprehensive domain statistics including:
    - Total pages and success rates
    - Content size metrics
    - Popular paths and content types
    - Error distribution
    - Performance metrics
    """
    try:
        context = create_analytics_context(current_user, start_date, end_date, use_cache)
        
        domain_stats = await analytics_service.get_domain_statistics(
            domain=domain,
            context=context
        )
        
        return DomainStatisticsResponse(
            data=domain_stats,
            metadata={
                "domain": domain,
                "analysis_period": {
                    "start": start_date,
                    "end": end_date
                },
                "detailed_metrics_included": include_detailed_metrics
            },
            performance={
                "query_time_ms": 0,
                "cached": False,
                "database_used": "hybrid"
            }
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


@router.get("/domains/top-domains", response_model=TopDomainsResponse)
async def get_top_domains(
    metric: str = Query("total_pages", description="Metric to rank by"),
    limit: int = Query(50, ge=1, le=500, description="Number of domains to return"),
    start_date: Optional[datetime] = Query(None, description="Start date for analysis"),
    end_date: Optional[datetime] = Query(None, description="End date for analysis"),
    include_inactive: bool = Query(False, description="Include domains with no recent activity"),
    use_cache: bool = Query(True, description="Use cached results"),
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get top domains ranked by specified metric:
    - total_pages: Total pages scraped
    - success_rate: Scraping success rate percentage  
    - content_size: Total content size collected
    """
    try:
        # Validate metric parameter
        valid_metrics = ["total_pages", "success_rate", "content_size"]
        if metric not in valid_metrics:
            raise ValueError(f"Invalid metric '{metric}'. Must be one of: {valid_metrics}")
        
        context = create_analytics_context(current_user, start_date, end_date, use_cache)
        
        top_domains = await analytics_service.get_top_domains(
            metric=metric,
            limit=limit,
            context=context
        )
        
        return TopDomainsResponse(
            data=top_domains,
            metadata={
                "ranking_metric": metric,
                "total_domains": len(top_domains),
                "analysis_period": {
                    "start": start_date,
                    "end": end_date
                },
                "include_inactive": include_inactive
            },
            performance={
                "query_time_ms": 0,
                "cached": False,
                "database_used": "duckdb"
            }
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


@router.get("/domains/coverage-analysis")
async def get_domain_coverage_analysis(
    domains: List[str] = Query(..., description="Domains to analyze"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Analyze domain coverage including:
    - URL coverage percentages
    - Content freshness analysis
    - Scraping gaps identification
    """
    try:
        # This would be implemented with more complex coverage analysis
        # For now, return placeholder structure
        coverage_data = {
            "domains": domains,
            "coverage_summary": {
                "total_urls_discovered": 0,
                "urls_scraped": 0,
                "coverage_percentage": 0.0
            },
            "freshness_analysis": {
                "fresh_content_percentage": 0.0,
                "stale_content_percentage": 0.0,
                "avg_content_age_days": 0.0
            },
            "gaps_identified": []
        }
        
        return BaseAnalyticsResponse(
            data=coverage_data,
            metadata={"domains_analyzed": len(domains)},
            performance={"query_time_ms": 0, "cached": False}
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


# Project Analytics Endpoints
@router.get("/projects/{project_id}/performance", response_model=ProjectPerformanceResponse)
async def get_project_performance(
    project_id: UUID,
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    include_domain_breakdown: bool = Query(True, description="Include per-domain breakdown"),
    include_time_series: bool = Query(False, description="Include time series data"),
    use_cache: bool = Query(True, description="Use cached results"),
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get comprehensive project performance analytics including:
    - Overall scraping metrics
    - Success rates and error analysis
    - Domain-level breakdown
    - Performance trends
    """
    try:
        context = create_analytics_context(current_user, start_date, end_date, use_cache)
        
        performance_data = await analytics_service.get_project_performance(
            project_id=project_id,
            include_domain_breakdown=include_domain_breakdown,
            context=context
        )
        
        return ProjectPerformanceResponse(
            data=performance_data,
            metadata={
                "project_id": str(project_id),
                "analysis_period": {
                    "start": start_date,
                    "end": end_date
                },
                "includes_domain_breakdown": include_domain_breakdown,
                "includes_time_series": include_time_series
            },
            performance={
                "query_time_ms": 0,
                "cached": False,
                "database_used": "hybrid"
            }
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


@router.get("/projects/{project_id}/content-quality", response_model=ProjectContentQualityResponse)
async def get_project_content_quality(
    project_id: UUID,
    quality_threshold: float = Query(0.7, ge=0.0, le=1.0, description="Quality score threshold"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    use_cache: bool = Query(True, description="Use cached results"),
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Analyze project content quality including:
    - Quality score distribution
    - Content completeness metrics
    - Extraction accuracy analysis
    - Quality trends over time
    """
    try:
        # This would integrate with content quality scoring service
        # For now, return placeholder structure
        quality_metrics = ContentQualityMetrics(
            project_id=project_id,
            total_pages=0,
            high_quality_pages=0,
            medium_quality_pages=0,
            low_quality_pages=0,
            avg_quality_score=0.0,
            content_completeness=0.0,
            extraction_accuracy=0.0,
            duplicate_content_rate=0.0
        )
        
        return ProjectContentQualityResponse(
            data=quality_metrics,
            metadata={
                "project_id": str(project_id),
                "quality_threshold": quality_threshold,
                "analysis_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            performance={
                "query_time_ms": 0,
                "cached": False,
                "database_used": "duckdb"
            }
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


@router.get("/projects/{project_id}/scraping-efficiency")
async def get_project_scraping_efficiency(
    project_id: UUID,
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Analyze project scraping efficiency including:
    - Pages per hour rates
    - Resource utilization
    - Cost effectiveness metrics
    - Optimization suggestions
    """
    try:
        # This would calculate detailed efficiency metrics
        efficiency_data = {
            "project_id": str(project_id),
            "efficiency_metrics": {
                "pages_per_hour": 0.0,
                "success_rate": 0.0,
                "avg_response_time": 0.0,
                "resource_utilization": 0.0
            },
            "cost_analysis": {
                "estimated_cost": 0.0,
                "cost_per_page": 0.0,
                "cost_efficiency_score": 0.0
            },
            "optimization_suggestions": []
        }
        
        return BaseAnalyticsResponse(
            data=efficiency_data,
            metadata={"project_id": str(project_id)},
            performance={"query_time_ms": 0, "cached": False}
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


@router.post("/projects/comparison", response_model=ProjectComparisonResponse)
async def compare_projects(
    request: ProjectComparisonRequest,
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Compare multiple projects across various metrics:
    - Success rates and performance
    - Content quality scores
    - Resource efficiency
    - Cost analysis
    """
    try:
        # This would implement detailed project comparison
        comparison_data = []
        for i, project_id in enumerate(request.project_ids):
            comparison_data.append(ProjectComparisonEntry(
                project_id=project_id,
                project_name=f"Project {i+1}",
                metrics={metric: 0.0 for metric in request.metrics},
                rank={metric: i+1 for metric in request.metrics}
            ))
        
        summary = {
            "projects_compared": len(request.project_ids),
            "metrics_analyzed": len(request.metrics),
            "top_performer": comparison_data[0].project_name if comparison_data else None
        }
        
        return ProjectComparisonResponse(
            data=comparison_data,
            summary=summary,
            metadata={
                "comparison_metrics": request.metrics,
                "analysis_period": {
                    "start": request.start_date,
                    "end": request.end_date
                }
            }
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


# Content Analytics Endpoints
@router.get("/content/quality-distribution", response_model=ContentQualityDistributionResponse)
async def get_content_quality_distribution(
    projects: Optional[List[UUID]] = Query(None, description="Specific projects to analyze"),
    domains: Optional[List[str]] = Query(None, description="Specific domains to analyze"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    use_cache: bool = Query(True, description="Use cached results"),
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get content quality distribution across projects and domains:
    - Quality score buckets and distributions
    - Content size correlations
    - Domain-level quality patterns
    """
    try:
        # This would implement quality distribution analysis
        distribution_data = ContentQualityDistributionData(
            total_pages_analyzed=0,
            distribution=[],
            overall_avg_quality=0.0,
            quality_improvement_trend=0.0
        )
        
        return ContentQualityDistributionResponse(
            data=distribution_data,
            metadata={
                "projects_analyzed": len(projects) if projects else 0,
                "domains_analyzed": len(domains) if domains else 0,
                "analysis_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            performance={
                "query_time_ms": 0,
                "cached": False,
                "database_used": "duckdb"
            }
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


@router.get("/content/extraction-performance")
async def get_extraction_performance(
    extraction_method: Optional[str] = Query(None, description="Filter by extraction method"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Analyze content extraction performance:
    - Extraction success rates by method
    - Processing time analysis
    - Content completeness metrics
    """
    try:
        performance_data = {
            "extraction_methods": {
                "firecrawl": {
                    "success_rate": 0.0,
                    "avg_processing_time": 0.0,
                    "content_completeness": 0.0
                }
            },
            "overall_metrics": {
                "total_extractions": 0,
                "avg_success_rate": 0.0,
                "avg_processing_time": 0.0
            },
            "performance_trends": []
        }
        
        return BaseAnalyticsResponse(
            data=performance_data,
            metadata={"extraction_method_filter": extraction_method}
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


# System Analytics Endpoints  
@router.get("/system/performance-overview", response_model=SystemPerformanceResponse)
async def get_system_performance_overview(
    include_resource_usage: bool = Query(True, description="Include resource usage metrics"),
    include_database_metrics: bool = Query(True, description="Include database metrics"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    use_cache: bool = Query(True, description="Use cached results"),
    current_user: User = Depends(deps.get_current_active_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get comprehensive system performance overview:
    - Overall system health metrics
    - Database performance statistics
    - Resource utilization analysis
    - Active users and projects
    """
    try:
        context = create_analytics_context(current_user, start_date, end_date, use_cache)
        
        system_data = await analytics_service.get_system_performance(
            include_database_metrics=include_database_metrics,
            context=context
        )
        
        return SystemPerformanceResponse(
            data=system_data,
            metadata={
                "includes_resource_usage": include_resource_usage,
                "includes_database_metrics": include_database_metrics,
                "analysis_period": {
                    "start": start_date,
                    "end": end_date
                }
            },
            performance={
                "query_time_ms": 0,
                "cached": False,
                "database_used": "hybrid"
            }
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=500, detail=error_response.dict())


@router.get("/system/resource-utilization")
async def get_resource_utilization(
    time_window: int = Query(24, description="Time window in hours"),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get detailed system resource utilization:
    - CPU and memory usage
    - Database connection pool status
    - Cache hit rates
    - Network I/O metrics
    """
    try:
        # This would integrate with system monitoring
        resource_data = {
            "cpu_usage": {
                "current": 0.0,
                "avg_24h": 0.0,
                "peak_24h": 0.0
            },
            "memory_usage": {
                "current_mb": 0.0,
                "avg_24h_mb": 0.0,
                "peak_24h_mb": 0.0
            },
            "database_pools": {
                "postgresql": {
                    "active_connections": 0,
                    "pool_utilization": 0.0
                },
                "duckdb": {
                    "active_connections": 0,
                    "pool_utilization": 0.0
                }
            },
            "cache_performance": {
                "hit_rate": 0.0,
                "miss_rate": 0.0,
                "avg_response_time": 0.0
            }
        }
        
        return BaseAnalyticsResponse(
            data=resource_data,
            metadata={"time_window_hours": time_window}
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=500, detail=error_response.dict())


# Time Series Analytics Endpoints
@router.get("/time-series/{metric}", response_model=TimeSeriesResponse)
async def get_time_series_analytics(
    metric: str,
    granularity: TimeGranularity = Query(TimeGranularity.DAY, description="Time granularity"),
    aggregation: str = Query("sum", description="Aggregation function"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    include_forecast: bool = Query(False, description="Include forecast data"),
    current_user: User = Depends(deps.get_current_active_user)
):
    """
    Get time series analytics for specified metrics:
    - Domain growth over time
    - Content quality trends
    - System performance metrics
    - User activity patterns
    """
    try:
        # This would implement time series analysis
        time_series_data = []
        
        # Generate sample data points
        if start_date and end_date:
            current_date = start_date
            while current_date <= end_date:
                time_series_data.append(TimeSeriesDataPoint(
                    timestamp=current_date,
                    value=0.0,
                    metadata={"metric": metric}
                ))
                
                # Increment based on granularity
                if granularity == TimeGranularity.DAY:
                    current_date += timedelta(days=1)
                elif granularity == TimeGranularity.HOUR:
                    current_date += timedelta(hours=1)
                else:
                    current_date += timedelta(days=1)
        
        forecast_data = None
        if include_forecast:
            forecast_data = []  # Would include forecast points
        
        trends = {
            "overall_trend": "stable",
            "trend_strength": 0.0,
            "seasonal_pattern": False
        }
        
        return TimeSeriesResponse(
            data=time_series_data,
            forecast=forecast_data,
            trends=trends,
            metadata={
                "metric": metric,
                "granularity": granularity.value,
                "aggregation": aggregation,
                "data_points": len(time_series_data)
            }
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=400, detail=error_response.dict())


# Health and Status Endpoints
@router.get("/health")
async def get_analytics_health(
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """Get analytics service health status and performance metrics"""
    try:
        health_data = await analytics_service.get_service_health()
        
        return JSONResponse(
            status_code=200 if health_data["status"] == "healthy" else 503,
            content=health_data
        )
        
    except Exception as e:
        logger.error(f"Analytics health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@router.post("/cache/invalidate")
async def invalidate_analytics_cache(
    pattern: str = Query("*", description="Cache pattern to invalidate"),
    current_user: User = Depends(deps.get_current_admin_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """Invalidate analytics cache (admin only)"""
    try:
        await analytics_service.invalidate_cache(pattern)
        
        return BaseAnalyticsResponse(
            data={"invalidated_pattern": pattern},
            metadata={"operation": "cache_invalidation"}
        )
        
    except Exception as e:
        error_response = handle_analytics_error(e)
        raise HTTPException(status_code=500, detail=error_response.dict())