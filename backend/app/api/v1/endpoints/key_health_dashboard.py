"""
Meilisearch Key Health Dashboard

Provides comprehensive monitoring endpoints for tracking the health,
usage, and security status of all Meilisearch keys in the multi-tenant system.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ....core.database import get_db
from ....models.user import User
from ....models.project import Project
from ....models.meilisearch_audit import (
    MeilisearchKey, MeilisearchKeyType, MeilisearchSecurityEvent, 
    MeilisearchUsageLog
)
from ....models.sharing import PublicSearchConfig, ProjectShare
from ....services.meilisearch_key_manager import meilisearch_key_manager
from ....api.deps import get_current_active_user
from ....core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/key-health/overview", response_model=Dict[str, Any])
async def get_key_health_overview(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive overview of Meilisearch key health across the system
    
    Only accessible by admin users for system monitoring.
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        # Get total key counts by type
        key_counts_query = select(
            MeilisearchKey.key_type,
            func.count(MeilisearchKey.id).label('count'),
            func.count(
                MeilisearchKey.id.op('FILTER')(
                    MeilisearchKey.is_active == True
                )
            ).label('active_count')
        ).group_by(MeilisearchKey.key_type)
        
        key_counts_result = await db.execute(key_counts_query)
        key_counts = key_counts_result.all()
        
        # Get keys requiring rotation (older than rotation period)
        rotation_cutoff = datetime.utcnow() - timedelta(days=settings.MEILISEARCH_KEY_ROTATION_DAYS)
        
        keys_needing_rotation_query = select(func.count(MeilisearchKey.id)).where(
            and_(
                MeilisearchKey.is_active == True,
                MeilisearchKey.key_type == MeilisearchKeyType.PROJECT_OWNER,
                MeilisearchKey.created_at < rotation_cutoff
            )
        )
        keys_needing_rotation_result = await db.execute(keys_needing_rotation_query)
        keys_needing_rotation = keys_needing_rotation_result.scalar() or 0
        
        # Get recent security events (last 24 hours)
        security_events_cutoff = datetime.utcnow() - timedelta(hours=24)
        
        recent_security_events_query = select(
            MeilisearchSecurityEvent.severity,
            func.count(MeilisearchSecurityEvent.id).label('count')
        ).where(
            MeilisearchSecurityEvent.created_at >= security_events_cutoff
        ).group_by(MeilisearchSecurityEvent.severity)
        
        security_events_result = await db.execute(recent_security_events_query)
        security_events = security_events_result.all()
        
        # Get key usage statistics (last 7 days)
        usage_cutoff = datetime.utcnow() - timedelta(days=7)
        
        key_usage_query = select(
            func.sum(MeilisearchKey.usage_count).label('total_usage'),
            func.avg(MeilisearchKey.usage_count).label('avg_usage'),
            func.count(MeilisearchKey.id.op('FILTER')(
                MeilisearchKey.last_used_at >= usage_cutoff
            )).label('recently_used_keys')
        ).where(MeilisearchKey.is_active == True)
        
        usage_result = await db.execute(key_usage_query)
        usage_stats = usage_result.first()
        
        # Get project coverage (projects with/without dedicated keys)
        projects_with_keys_query = select(func.count(Project.id)).where(
            and_(
                Project.process_documents == True,
                Project.index_search_key.isnot(None)
            )
        )
        projects_with_keys_result = await db.execute(projects_with_keys_query)
        projects_with_keys = projects_with_keys_result.scalar() or 0
        
        total_projects_query = select(func.count(Project.id)).where(
            Project.process_documents == True
        )
        total_projects_result = await db.execute(total_projects_query)
        total_projects = total_projects_result.scalar() or 0
        
        # Check Meilisearch service health
        try:
            admin_service = await meilisearch_key_manager.get_admin_client()
            meilisearch_health = await admin_service.health()
            meilisearch_status = "healthy"
        except Exception as e:
            meilisearch_health = {"error": str(e)}
            meilisearch_status = "unhealthy"
        
        # Compile overview
        overview = {
            "timestamp": datetime.utcnow(),
            "system_health": {
                "meilisearch_status": meilisearch_status,
                "meilisearch_health": meilisearch_health
            },
            "key_statistics": {
                "total_keys": sum(row.count for row in key_counts),
                "active_keys": sum(row.active_count for row in key_counts),
                "keys_by_type": {
                    row.key_type.value: {
                        "total": row.count,
                        "active": row.active_count
                    }
                    for row in key_counts
                },
                "keys_needing_rotation": keys_needing_rotation,
                "rotation_health_score": max(0, 100 - (keys_needing_rotation * 10))
            },
            "project_coverage": {
                "total_projects": total_projects,
                "projects_with_keys": projects_with_keys,
                "coverage_percentage": (projects_with_keys / total_projects * 100) if total_projects > 0 else 0,
                "projects_without_keys": total_projects - projects_with_keys
            },
            "usage_statistics": {
                "total_usage_7_days": int(usage_stats.total_usage or 0),
                "average_usage_per_key": float(usage_stats.avg_usage or 0),
                "recently_used_keys": int(usage_stats.recently_used_keys or 0)
            },
            "security_events_24h": {
                event.severity: event.count
                for event in security_events
            },
            "health_score": _calculate_system_health_score(
                meilisearch_status,
                keys_needing_rotation,
                total_projects - projects_with_keys,
                security_events
            )
        }
        
        return overview
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get key health overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve key health overview"
        )


@router.get("/key-health/projects/{project_id}", response_model=Dict[str, Any])
async def get_project_key_health(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get detailed key health information for a specific project
    """
    try:
        # Verify user has access to this project (owner or admin)
        project_query = select(Project).where(Project.id == project_id)
        project_result = await db.execute(project_query)
        project = project_result.scalar_one_or_none()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check access permissions
        if not current_user.is_superuser and project.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project"
            )
        
        # Get all keys for this project
        project_keys_query = select(MeilisearchKey).where(
            MeilisearchKey.project_id == project_id
        ).order_by(desc(MeilisearchKey.created_at))
        
        project_keys_result = await db.execute(project_keys_query)
        project_keys = project_keys_result.scalars().all()
        
        # Get security events for this project
        security_events_query = select(MeilisearchSecurityEvent).where(
            or_(
                MeilisearchSecurityEvent.key_id.in_([key.id for key in project_keys]),
                and_(
                    MeilisearchSecurityEvent.metadata.op('->>')('project_id') == str(project_id),
                    MeilisearchSecurityEvent.metadata.isnot(None)
                )
            )
        ).order_by(desc(MeilisearchSecurityEvent.created_at)).limit(50)
        
        security_events_result = await db.execute(security_events_query)
        security_events = security_events_result.scalars().all()
        
        # Check key health status
        key_health_status = []
        for key in project_keys:
            if key.is_active and key.key_uid:
                try:
                    # Check key status in Meilisearch
                    key_status = await meilisearch_key_manager.get_key_status(key.key_uid)
                    health_status = "healthy" if key_status.get("status") == "active" else "unhealthy"
                except Exception as e:
                    health_status = f"error: {str(e)}"
                    key_status = {"error": str(e)}
            else:
                health_status = "inactive"
                key_status = {"status": "inactive"}
            
            key_health_status.append({
                "key_id": key.id,
                "key_uid": key.key_uid,
                "key_type": key.key_type.value,
                "health_status": health_status,
                "meilisearch_status": key_status,
                "created_at": key.created_at,
                "last_used_at": key.last_used_at,
                "usage_count": key.usage_count,
                "is_active": key.is_active
            })
        
        # Get sharing configuration
        sharing_info = {}
        if project_keys:
            # Check for public search config
            public_config_query = select(PublicSearchConfig).where(
                PublicSearchConfig.project_id == project_id
            )
            public_config_result = await db.execute(public_config_query)
            public_config = public_config_result.scalar_one_or_none()
            
            # Check for project shares
            shares_query = select(ProjectShare).where(
                ProjectShare.project_id == project_id
            )
            shares_result = await db.execute(shares_query)
            shares = shares_result.scalars().all()
            
            sharing_info = {
                "public_search_enabled": bool(public_config and public_config.is_enabled),
                "public_search_config": {
                    "rate_limit_per_hour": public_config.rate_limit_per_hour if public_config else None,
                    "allow_downloads": public_config.allow_downloads if public_config else None,
                    "search_key_uid": public_config.search_key_uid if public_config else None
                } if public_config else None,
                "active_shares": len([s for s in shares if s.status.value == "active"]),
                "total_shares": len(shares)
            }
        
        # Calculate project health score
        project_health_score = _calculate_project_health_score(
            project, project_keys, security_events
        )
        
        return {
            "project_id": project_id,
            "project_name": project.name,
            "timestamp": datetime.utcnow(),
            "key_health": key_health_status,
            "security_events": [
                {
                    "id": event.id,
                    "event_type": event.event_type,
                    "severity": event.severity,
                    "description": event.description,
                    "created_at": event.created_at,
                    "automated": event.automated,
                    "metadata": event.metadata
                }
                for event in security_events
            ],
            "sharing_info": sharing_info,
            "health_score": project_health_score,
            "recommendations": _get_project_recommendations(project, project_keys, security_events)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get project key health for {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve project key health"
        )


@router.get("/key-health/rotation-candidates", response_model=Dict[str, Any])
async def get_rotation_candidates(
    days_threshold: int = Query(90, ge=1, le=365, description="Days since creation to consider for rotation"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get list of keys that should be rotated based on age threshold
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        rotation_cutoff = datetime.utcnow() - timedelta(days=days_threshold)
        
        # Get keys needing rotation
        rotation_candidates_query = select(
            MeilisearchKey,
            Project.name.label('project_name'),
            Project.user_id.label('project_owner_id')
        ).join(Project).where(
            and_(
                MeilisearchKey.is_active == True,
                MeilisearchKey.key_type == MeilisearchKeyType.PROJECT_OWNER,
                MeilisearchKey.created_at < rotation_cutoff
            )
        ).order_by(MeilisearchKey.created_at)
        
        candidates_result = await db.execute(rotation_candidates_query)
        candidates = candidates_result.all()
        
        rotation_candidates = []
        for key, project_name, project_owner_id in candidates:
            age_days = (datetime.utcnow() - key.created_at).days
            
            rotation_candidates.append({
                "key_id": key.id,
                "key_uid": key.key_uid,
                "project_id": key.project_id,
                "project_name": project_name,
                "project_owner_id": project_owner_id,
                "created_at": key.created_at,
                "age_days": age_days,
                "usage_count": key.usage_count,
                "last_used_at": key.last_used_at,
                "rotation_priority": _calculate_rotation_priority(key, age_days)
            })
        
        # Sort by priority (highest first)
        rotation_candidates.sort(key=lambda x: x['rotation_priority'], reverse=True)
        
        return {
            "timestamp": datetime.utcnow(),
            "threshold_days": days_threshold,
            "candidates_count": len(rotation_candidates),
            "rotation_candidates": rotation_candidates,
            "summary": {
                "high_priority": len([c for c in rotation_candidates if c['rotation_priority'] >= 80]),
                "medium_priority": len([c for c in rotation_candidates if 50 <= c['rotation_priority'] < 80]),
                "low_priority": len([c for c in rotation_candidates if c['rotation_priority'] < 50])
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rotation candidates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve rotation candidates"
        )


@router.get("/key-health/security-alerts", response_model=Dict[str, Any])
async def get_security_alerts(
    hours_back: int = Query(24, ge=1, le=168, description="Hours to look back for alerts"),
    severity_filter: Optional[str] = Query(None, description="Filter by severity (info, warning, error, critical)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get recent security alerts and events
    """
    try:
        # Check if user is admin
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        alerts_cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        
        # Build query
        alerts_query = select(MeilisearchSecurityEvent).where(
            MeilisearchSecurityEvent.created_at >= alerts_cutoff
        )
        
        if severity_filter:
            alerts_query = alerts_query.where(
                MeilisearchSecurityEvent.severity == severity_filter
            )
        
        alerts_query = alerts_query.order_by(desc(MeilisearchSecurityEvent.created_at))
        
        alerts_result = await db.execute(alerts_query)
        alerts = alerts_result.scalars().all()
        
        # Group alerts by type and severity
        alert_summary = {}
        for alert in alerts:
            key = f"{alert.event_type}_{alert.severity}"
            if key not in alert_summary:
                alert_summary[key] = {
                    "event_type": alert.event_type,
                    "severity": alert.severity,
                    "count": 0,
                    "latest_occurrence": alert.created_at
                }
            alert_summary[key]["count"] += 1
            
            if alert.created_at > alert_summary[key]["latest_occurrence"]:
                alert_summary[key]["latest_occurrence"] = alert.created_at
        
        # Calculate alert trends
        alert_trends = _calculate_alert_trends(alerts, hours_back)
        
        return {
            "timestamp": datetime.utcnow(),
            "time_range_hours": hours_back,
            "severity_filter": severity_filter,
            "total_alerts": len(alerts),
            "alert_summary": list(alert_summary.values()),
            "alert_trends": alert_trends,
            "recent_alerts": [
                {
                    "id": alert.id,
                    "event_type": alert.event_type,
                    "severity": alert.severity,
                    "description": alert.description,
                    "created_at": alert.created_at,
                    "automated": alert.automated,
                    "user_id": alert.user_id,
                    "metadata": alert.metadata
                }
                for alert in alerts[:50]  # Latest 50 alerts
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get security alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve security alerts"
        )


# Helper functions
def _calculate_system_health_score(
    meilisearch_status: str,
    keys_needing_rotation: int,
    projects_without_keys: int,
    security_events: List
) -> int:
    """Calculate overall system health score (0-100)"""
    score = 100
    
    # Meilisearch health
    if meilisearch_status != "healthy":
        score -= 30
    
    # Key rotation health
    if keys_needing_rotation > 0:
        score -= min(20, keys_needing_rotation * 2)
    
    # Project coverage
    if projects_without_keys > 0:
        score -= min(15, projects_without_keys * 3)
    
    # Security events
    critical_events = len([e for e in security_events if e.severity == "critical"])
    warning_events = len([e for e in security_events if e.severity == "warning"])
    
    score -= critical_events * 10
    score -= warning_events * 2
    
    return max(0, score)


def _calculate_project_health_score(
    project: Project,
    keys: List[MeilisearchKey],
    security_events: List[MeilisearchSecurityEvent]
) -> int:
    """Calculate project-specific health score"""
    score = 100
    
    # Check if project has active keys
    active_keys = [k for k in keys if k.is_active]
    if not active_keys:
        score -= 50
    
    # Check key age
    rotation_threshold = timedelta(days=settings.MEILISEARCH_KEY_ROTATION_DAYS)
    old_keys = [k for k in active_keys if datetime.utcnow() - k.created_at > rotation_threshold]
    score -= len(old_keys) * 10
    
    # Check security events
    recent_events = [e for e in security_events if e.created_at > datetime.utcnow() - timedelta(days=7)]
    critical_events = [e for e in recent_events if e.severity == "critical"]
    warning_events = [e for e in recent_events if e.severity == "warning"]
    
    score -= len(critical_events) * 15
    score -= len(warning_events) * 5
    
    return max(0, score)


def _calculate_rotation_priority(key: MeilisearchKey, age_days: int) -> int:
    """Calculate rotation priority score (0-100)"""
    priority = 0
    
    # Age factor
    if age_days > 180:
        priority += 50
    elif age_days > 90:
        priority += 30
    else:
        priority += 10
    
    # Usage factor
    if key.usage_count > 1000:
        priority += 20
    elif key.usage_count > 100:
        priority += 10
    
    # Last used factor
    if key.last_used_at:
        days_since_use = (datetime.utcnow() - key.last_used_at).days
        if days_since_use < 7:
            priority += 20  # Active keys get priority
    
    return min(100, priority)


def _get_project_recommendations(
    project: Project,
    keys: List[MeilisearchKey],
    security_events: List[MeilisearchSecurityEvent]
) -> List[str]:
    """Get recommendations for improving project security"""
    recommendations = []
    
    active_keys = [k for k in keys if k.is_active]
    if not active_keys:
        recommendations.append("Project missing active search keys - run migration script")
    
    rotation_threshold = timedelta(days=settings.MEILISEARCH_KEY_ROTATION_DAYS)
    old_keys = [k for k in active_keys if datetime.utcnow() - k.created_at > rotation_threshold]
    if old_keys:
        recommendations.append(f"Rotate {len(old_keys)} old key(s) for improved security")
    
    recent_critical_events = [
        e for e in security_events 
        if e.severity == "critical" and e.created_at > datetime.utcnow() - timedelta(days=7)
    ]
    if recent_critical_events:
        recommendations.append("Review recent critical security events and take action")
    
    if not recommendations:
        recommendations.append("Project key security is optimal")
    
    return recommendations


def _calculate_alert_trends(alerts: List[MeilisearchSecurityEvent], hours_back: int) -> Dict[str, Any]:
    """Calculate trends in security alerts"""
    if not alerts:
        return {"trend": "stable", "change_percentage": 0}
    
    # Split into first and second half of time period
    midpoint = datetime.utcnow() - timedelta(hours=hours_back // 2)
    
    recent_alerts = [a for a in alerts if a.created_at >= midpoint]
    older_alerts = [a for a in alerts if a.created_at < midpoint]
    
    recent_count = len(recent_alerts)
    older_count = len(older_alerts)
    
    if older_count == 0:
        trend = "new" if recent_count > 0 else "stable"
        change_percentage = 100 if recent_count > 0 else 0
    else:
        change_percentage = ((recent_count - older_count) / older_count) * 100
        
        if change_percentage > 20:
            trend = "increasing"
        elif change_percentage < -20:
            trend = "decreasing"
        else:
            trend = "stable"
    
    return {
        "trend": trend,
        "change_percentage": round(change_percentage, 1),
        "recent_period_count": recent_count,
        "previous_period_count": older_count
    }