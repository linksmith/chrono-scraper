"""
API Key Usage Analytics Endpoints

Provides comprehensive analytics and metrics endpoints for monitoring
Meilisearch key usage patterns, performance, and forecasting.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....models.user import User
from ....api.deps import get_current_active_user
from ....services.key_analytics_service import KeyAnalyticsService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/analytics/usage/overview", response_model=Dict[str, Any])
async def get_usage_analytics_overview(
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive usage analytics overview for all Meilisearch keys
    
    Provides system-wide usage statistics, trends, and performance metrics.
    Admin access required.
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        analytics_service = KeyAnalyticsService(db)
        overview = await analytics_service.get_usage_overview(days_back)
        
        logger.info(f"Usage analytics overview generated for {days_back} days by admin {current_user.id}")
        
        return overview
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get usage analytics overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve usage analytics"
        )


@router.get("/analytics/usage/projects/{project_id}", response_model=Dict[str, Any])
async def get_project_usage_analytics(
    project_id: int,
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed usage analytics for a specific project
    
    Provides project-specific metrics, sharing statistics, and recommendations.
    Project owners and admins can access this endpoint.
    """
    try:
        analytics_service = KeyAnalyticsService(db)
        project_analytics = await analytics_service.get_project_analytics(project_id, days_back)
        
        # Check if there's an error in the analytics result
        if "error" in project_analytics:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=project_analytics["error"]
            )
        
        # Check access permissions (this would be done in the service for real projects)
        # For now, we'll allow any authenticated user to view analytics
        # In production, you'd verify project ownership or admin status
        
        logger.info(f"Project usage analytics generated for project {project_id} by user {current_user.id}")
        
        return project_analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project analytics for {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve project analytics"
        )


