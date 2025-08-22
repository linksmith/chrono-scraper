"""
Monitoring and analytics endpoints
"""
from typing import Any, Dict
from fastapi import APIRouter, Depends, Query, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_approved_user, require_permission
from app.models.user import User
from app.models.rbac import PermissionType
from app.services.monitoring import MonitoringService
from app.services.prometheus_metrics import PrometheusMetricsService

router = APIRouter()


@router.get("/system/overview")
async def get_system_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> Dict[str, Any]:
    """
    Get system-wide overview statistics (admin only)
    """
    overview = await MonitoringService.get_system_overview(db)
    return overview


@router.get("/dashboard")
async def get_user_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Get dashboard statistics for current user
    """
    stats = await MonitoringService.get_user_dashboard_stats(db, current_user.id)
    return stats


@router.get("/projects/{project_id}/analytics")
async def get_project_analytics(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Get detailed analytics for a project
    """
    analytics = await MonitoringService.get_project_analytics(
        db, project_id, current_user.id
    )
    
    if not analytics:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    return analytics


@router.get("/system/health")
async def get_system_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> Dict[str, Any]:
    """
    Get system health status (admin only)
    """
    health = await MonitoringService.get_system_health(db)
    return health


@router.get("/system/trends")
async def get_usage_trends(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> Dict[str, Any]:
    """
    Get usage trends over specified period (admin only)
    """
    trends = await MonitoringService.get_usage_trends(db, days)
    return trends


# Shared Pages Architecture Monitoring Endpoints

@router.get("/shared-pages/metrics")
async def get_shared_pages_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> Dict[str, Any]:
    """
    Get comprehensive shared pages architecture metrics (admin only)
    """
    metrics = await MonitoringService.get_shared_pages_metrics(db)
    return metrics


@router.get("/shared-pages/health")
async def get_shared_pages_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> Dict[str, Any]:
    """
    Get comprehensive health check for shared pages architecture (admin only)
    """
    health = await MonitoringService.get_shared_pages_health_check(db)
    return health


@router.get("/shared-pages/business-metrics")
async def get_shared_pages_business_metrics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> Dict[str, Any]:
    """
    Get business metrics for shared pages architecture adoption and efficiency (admin only)
    """
    metrics = await MonitoringService.get_shared_pages_business_metrics(db, days)
    return metrics


@router.get("/shared-pages/performance")
async def get_shared_pages_performance_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(PermissionType.ADMIN_VIEW))
) -> Dict[str, Any]:
    """
    Get real-time performance metrics for shared pages architecture (admin only)
    """
    import time
    start_time = time.time()
    
    # Measure response time for core metrics
    metrics = await MonitoringService.get_shared_pages_metrics(db)
    response_time = time.time() - start_time
    
    # Add performance metadata
    metrics["response_time_seconds"] = round(response_time, 3)
    metrics["response_status"] = "fast" if response_time < 1.0 else "normal" if response_time < 3.0 else "slow"
    
    return metrics


