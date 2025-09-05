"""
Dashboard endpoints - User-focused statistics for researchers
"""
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from datetime import datetime, timedelta
import logging

from app.api.deps import get_db, get_current_approved_user
from app.models.user import User
from app.models.project import Project, Domain, ScrapeSession
from app.models.shared_pages import PageV2, ProjectPage
from app.models.entities import ExtractedEntity
from app.models.library import StarredItem, SavedSearch

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/user-stats")
async def get_user_dashboard_stats(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Get user-specific dashboard statistics for researchers
    """
    try:
        # User's projects count
        projects_stmt = select(func.count(Project.id)).where(Project.owner_id == current_user.id)
        projects_result = await db.execute(projects_stmt)
        my_projects_count = projects_result.scalar() or 0

        # Total pages scraped by user (across all their projects)
        pages_stmt = select(func.count(ProjectPage.page_id)).join(
            Project, ProjectPage.project_id == Project.id
        ).where(Project.owner_id == current_user.id)
        pages_result = await db.execute(pages_stmt)
        total_pages_scraped = pages_result.scalar() or 0

        # Entities discovered in user's projects (directly from project_id since page_id is legacy)
        entities_stmt = select(func.count(ExtractedEntity.id.distinct())).join(
            Project, ExtractedEntity.project_id == Project.id
        ).where(Project.owner_id == current_user.id)
        entities_result = await db.execute(entities_stmt)
        entities_discovered = entities_result.scalar() or 0

        # Saved searches count
        saved_searches_stmt = select(func.count(SavedSearch.id)).where(
            SavedSearch.user_id == current_user.id
        )
        saved_searches_result = await db.execute(saved_searches_stmt)
        saved_searches_count = saved_searches_result.scalar() or 0

        # Library items (starred pages) count
        library_stmt = select(func.count(StarredItem.id)).where(
            StarredItem.user_id == current_user.id
        )
        library_result = await db.execute(library_stmt)
        library_items_count = library_result.scalar() or 0

        # Average content quality score (if available)
        quality_stmt = select(func.avg(PageV2.quality_score)).join(
            ProjectPage, ProjectPage.page_id == PageV2.id
        ).join(
            Project, ProjectPage.project_id == Project.id
        ).where(
            and_(
                Project.owner_id == current_user.id,
                PageV2.quality_score.is_not(None)
            )
        )
        quality_result = await db.execute(quality_stmt)
        avg_quality_score = quality_result.scalar() or 0.0

        return {
            "my_projects_count": my_projects_count,
            "total_pages_scraped": total_pages_scraped,
            "entities_discovered": entities_discovered,
            "saved_searches_count": saved_searches_count,
            "library_items_count": library_items_count,
            "average_content_quality": round(avg_quality_score, 2) if avg_quality_score else 0.0
        }

    except Exception as e:
        logger.error(f"Error getting user dashboard stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard statistics"
        )


@router.get("/recent-activity")
async def get_recent_activity(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    days: int = Query(default=7, ge=1, le=30, description="Number of days to look back")
) -> Dict[str, Any]:
    """
    Get user's recent activity for dashboard
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Recent scrapes completed
        recent_scrapes_stmt = select(
            PageV2.title,
            PageV2.url.label("original_url"),
            PageV2.capture_date.label("timestamp"),
            Project.name.label("project_name")
        ).join(
            ProjectPage, ProjectPage.page_id == PageV2.id
        ).join(
            Project, ProjectPage.project_id == Project.id
        ).where(
            and_(
                Project.owner_id == current_user.id,
                PageV2.capture_date >= cutoff_date
            )
        ).order_by(desc(PageV2.capture_date)).limit(10)
        
        recent_scrapes_result = await db.execute(recent_scrapes_stmt)
        recent_scrapes = [
            {
                "type": "scrape_completed",
                "title": row.title or "Untitled",
                "url": row.original_url,
                "project_name": row.project_name,
                "timestamp": row.timestamp
            }
            for row in recent_scrapes_result.fetchall()
        ]

        # Recent entities discovered (using direct project_id since page_id is legacy)
        recent_entities_stmt = select(
            ExtractedEntity.normalized_text,
            ExtractedEntity.entity_type,
            ExtractedEntity.extraction_confidence,
            ExtractedEntity.extracted_at.label("timestamp"),
            Project.name.label("project_name")
        ).join(
            Project, ExtractedEntity.project_id == Project.id
        ).where(
            and_(
                Project.owner_id == current_user.id,
                ExtractedEntity.extracted_at >= cutoff_date
            )
        ).order_by(desc(ExtractedEntity.extracted_at)).limit(10)
        
        recent_entities_result = await db.execute(recent_entities_stmt)
        recent_entities = [
            {
                "type": "entity_discovered",
                "entity_name": row.normalized_text,
                "entity_type": row.entity_type,
                "confidence": row.extraction_confidence,
                "project_name": row.project_name,
                "timestamp": row.timestamp
            }
            for row in recent_entities_result.fetchall()
        ]

        # Recent starred items - temporarily disabled until StarredItem system is updated for UUID PageV2
        # TODO: Update StarredItem to handle UUID-based PageV2 references
        recent_starred = []

        # Combine and sort all activities
        all_activities = recent_scrapes + recent_entities + recent_starred
        all_activities.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return {
            "recent_activity": all_activities[:15],  # Limit to 15 most recent
            "timeframe_days": days
        }

    except Exception as e:
        logger.error(f"Error getting recent activity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve recent activity"
        )


@router.get("/entity-insights")
async def get_entity_insights(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Get entity extraction insights for user's projects
    """
    try:
        # Top entities by frequency (using direct project_id)
        top_entities_stmt = select(
            ExtractedEntity.normalized_text,
            ExtractedEntity.entity_type,
            func.count(ExtractedEntity.id).label("frequency"),
            func.avg(ExtractedEntity.extraction_confidence).label("avg_confidence")
        ).join(
            Project, ExtractedEntity.project_id == Project.id
        ).where(
            Project.owner_id == current_user.id
        ).group_by(
            ExtractedEntity.normalized_text, ExtractedEntity.entity_type
        ).order_by(desc("frequency")).limit(10)
        
        top_entities_result = await db.execute(top_entities_stmt)
        top_entities = [
            {
                "name": row.normalized_text,
                "type": row.entity_type,
                "frequency": row.frequency,
                "avg_confidence": round(row.avg_confidence, 2)
            }
            for row in top_entities_result.fetchall()
        ]

        # Entity types distribution (using direct project_id)
        entity_types_stmt = select(
            ExtractedEntity.entity_type,
            func.count(ExtractedEntity.id).label("count")
        ).join(
            Project, ExtractedEntity.project_id == Project.id
        ).where(
            Project.owner_id == current_user.id
        ).group_by(ExtractedEntity.entity_type)
        
        entity_types_result = await db.execute(entity_types_stmt)
        entity_types_distribution = [
            {
                "type": row.entity_type,
                "count": row.count
            }
            for row in entity_types_result.fetchall()
        ]

        # Average confidence scores (using direct project_id)
        confidence_stmt = select(
            func.avg(ExtractedEntity.extraction_confidence).label("avg_confidence"),
            func.min(ExtractedEntity.extraction_confidence).label("min_confidence"),
            func.max(ExtractedEntity.extraction_confidence).label("max_confidence")
        ).join(
            Project, ExtractedEntity.project_id == Project.id
        ).where(
            Project.owner_id == current_user.id
        )
        
        confidence_result = await db.execute(confidence_stmt)
        confidence_stats = confidence_result.first()
        
        return {
            "top_entities": top_entities,
            "entity_types_distribution": entity_types_distribution,
            "confidence_stats": {
                "average": round(confidence_stats.avg_confidence, 2) if confidence_stats.avg_confidence else 0.0,
                "minimum": round(confidence_stats.min_confidence, 2) if confidence_stats.min_confidence else 0.0,
                "maximum": round(confidence_stats.max_confidence, 2) if confidence_stats.max_confidence else 0.0
            }
        }

    except Exception as e:
        logger.error(f"Error getting entity insights: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve entity insights"
        )


@router.get("/project-progress")
async def get_project_progress(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Get progress information for user's active projects and scraping jobs
    """
    try:
        # Active scraping sessions
        active_sessions_stmt = select(
            ScrapeSession.id,
            ScrapeSession.total_urls,
            ScrapeSession.completed_urls,
            ScrapeSession.failed_urls,
            ScrapeSession.status,
            ScrapeSession.started_at,
            Project.name.label("project_name")
        ).join(
            Project, ScrapeSession.project_id == Project.id
        ).where(
            and_(
                Project.owner_id == current_user.id,
                ScrapeSession.status.in_(["running", "queued", "paused"])
            )
        ).order_by(desc(ScrapeSession.started_at))
        
        active_sessions_result = await db.execute(active_sessions_stmt)
        active_jobs = []
        
        for row in active_sessions_result.fetchall():
            progress = 0
            if row.total_urls and row.total_urls > 0:
                progress = int((row.completed_urls / row.total_urls) * 100)
            
            active_jobs.append({
                "id": row.id,
                "name": f"{row.project_name} Scraping",
                "progress": progress,
                "status": row.status,
                "completed": row.completed_urls,
                "total": row.total_urls,
                "failed": row.failed_urls,
                "started_at": row.started_at
            })

        # Project statistics
        projects_stmt = select(
            Project.id,
            Project.name,
            Project.status,
            func.count(ProjectPage.page_id).label("pages_count")
        ).outerjoin(
            ProjectPage, ProjectPage.project_id == Project.id
        ).where(
            Project.owner_id == current_user.id
        ).group_by(Project.id, Project.name, Project.status)
        
        projects_result = await db.execute(projects_stmt)
        project_stats = [
            {
                "id": row.id,
                "name": row.name,
                "status": row.status,
                "pages_count": row.pages_count
            }
            for row in projects_result.fetchall()
        ]

        return {
            "active_jobs": active_jobs,
            "project_stats": project_stats,
            "summary": {
                "total_active_jobs": len(active_jobs),
                "total_projects": len(project_stats),
                "active_projects": len([p for p in project_stats if p["status"] == "active"])
            }
        }

    except Exception as e:
        logger.error(f"Error getting project progress: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve project progress"
        )


@router.get("/stats")
async def get_dashboard_stats(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user)
) -> Dict[str, Any]:
    """
    Get comprehensive dashboard statistics (alias for user-stats)
    """
    # Redirect to user-stats for compatibility
    return await get_user_dashboard_stats(db=db, current_user=current_user)


@router.get("/content-timeline")
async def get_content_timeline(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_approved_user),
    days: int = Query(default=30, ge=7, le=365, description="Number of days for timeline")
) -> Dict[str, Any]:
    """
    Get content discovery timeline and trends
    """
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Daily content extraction counts
        daily_counts_stmt = select(
            func.date(PageV2.capture_date).label("date"),
            func.count(PageV2.id).label("count")
        ).join(
            ProjectPage, ProjectPage.page_id == PageV2.id
        ).join(
            Project, ProjectPage.project_id == Project.id
        ).where(
            and_(
                Project.owner_id == current_user.id,
                PageV2.capture_date >= cutoff_date
            )
        ).group_by(func.date(PageV2.capture_date)).order_by("date")
        
        daily_counts_result = await db.execute(daily_counts_stmt)
        daily_timeline = [
            {
                "date": str(row.date),
                "count": row.count
            }
            for row in daily_counts_result.fetchall()
        ]

        # Most productive domains
        domains_stmt = select(
            func.substring(PageV2.url, r'https?://(?:www\.)?([^/]+)').label("domain"),
            func.count(PageV2.id).label("pages_count"),
            func.avg(PageV2.quality_score).label("avg_quality")
        ).join(
            ProjectPage, ProjectPage.page_id == PageV2.id
        ).join(
            Project, ProjectPage.project_id == Project.id
        ).where(
            and_(
                Project.owner_id == current_user.id,
                PageV2.capture_date >= cutoff_date
            )
        ).group_by("domain").order_by(desc("pages_count")).limit(10)
        
        domains_result = await db.execute(domains_stmt)
        productive_domains = [
            {
                "domain": row.domain or "Unknown",
                "pages_count": row.pages_count,
                "avg_quality": round(row.avg_quality, 2) if row.avg_quality else 0.0
            }
            for row in domains_result.fetchall()
        ]

        return {
            "daily_timeline": daily_timeline,
            "productive_domains": productive_domains,
            "timeframe_days": days
        }

    except Exception as e:
        logger.error(f"Error getting content timeline: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve content timeline"
        )