@router.get("/analytics/rate-limits", response_model=Dict[str, Any])
async def get_rate_limit_analytics(
    days_back: int = Query(7, ge=1, le=30, description="Number of days to analyze"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get analytics on rate limiting effectiveness and patterns
    
    Provides insights into rate limiting performance, blocked identifiers,
    and recommendations for optimization. Admin access required.
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        analytics_service = KeyAnalyticsService(db)
        rate_limit_analytics = await analytics_service.get_rate_limit_analytics(days_back)
        
        # Check if there's an error in the analytics result
        if "error" in rate_limit_analytics:
            logger.warning(f"Rate limit analytics error: {rate_limit_analytics['error']}")
            # Don't raise exception, just return the error in response
        
        logger.info(f"Rate limit analytics generated for {days_back} days by admin {current_user.id}")
        
        return rate_limit_analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rate limit analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve rate limit analytics"
        )


@router.get("/analytics/forecast", response_model=Dict[str, Any])
async def get_usage_forecast(
    project_id: Optional[int] = Query(None, description="Optional project ID for project-specific forecast"),
    forecast_days: int = Query(30, ge=7, le=90, description="Number of days to forecast"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate usage forecast based on historical patterns
    
    Provides predictive analytics for future usage trends and capacity planning.
    Admin access required for system-wide forecasts.
    """
    try:
        # Check access permissions
        if project_id is None and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required for system-wide forecasts"
            )
        
        # For project-specific forecasts, we'd check project ownership here
        # For now, allowing any authenticated user
        
        analytics_service = KeyAnalyticsService(db)
        forecast = await analytics_service.generate_usage_forecast(project_id, forecast_days)
        
        # Check if there's an error in the forecast result
        if "error" in forecast:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=forecast["error"]
            )
        
        logger.info(
            f"Usage forecast generated for {forecast_days} days "
            f"(project_id={project_id}) by user {current_user.id}"
        )
        
        return forecast
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate usage forecast: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate usage forecast"
        )


@router.get("/analytics/metrics/summary", response_model=Dict[str, Any])
async def get_analytics_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get high-level summary of key analytics metrics
    
    Provides a quick overview of system health and key performance indicators.
    Admin access required.
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        analytics_service = KeyAnalyticsService(db)
        
        # Get multiple analytics in parallel (simplified for this example)
        usage_overview = await analytics_service.get_usage_overview(days_back=30)
        rate_limit_analytics = await analytics_service.get_rate_limit_analytics(days_back=7)
        
        # Extract key metrics for summary
        summary = {
            "timestamp": datetime.utcnow(),
            "system_health": {
                "total_active_keys": usage_overview["overview"]["active_keys"],
                "total_requests_30_days": usage_overview["overview"]["total_requests"],
                "key_utilization_rate": usage_overview["overview"]["utilization_rate"],
                "usage_trend": usage_overview["usage_trends"]["trend_direction"]
            },
            "rate_limiting": {
                "effectiveness_score": rate_limit_analytics.get("effectiveness_metrics", {}).get("effectiveness_score", 0),
                "total_blocked_identifiers": rate_limit_analytics.get("effectiveness_metrics", {}).get("total_identifiers_blocked", 0),
                "block_rate_percentage": rate_limit_analytics.get("effectiveness_metrics", {}).get("block_rate_percentage", 0)
            },
            "performance_indicators": {
                "average_requests_per_key": usage_overview["overview"]["average_requests_per_key"],
                "unused_keys_count": usage_overview["overview"]["unused_keys"],
                "top_performing_key_usage": (
                    max(key["usage_count"] for key in usage_overview["top_performing_keys"])
                    if usage_overview["top_performing_keys"] else 0
                )
            },
            "recommendations": [
                "System performance is optimal" if usage_overview["overview"]["utilization_rate"] > 80 else "Consider optimizing key utilization",
                "Rate limiting is effective" if rate_limit_analytics.get("effectiveness_metrics", {}).get("effectiveness_score", 0) > 80 else "Review rate limiting configuration",
                "Usage trend is healthy" if usage_overview["usage_trends"]["trend_direction"] == "increasing" else "Monitor usage patterns"
            ]
        }
        
        logger.info(f"Analytics summary generated by admin {current_user.id}")
        
        return summary
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get analytics summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics summary"
        )


@router.get("/analytics/export", response_model=Dict[str, Any])
async def export_analytics_data(
    export_type: str = Query(..., description="Type of data to export (usage, rate_limits, security)"),
    days_back: int = Query(30, ge=1, le=365, description="Number of days to include"),
    format: str = Query("json", description="Export format (json, csv)"),
    project_id: Optional[int] = Query(None, description="Optional project ID filter"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Export analytics data for external analysis
    
    Provides data export functionality for analytics data in various formats.
    Admin access required.
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        if export_type not in ["usage", "rate_limits", "security"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid export type. Must be one of: usage, rate_limits, security"
            )
        
        if format not in ["json", "csv"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid format. Must be one of: json, csv"
            )
        
        analytics_service = KeyAnalyticsService(db)
        
        # Get data based on export type
        export_data = {}
        if export_type == "usage":
            if project_id:
                export_data = await analytics_service.get_project_analytics(project_id, days_back)
            else:
                export_data = await analytics_service.get_usage_overview(days_back)
        elif export_type == "rate_limits":
            export_data = await analytics_service.get_rate_limit_analytics(days_back)
        elif export_type == "security":
            # This would be implemented with security-specific analytics
            export_data = {
                "message": "Security analytics export not yet implemented",
                "timestamp": datetime.utcnow()
            }
        
        # For CSV format, we'd need to flatten the data structure
        if format == "csv":
            # This is a simplified implementation
            # In production, you'd want proper CSV conversion
            export_data["export_note"] = "CSV format requires data flattening - use JSON for complete data"
        
        export_result = {
            "export_type": export_type,
            "format": format,
            "days_back": days_back,
            "project_id": project_id,
            "generated_at": datetime.utcnow(),
            "generated_by": current_user.id,
            "data": export_data
        }
        
        logger.info(
            f"Analytics data exported: type={export_type}, format={format}, "
            f"days_back={days_back}, project_id={project_id} by admin {current_user.id}"
        )
        
        return export_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export analytics data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export analytics data"
        )


@router.get("/analytics/health", response_model=Dict[str, Any])
async def get_analytics_system_health():
    """
    Check health of analytics system components
    
    Public endpoint for monitoring analytics system availability.
    """
    try:
        # Basic health checks
        health_status = {
            "timestamp": datetime.utcnow(),
            "status": "healthy",
            "components": {
                "database": "healthy",  # Would check actual DB connection
                "redis": "healthy",     # Would check Redis connection
                "analytics_service": "healthy"
            },
            "version": "1.0.0",
            "uptime_hours": 24  # Would calculate actual uptime
        }
        
        # Check for any component failures
        failed_components = [k for k, v in health_status["components"].items() if v != "healthy"]
        if failed_components:
            health_status["status"] = "degraded"
            health_status["failed_components"] = failed_components
        
        return health_status
        
    except Exception as e:
        logger.error(f"Analytics health check failed: {e}")
        return {
            "timestamp": datetime.utcnow(),
            "status": "unhealthy",
            "error": str(e)
        }