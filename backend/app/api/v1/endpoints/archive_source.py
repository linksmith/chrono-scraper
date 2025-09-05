"""
Archive source management endpoints

Provides API endpoints for managing archive source configurations, including
impact assessment, connectivity testing, metrics collection, and safe transitions
between archive sources for projects.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_approved_user
from app.models.user import User
from app.models.project import ArchiveSource
from app.schemas.archive_source_schemas import (
    ArchiveSourceUpdateRequest, ArchiveSourceUpdateResponse, ArchiveSourceImpact,
    ArchiveSourceTestRequest, ArchiveSourceTestResponse, 
    ArchiveSourceMetricsResponse
)
from app.services.archive_source_manager import ArchiveSourceManager, ArchiveSourceManagerException

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize the archive source manager
archive_manager = ArchiveSourceManager()


@router.put("/{project_id}/archive-source", response_model=ArchiveSourceUpdateResponse)
async def update_project_archive_source(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    request: ArchiveSourceUpdateRequest,
    http_request: Request
) -> ArchiveSourceUpdateResponse:
    """
    Update the archive source configuration for a project.
    
    This endpoint allows changing the archive source (Wayback Machine, Common Crawl, or Hybrid),
    fallback settings, and archive-specific configuration. It includes safety checks and 
    impact assessment to prevent disruptive changes.
    
    **Safety Features:**
    - Impact assessment to identify potential issues
    - Confirmation required for high-impact changes
    - Audit logging for all changes
    - Rollback capability within 24 hours
    
    **Parameters:**
    - **archive_source**: The new archive source to use
    - **fallback_enabled**: Whether to enable fallback to other sources
    - **archive_config**: Source-specific configuration (optional)
    - **confirm_impact**: User acknowledges potential impact (required for risky changes)
    - **change_reason**: Optional reason for the change (recommended for audit trail)
    
    **Response:**
    Returns detailed information about the update including old/new configurations,
    warnings, and the timestamp of the change.
    
    **Error Conditions:**
    - 404: Project not found or access denied
    - 400: Update is unsafe and requires confirmation
    - 500: Internal error during update
    """
    try:
        # Extract request context for audit trail
        client_ip = (
            http_request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
            http_request.headers.get("x-real-ip") or
            getattr(http_request.client, "host", None)
        )
        user_agent = http_request.headers.get("user-agent")
        
        response = await archive_manager.update_archive_source(
            db=db,
            project_id=project_id,
            request=request,
            user_id=current_user.id,
            session_id=None,  # Could be extracted from session if available
            ip_address=client_ip,
            user_agent=user_agent
        )
        
        logger.info(f"Archive source updated for project {project_id} by user {current_user.id}")
        return response
        
    except ArchiveSourceManagerException as e:
        logger.error(f"Archive source manager error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error updating archive source: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while updating archive source"
        )


@router.get("/{project_id}/archive-source/impact-assessment", response_model=ArchiveSourceImpact)
async def assess_archive_source_impact(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    new_source: ArchiveSource
) -> ArchiveSourceImpact:
    """
    Assess the impact of changing to a new archive source.
    
    This endpoint analyzes the potential impact of switching archive sources without
    making any changes. It provides detailed information about coverage changes,
    performance impact, ongoing operations, and safety recommendations.
    
    **Assessment Areas:**
    - Data coverage impact (estimated percentage change)
    - Performance impact (response time changes)
    - Active scraping sessions that would be affected
    - Safety assessment and recommendations
    - Warnings about potential issues
    
    **Use Cases:**
    - Planning archive source migrations
    - Understanding impact before making changes
    - Validating archive source selection
    - Risk assessment for operations teams
    
    **Parameters:**
    - **new_source**: The archive source to assess (wayback, commoncrawl, hybrid)
    
    **Response:**
    Comprehensive impact assessment including coverage changes, performance impact,
    warnings, recommendations, and safety indicators.
    """
    try:
        impact = await archive_manager.assess_archive_source_impact(
            db=db,
            project_id=project_id,
            new_archive_source=new_source,
            user_id=current_user.id
        )
        
        logger.info(f"Impact assessment completed for project {project_id} -> {new_source}")
        return impact
        
    except ArchiveSourceManagerException as e:
        logger.error(f"Impact assessment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in impact assessment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during impact assessment"
        )


@router.post("/{project_id}/archive-source/test", response_model=ArchiveSourceTestResponse)
async def test_archive_source_connectivity(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    request: ArchiveSourceTestRequest
) -> ArchiveSourceTestResponse:
    """
    Test connectivity and performance of an archive source.
    
    This endpoint tests the specified archive source against project domains to verify
    connectivity, measure performance, and identify potential issues before switching
    archive sources.
    
    **Test Features:**
    - Connectivity verification
    - Response time measurement
    - Data availability checking
    - Error analysis and classification
    - Health status assessment
    
    **Test Process:**
    1. Uses project domains or specified test domains
    2. Queries the archive source with recent date ranges
    3. Measures response times and success rates
    4. Analyzes errors and provides recommendations
    5. Returns comprehensive test results
    
    **Parameters:**
    - **archive_source**: Archive source to test
    - **test_domains**: Specific domains to test (uses project domains if empty)
    - **timeout_seconds**: Test timeout per domain (default: 30 seconds)
    
    **Response:**
    Detailed test results including overall status, individual domain results,
    performance metrics, error analysis, and recommendations.
    """
    try:
        test_response = await archive_manager.test_archive_source_connectivity(
            db=db,
            project_id=project_id,
            request=request,
            user_id=current_user.id
        )
        
        logger.info(f"Archive source test completed for project {project_id}: "
                   f"{request.archive_source} - {test_response.overall_status}")
        return test_response
        
    except ArchiveSourceManagerException as e:
        logger.error(f"Archive source test error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in archive source test: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during archive source test"
        )


@router.get("/{project_id}/archive-source/metrics", response_model=ArchiveSourceMetricsResponse)
async def get_archive_source_metrics(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int,
    time_period: str = "24h"
) -> ArchiveSourceMetricsResponse:
    """
    Get performance metrics for archive sources used by a project.
    
    This endpoint provides comprehensive performance metrics for the archive sources
    currently configured for a project, including success rates, response times,
    error analysis, and health status.
    
    **Metrics Categories:**
    - **Request Statistics**: Total, successful, and failed requests
    - **Performance**: Response times, success rates, throughput
    - **Error Analysis**: Error types, frequencies, and patterns
    - **Health Status**: Circuit breaker states, health scores
    - **Usage Patterns**: Fallback events, source utilization
    
    **Time Periods:**
    - **24h**: Last 24 hours (default)
    - **7d**: Last 7 days
    - **30d**: Last 30 days
    
    **Parameters:**
    - **time_period**: Time period for metrics aggregation
    
    **Response:**
    Comprehensive metrics including per-source statistics, overall performance,
    circuit breaker status, and optimization recommendations.
    
    **Use Cases:**
    - Performance monitoring and optimization
    - Archive source health checking
    - Capacity planning and scaling decisions
    - Troubleshooting connectivity issues
    """
    try:
        # Validate time period
        valid_periods = ["24h", "7d", "30d"]
        if time_period not in valid_periods:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid time_period. Must be one of: {valid_periods}"
            )
        
        metrics = await archive_manager.get_archive_source_metrics(
            db=db,
            project_id=project_id,
            user_id=current_user.id,
            time_period=time_period
        )
        
        logger.info(f"Archive source metrics retrieved for project {project_id} "
                   f"(period: {time_period})")
        return metrics
        
    except ArchiveSourceManagerException as e:
        logger.error(f"Archive source metrics error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error retrieving archive source metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while retrieving metrics"
        )


@router.get("/{project_id}/archive-source/health")
async def get_archive_source_health(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    project_id: int
):
    """
    Get health status of archive sources for a project.
    
    This is a lightweight endpoint that provides quick health status information
    for the archive sources configured for a project. Useful for monitoring
    dashboards and health checks.
    
    **Health Indicators:**
    - Overall health status (healthy/degraded/unhealthy)
    - Individual source health
    - Circuit breaker states
    - Last success/failure times
    - Basic performance indicators
    
    **Response:**
    Lightweight health status information optimized for monitoring and alerting.
    """
    try:
        # This could be implemented by calling the archive service router directly
        # or by extracting health info from the full metrics
        metrics = await archive_manager.get_archive_source_metrics(
            db=db,
            project_id=project_id,
            user_id=current_user.id,
            time_period="24h"
        )
        
        # Extract health status from metrics
        health_status = {
            "project_id": project_id,
            "overall_health": "healthy" if metrics.overall_success_rate >= 80 else 
                            "degraded" if metrics.overall_success_rate >= 50 else "unhealthy",
            "sources": {
                name: {
                    "health": "healthy" if stats.success_rate >= 80 else
                             "degraded" if stats.success_rate >= 50 else "unhealthy",
                    "success_rate": stats.success_rate,
                    "circuit_breaker_state": stats.circuit_breaker_state,
                    "last_success": stats.last_success_at.isoformat() if stats.last_success_at else None
                }
                for name, stats in metrics.archive_sources.items()
            },
            "checked_at": metrics.generated_at.isoformat()
        }
        
        return JSONResponse(content=health_status)
        
    except Exception as e:
        logger.error(f"Error getting archive source health: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while checking health"
        )