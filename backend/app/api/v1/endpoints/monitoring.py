"""
Monitoring and analytics endpoints
"""
from typing import Any, Dict
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_approved_user, require_permission
from app.models.user import User
from app.models.rbac import PermissionType
from app.services.monitoring import MonitoringService

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