# Public health endpoint (no auth required)
@router.get("/health")
async def public_health_check(
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Public health check endpoint (no authentication required)
    """
    try:
        # Basic database connectivity check
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        
        from datetime import datetime
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy"
        )


# Enhanced public health endpoint with shared pages status
@router.get("/health/detailed")
async def detailed_health_check(
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Detailed health check including shared pages architecture status (no authentication required)
    """
    try:
        from datetime import datetime
        import time
        
        start_time = time.time()
        
        # Basic database connectivity
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
        
        # Quick shared pages health check
        from app.models.shared_pages import PageV2, ProjectPage, CDXPageRegistry
        pages_count = await db.execute(text("SELECT COUNT(*) FROM pages_v2"))
        associations_count = await db.execute(text("SELECT COUNT(*) FROM project_pages"))
        cdx_count = await db.execute(text("SELECT COUNT(*) FROM cdx_page_registry"))
        
        response_time = time.time() - start_time
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "response_time_seconds": round(response_time, 3),
            "components": {
                "database": "healthy",
                "shared_pages_architecture": "healthy"
            },
            "metrics": {
                "shared_pages_count": pages_count.scalar() or 0,
                "project_associations_count": associations_count.scalar() or 0,
                "cdx_registry_count": cdx_count.scalar() or 0
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: {str(e)}"
        )


# Prometheus Metrics Endpoints

@router.get("/prometheus/metrics")
async def get_prometheus_metrics(
    db: AsyncSession = Depends(get_db)
):
    """
    Get Prometheus metrics for the entire system (no authentication required for Prometheus scraping)
    """
    try:
        # Generate basic system metrics
        from app.services.monitoring import MonitoringService
        overview = await MonitoringService.get_system_overview(db)
        
        metrics_lines = [
            "# HELP chrono_users_total Total number of users",
            "# TYPE chrono_users_total gauge",
            f"chrono_users_total {overview['totals']['users']}",
            "",
            "# HELP chrono_projects_total Total number of projects", 
            "# TYPE chrono_projects_total gauge",
            f"chrono_projects_total {overview['totals']['projects']}",
            "",
            "# HELP chrono_domains_total Total number of domains",
            "# TYPE chrono_domains_total gauge", 
            f"chrono_domains_total {overview['totals']['domains']}",
            "",
            "# HELP chrono_pages_total Total number of pages",
            "# TYPE chrono_pages_total gauge",
            f"chrono_pages_total {overview['totals']['pages']}",
            "",
            "# HELP chrono_active_users Total number of active users",
            "# TYPE chrono_active_users gauge",
            f"chrono_active_users {overview['active']['users']}",
            "",
            "# HELP chrono_active_projects Total number of active projects",
            "# TYPE chrono_active_projects gauge",
            f"chrono_active_projects {overview['active']['projects']}",
            ""
        ]
        
        metrics_content = "\n".join(metrics_lines)
        return Response(content=metrics_content, media_type="text/plain")
        
    except Exception as e:
        error_metrics = [
            "# HELP chrono_metrics_error Metrics collection error",
            "# TYPE chrono_metrics_error gauge",
            "chrono_metrics_error 1"
        ]
        return Response(content="\n".join(error_metrics), media_type="text/plain")


@router.get("/shared-pages/prometheus")
async def get_shared_pages_prometheus_metrics(
    db: AsyncSession = Depends(get_db)
):
    """
    Get Prometheus metrics for shared pages architecture (no authentication required for Prometheus scraping)
    """
    try:
        metrics_content = await PrometheusMetricsService.generate_shared_pages_metrics(db)
        return Response(content=metrics_content, media_type="text/plain")
    except Exception as e:
        error_metrics = [
            "# HELP chrono_shared_pages_metrics_error Shared pages metrics collection error",
            "# TYPE chrono_shared_pages_metrics_error gauge",
            "chrono_shared_pages_metrics_error 1"
        ]
        return Response(content="\n".join(error_metrics), media_type="text/plain")


@router.get("/health/prometheus")
async def get_health_prometheus_metrics(
    db: AsyncSession = Depends(get_db)
):
    """
    Get Prometheus health metrics (no authentication required for Prometheus scraping)
    """
    try:
        metrics_content = await PrometheusMetricsService.generate_health_metrics(db)
        return Response(content=metrics_content, media_type="text/plain")
    except Exception as e:
        error_metrics = [
            "# HELP chrono_health_check_error Health check error",
            "# TYPE chrono_health_check_error gauge",
            "chrono_health_check_error 1"
        ]
        return Response(content="\n".join(error_metrics), media_type="text/plain")


@router.get("/business/prometheus")
async def get_business_prometheus_metrics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get Prometheus business metrics (no authentication required for Prometheus scraping)
    """
    try:
        metrics_content = await PrometheusMetricsService.generate_business_metrics(db, days)
        return Response(content=metrics_content, media_type="text/plain")
    except Exception as e:
        error_metrics = [
            "# HELP chrono_business_metrics_error Business metrics collection error",
            "# TYPE chrono_business_metrics_error gauge",
            "chrono_business_metrics_error 1"
        ]
        return Response(content="\n".join(error_metrics), media_type="text/plain")