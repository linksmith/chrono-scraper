"""
Monitoring and statistics services
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlmodel import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, Domain, Page, ScrapeSession, ProjectStatus, DomainStatus
from app.models.user import User
from app.services.meilisearch_service import MeilisearchService


class MonitoringService:
    """Service for system monitoring and statistics"""
    
    @staticmethod
    async def get_system_overview(db: AsyncSession) -> Dict[str, Any]:
        """Get system-wide overview statistics"""
        
        # Total counts
        total_users = await db.execute(select(func.count(User.id)))
        total_projects = await db.execute(select(func.count(Project.id)))
        total_domains = await db.execute(select(func.count(Domain.id)))
        total_pages = await db.execute(select(func.count(Page.id)))
        
        # Active counts
        active_users = await db.execute(
            select(func.count(User.id)).where(
                and_(User.is_active == True, User.approval_status == "approved")
            )
        )
        
        active_projects = await db.execute(
            select(func.count(Project.id)).where(
                Project.status.in_([ProjectStatus.INDEXED, ProjectStatus.INDEXING])
            )
        )
        
        # Recent activity (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        new_users_week = await db.execute(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )
        
        new_projects_week = await db.execute(
            select(func.count(Project.id)).where(Project.created_at >= week_ago)
        )
        
        pages_scraped_week = await db.execute(
            select(func.count(Page.id)).where(Page.scraped_at >= week_ago)
        )
        
        return {
            "totals": {
                "users": total_users.scalar() or 0,
                "projects": total_projects.scalar() or 0,
                "domains": total_domains.scalar() or 0,
                "pages": total_pages.scalar() or 0
            },
            "active": {
                "users": active_users.scalar() or 0,
                "projects": active_projects.scalar() or 0
            },
            "recent_activity": {
                "new_users_this_week": new_users_week.scalar() or 0,
                "new_projects_this_week": new_projects_week.scalar() or 0,
                "pages_scraped_this_week": pages_scraped_week.scalar() or 0
            },
            "generated_at": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    async def get_user_dashboard_stats(db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """Get dashboard statistics for a specific user"""
        
        # User's projects
        user_projects = await db.execute(
            select(func.count(Project.id)).where(Project.user_id == user_id)
        )
        
        # Total domains across user's projects
        user_domains = await db.execute(
            select(func.count(Domain.id))
            .join(Project)
            .where(Project.user_id == user_id)
        )
        
        # Total pages scraped for user
        user_pages = await db.execute(
            select(func.count(Page.id))
            .join(Domain)
            .join(Project)
            .where(Project.user_id == user_id)
        )
        
        # Recent scraping activity (last 30 days)
        month_ago = datetime.utcnow() - timedelta(days=30)
        
        recent_pages = await db.execute(
            select(func.count(Page.id))
            .join(Domain)
            .join(Project)
            .where(
                and_(
                    Project.user_id == user_id,
                    Page.scraped_at >= month_ago
                )
            )
        )
        
        # Project status breakdown
        project_status_stats = await db.execute(
            select(Project.status, func.count(Project.id))
            .where(Project.user_id == user_id)
            .group_by(Project.status)
        )
        
        status_breakdown = {}
        for status, count in project_status_stats:
            status_breakdown[status] = count
        
        # Recent projects
        recent_projects_result = await db.execute(
            select(Project.id, Project.name, Project.created_at, Project.status)
            .where(Project.user_id == user_id)
            .order_by(Project.created_at.desc())
            .limit(5)
        )
        
        recent_projects = []
        for project_id, name, created_at, status in recent_projects_result:
            recent_projects.append({
                "id": project_id,
                "name": name,
                "created_at": created_at.isoformat(),
                "status": status
            })
        
        return {
            "totals": {
                "projects": user_projects.scalar() or 0,
                "domains": user_domains.scalar() or 0,
                "pages": user_pages.scalar() or 0
            },
            "recent_activity": {
                "pages_scraped_last_month": recent_pages.scalar() or 0
            },
            "project_status_breakdown": status_breakdown,
            "recent_projects": recent_projects,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    async def get_project_analytics(
        db: AsyncSession, 
        project_id: int, 
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get detailed analytics for a project"""
        
        # Verify project access
        query = select(Project).where(Project.id == project_id)
        if user_id:
            query = query.where(Project.user_id == user_id)
        
        project_result = await db.execute(query)
        project = project_result.scalar_one_or_none()
        
        if not project:
            return {}
        
        # Domain statistics
        domain_stats = await db.execute(
            select(
                func.count(Domain.id).label("total_domains"),
                func.sum(Domain.total_pages).label("total_pages"),
                func.sum(Domain.scraped_pages).label("scraped_pages"),
                func.sum(Domain.failed_pages).label("failed_pages")
            )
            .where(Domain.project_id == project_id)
        )
        
        domain_row = domain_stats.first()
        
        # Pages by status
        page_status_stats = await db.execute(
            select(Page.processed, func.count(Page.id))
            .join(Domain)
            .where(Domain.project_id == project_id)
            .group_by(Page.processed)
        )
        
        processed_breakdown = {}
        for processed, count in page_status_stats:
            status = "processed" if processed else "unprocessed"
            processed_breakdown[status] = count
        
        # Scraping timeline (last 30 days)
        month_ago = datetime.utcnow() - timedelta(days=30)
        
        daily_stats = await db.execute(
            select(
                func.date(Page.scraped_at).label("date"),
                func.count(Page.id).label("pages_count")
            )
            .join(Domain)
            .where(
                and_(
                    Domain.project_id == project_id,
                    Page.scraped_at >= month_ago
                )
            )
            .group_by(func.date(Page.scraped_at))
            .order_by(func.date(Page.scraped_at))
        )
        
        timeline = []
        for date, count in daily_stats:
            timeline.append({
                "date": date.isoformat() if date else None,
                "pages_scraped": count
            })
        
        # Domain performance
        domain_performance = await db.execute(
            select(
                Domain.id,
                Domain.domain_name,
                Domain.status,
                Domain.total_pages,
                Domain.scraped_pages,
                Domain.failed_pages,
                Domain.last_scraped
            )
            .where(Domain.project_id == project_id)
            .order_by(Domain.scraped_pages.desc())
        )
        
        domains = []
        for row in domain_performance:
            domains.append({
                "id": row.id,
                "domain_name": row.domain_name,
                "status": row.status,
                "total_pages": row.total_pages,
                "scraped_pages": row.scraped_pages,
                "failed_pages": row.failed_pages,
                "last_scraped": row.last_scraped.isoformat() if row.last_scraped else None,
                "success_rate": (row.scraped_pages / row.total_pages * 100) if row.total_pages > 0 else 0
            })
        
        # Meilisearch index stats
        index_stats = await MeilisearchService.get_index_stats(project)
        
        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "status": project.status
            },
            "summary": {
                "total_domains": domain_row.total_domains or 0,
                "total_pages": int(domain_row.total_pages or 0),
                "scraped_pages": int(domain_row.scraped_pages or 0),
                "failed_pages": int(domain_row.failed_pages or 0),
                "success_rate": (domain_row.scraped_pages / domain_row.total_pages * 100) if domain_row.total_pages and domain_row.total_pages > 0 else 0
            },
            "processing_breakdown": processed_breakdown,
            "scraping_timeline": timeline,
            "domain_performance": domains,
            "index_stats": index_stats,
            "generated_at": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    async def get_system_health(db: AsyncSession) -> Dict[str, Any]:
        """Get system health status"""
        
        health_status = {
            "overall": "healthy",
            "services": {},
            "issues": [],
            "checked_at": datetime.utcnow().isoformat()
        }
        
        # Database health
        try:
            await db.execute(select(1))
            health_status["services"]["database"] = "healthy"
        except Exception as e:
            health_status["services"]["database"] = "unhealthy"
            health_status["issues"].append(f"Database error: {str(e)}")
            health_status["overall"] = "unhealthy"
        
        # Meilisearch health
        try:
            meilisearch_health = await MeilisearchService.health_check()
            health_status["services"]["meilisearch"] = meilisearch_health["status"]
            
            if meilisearch_health["status"] != "healthy":
                health_status["issues"].append("Meilisearch is unhealthy")
                health_status["overall"] = "degraded"
                
        except Exception as e:
            health_status["services"]["meilisearch"] = "unhealthy"
            health_status["issues"].append(f"Meilisearch error: {str(e)}")
            health_status["overall"] = "unhealthy"
        
        # Check for failed projects
        failed_projects = await db.execute(
            select(func.count(Project.id)).where(Project.status == ProjectStatus.ERROR)
        )
        
        failed_count = failed_projects.scalar() or 0
        if failed_count > 0:
            health_status["issues"].append(f"{failed_count} projects in error state")
            if health_status["overall"] == "healthy":
                health_status["overall"] = "degraded"
        
        # Check for old unprocessed pages
        week_ago = datetime.utcnow() - timedelta(days=7)
        old_unprocessed = await db.execute(
            select(func.count(Page.id)).where(
                and_(
                    Page.processed == False,
                    Page.scraped_at < week_ago
                )
            )
        )
        
        old_count = old_unprocessed.scalar() or 0
        if old_count > 100:  # Threshold for concern
            health_status["issues"].append(f"{old_count} old unprocessed pages")
            if health_status["overall"] == "healthy":
                health_status["overall"] = "degraded"
        
        return health_status
    
    @staticmethod
    async def get_usage_trends(
        db: AsyncSession, 
        days: int = 30
    ) -> Dict[str, Any]:
        """Get usage trends over specified period"""
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Daily user registrations
        user_registrations = await db.execute(
            select(
                func.date(User.created_at).label("date"),
                func.count(User.id).label("count")
            )
            .where(User.created_at >= start_date)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
        
        # Daily project creations
        project_creations = await db.execute(
            select(
                func.date(Project.created_at).label("date"),
                func.count(Project.id).label("count")
            )
            .where(Project.created_at >= start_date)
            .group_by(func.date(Project.created_at))
            .order_by(func.date(Project.created_at))
        )
        
        # Daily pages scraped
        pages_scraped = await db.execute(
            select(
                func.date(Page.scraped_at).label("date"),
                func.count(Page.id).label("count")
            )
            .where(Page.scraped_at >= start_date)
            .group_by(func.date(Page.scraped_at))
            .order_by(func.date(Page.scraped_at))
        )
        
        # Convert to lists
        trends = {
            "period_days": days,
            "start_date": start_date.isoformat(),
            "end_date": datetime.utcnow().isoformat(),
            "user_registrations": [
                {"date": row.date.isoformat(), "count": row.count}
                for row in user_registrations
            ],
            "project_creations": [
                {"date": row.date.isoformat(), "count": row.count}
                for row in project_creations
            ],
            "pages_scraped": [
                {"date": row.date.isoformat(), "count": row.count}
                for row in pages_scraped
            ]
        }
        
        return trends