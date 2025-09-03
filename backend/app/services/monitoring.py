"""
Monitoring and statistics services with shared pages architecture support
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlmodel import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import time
import redis.asyncio as redis
import psutil
import subprocess
import json
import httpx
from celery import current_app
from celery.app.control import Inspect

from app.models.project import Project, Domain, Page, ScrapeSession, ProjectStatus
from app.models.shared_pages import PageV2, ProjectPage, CDXPageRegistry, ScrapeStatus
from app.models.user import User
from app.services.meilisearch_service import MeilisearchService
from app.core.config import settings

logger = logging.getLogger(__name__)


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
                and_(User.is_active is True, User.approval_status == "approved")
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
                    Page.processed is False,
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

    @staticmethod
    async def get_shared_pages_metrics(db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive shared pages architecture metrics"""
        
        # Core shared pages statistics
        total_pages_v2 = await db.execute(select(func.count(PageV2.id)))
        total_project_pages = await db.execute(select(func.count(ProjectPage.id)))
        total_cdx_registry = await db.execute(select(func.count(CDXPageRegistry.id)))
        
        # Processing status breakdown
        processed_pages = await db.execute(
            select(func.count(PageV2.id)).where(PageV2.processed is True)
        )
        
        indexed_pages = await db.execute(
            select(func.count(PageV2.id)).where(PageV2.indexed is True)
        )
        
        failed_pages = await db.execute(
            select(func.count(PageV2.id)).where(PageV2.error_message.isnot(None))
        )
        
        # CDX deduplication efficiency
        cdx_with_pages = await db.execute(
            select(func.count(CDXPageRegistry.id)).where(CDXPageRegistry.page_id.isnot(None))
        )
        
        cdx_total = total_cdx_registry.scalar() or 0
        cdx_linked = cdx_with_pages.scalar() or 0
        deduplication_rate = (cdx_linked / cdx_total * 100) if cdx_total > 0 else 0
        
        # Cross-project sharing statistics
        sharing_stats = await db.execute(
            text("""
                SELECT 
                    COUNT(DISTINCT pp.page_id) as unique_pages_shared,
                    COUNT(pp.id) as total_associations,
                    ROUND(AVG(project_count), 2) as avg_projects_per_page
                FROM project_pages pp
                JOIN (
                    SELECT page_id, COUNT(DISTINCT project_id) as project_count
                    FROM project_pages
                    GROUP BY page_id
                ) page_projects ON pp.page_id = page_projects.page_id
            """)
        )
        
        sharing_result = sharing_stats.first()
        unique_pages_shared = sharing_result.unique_pages_shared if sharing_result else 0
        total_associations = sharing_result.total_associations if sharing_result else 0
        avg_projects_per_page = float(sharing_result.avg_projects_per_page) if sharing_result and sharing_result.avg_projects_per_page else 0
        
        # Calculate sharing efficiency
        sharing_efficiency = 0
        if total_associations > 0 and unique_pages_shared > 0:
            sharing_efficiency = ((total_associations - unique_pages_shared) / total_associations * 100)
        
        # Recent activity (last 24 hours)
        day_ago = datetime.utcnow() - timedelta(days=1)
        
        recent_pages_created = await db.execute(
            select(func.count(PageV2.id)).where(PageV2.created_at >= day_ago)
        )
        
        recent_associations = await db.execute(
            select(func.count(ProjectPage.id)).where(ProjectPage.added_at >= day_ago)
        )
        
        recent_cdx_entries = await db.execute(
            select(func.count(CDXPageRegistry.id)).where(CDXPageRegistry.first_seen_at >= day_ago)
        )
        
        # Performance metrics
        avg_processing_time = await db.execute(
            text("""
                SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_seconds
                FROM pages_v2 
                WHERE processed = true 
                AND created_at >= NOW() - INTERVAL '7 days'
            """)
        )
        
        avg_processing_seconds = avg_processing_time.scalar() or 0
        
        return {
            "core_metrics": {
                "total_shared_pages": total_pages_v2.scalar() or 0,
                "total_project_associations": total_project_pages.scalar() or 0,
                "total_cdx_entries": cdx_total,
                "processed_pages": processed_pages.scalar() or 0,
                "indexed_pages": indexed_pages.scalar() or 0,
                "failed_pages": failed_pages.scalar() or 0
            },
            "deduplication_metrics": {
                "cdx_entries_with_pages": cdx_linked,
                "deduplication_rate_percent": round(deduplication_rate, 2),
                "deduplication_efficiency": "high" if deduplication_rate >= 70 else "medium" if deduplication_rate >= 50 else "low"
            },
            "sharing_metrics": {
                "unique_pages_shared": unique_pages_shared,
                "total_associations": total_associations,
                "avg_projects_per_page": avg_projects_per_page,
                "sharing_efficiency_percent": round(sharing_efficiency, 2),
                "api_call_reduction_estimate": round(sharing_efficiency * 0.7, 2)  # Estimated 70% of sharing translates to API savings
            },
            "recent_activity": {
                "pages_created_24h": recent_pages_created.scalar() or 0,
                "associations_created_24h": recent_associations.scalar() or 0,
                "cdx_entries_24h": recent_cdx_entries.scalar() or 0
            },
            "performance_metrics": {
                "avg_processing_time_seconds": round(avg_processing_seconds, 2),
                "processing_status": "fast" if avg_processing_seconds < 30 else "normal" if avg_processing_seconds < 120 else "slow"
            },
            "generated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    async def get_shared_pages_health_check(db: AsyncSession) -> Dict[str, Any]:
        """Comprehensive health check for shared pages architecture"""
        
        health_status = {
            "overall": "healthy",
            "components": {},
            "metrics": {},
            "issues": [],
            "warnings": [],
            "checked_at": datetime.utcnow().isoformat()
        }
        
        try:
            # Database table health checks
            tables_health = await MonitoringService._check_shared_pages_tables_health(db)
            health_status["components"]["database_tables"] = tables_health
            
            # CDX deduplication health
            dedup_health = await MonitoringService._check_cdx_deduplication_health(db)
            health_status["components"]["cdx_deduplication"] = dedup_health
            
            # Processing pipeline health
            processing_health = await MonitoringService._check_processing_pipeline_health(db)
            health_status["components"]["processing_pipeline"] = processing_health
            
            # Search integration health
            search_health = await MonitoringService._check_search_integration_health(db)
            health_status["components"]["search_integration"] = search_health
            
            # Performance thresholds check
            performance_health = await MonitoringService._check_performance_thresholds(db)
            health_status["components"]["performance"] = performance_health
            
            # Aggregate health status
            component_statuses = [comp["status"] for comp in health_status["components"].values()]
            
            if "critical" in component_statuses:
                health_status["overall"] = "critical"
            elif "unhealthy" in component_statuses:
                health_status["overall"] = "unhealthy"
            elif "degraded" in component_statuses:
                health_status["overall"] = "degraded"
            
            # Collect all issues and warnings
            for component in health_status["components"].values():
                health_status["issues"].extend(component.get("issues", []))
                health_status["warnings"].extend(component.get("warnings", []))
                
        except Exception as e:
            logger.error(f"Shared pages health check failed: {str(e)}")
            health_status["overall"] = "critical"
            health_status["issues"].append(f"Health check system error: {str(e)}")
        
        return health_status

    @staticmethod
    async def _check_shared_pages_tables_health(db: AsyncSession) -> Dict[str, Any]:
        """Check health of shared pages database tables"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": []
        }
        
        try:
            # Check table accessibility and basic counts
            pages_v2_count = await db.execute(select(func.count(PageV2.id)))
            project_pages_count = await db.execute(select(func.count(ProjectPage.id)))
            cdx_registry_count = await db.execute(select(func.count(CDXPageRegistry.id)))
            
            health["metrics"]["pages_v2_count"] = pages_v2_count.scalar() or 0
            health["metrics"]["project_pages_count"] = project_pages_count.scalar() or 0
            health["metrics"]["cdx_registry_count"] = cdx_registry_count.scalar() or 0
            
            # Check for constraint violations
            constraint_check = await db.execute(
                text("""
                    SELECT 
                        COUNT(*) as total_duplicates
                    FROM (
                        SELECT url, unix_timestamp, COUNT(*) as dup_count
                        FROM pages_v2 
                        GROUP BY url, unix_timestamp 
                        HAVING COUNT(*) > 1
                    ) duplicates
                """)
            )
            
            duplicate_count = constraint_check.scalar() or 0
            if duplicate_count > 0:
                health["issues"].append(f"Found {duplicate_count} duplicate URL/timestamp combinations in pages_v2")
                health["status"] = "degraded"
            
            # Check for orphaned records
            orphaned_project_pages = await db.execute(
                text("""
                    SELECT COUNT(*) 
                    FROM project_pages pp 
                    LEFT JOIN pages_v2 p ON pp.page_id = p.id 
                    WHERE p.id IS NULL
                """)
            )
            
            orphaned_count = orphaned_project_pages.scalar() or 0
            if orphaned_count > 0:
                health["warnings"].append(f"Found {orphaned_count} orphaned project_pages records")
                if health["status"] == "healthy":
                    health["status"] = "degraded"
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append(f"Database table check failed: {str(e)}")
        
        return health

    @staticmethod
    async def _check_cdx_deduplication_health(db: AsyncSession) -> Dict[str, Any]:
        """Check CDX deduplication system health"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": []
        }
        
        try:
            # Check deduplication efficiency
            total_cdx = await db.execute(select(func.count(CDXPageRegistry.id)))
            linked_cdx = await db.execute(
                select(func.count(CDXPageRegistry.id)).where(CDXPageRegistry.page_id.isnot(None))
            )
            
            total_count = total_cdx.scalar() or 0
            linked_count = linked_cdx.scalar() or 0
            
            if total_count > 0:
                dedup_rate = (linked_count / total_count) * 100
                health["metrics"]["deduplication_rate"] = round(dedup_rate, 2)
                
                # Check against target thresholds
                if dedup_rate < 50:
                    health["issues"].append(f"Deduplication rate {dedup_rate:.1f}% below critical threshold (50%)")
                    health["status"] = "critical"
                elif dedup_rate < 60:
                    health["warnings"].append(f"Deduplication rate {dedup_rate:.1f}% below target threshold (60%)")
                    health["status"] = "degraded"
            
            # Check for stale CDX entries
            week_ago = datetime.utcnow() - timedelta(days=7)
            stale_pending = await db.execute(
                select(func.count(CDXPageRegistry.id)).where(
                    and_(
                        CDXPageRegistry.scrape_status == ScrapeStatus.PENDING,
                        CDXPageRegistry.first_seen_at < week_ago
                    )
                )
            )
            
            stale_count = stale_pending.scalar() or 0
            if stale_count > 100:
                health["warnings"].append(f"Found {stale_count} stale pending CDX entries (>7 days old)")
                if health["status"] == "healthy":
                    health["status"] = "degraded"
            
            health["metrics"]["stale_pending_entries"] = stale_count
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append(f"CDX deduplication check failed: {str(e)}")
        
        return health

    @staticmethod
    async def _check_processing_pipeline_health(db: AsyncSession) -> Dict[str, Any]:
        """Check shared pages processing pipeline health"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": []
        }
        
        try:
            # Check processing backlog
            unprocessed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.processed is False)
            )
            
            unprocessed_count = unprocessed_pages.scalar() or 0
            health["metrics"]["unprocessed_pages"] = unprocessed_count
            
            if unprocessed_count > 1000:
                health["issues"].append(f"Large processing backlog: {unprocessed_count} unprocessed pages")
                health["status"] = "critical"
            elif unprocessed_count > 500:
                health["warnings"].append(f"Processing backlog growing: {unprocessed_count} unprocessed pages")
                health["status"] = "degraded"
            
            # Check for pages stuck in processing
            hour_ago = datetime.utcnow() - timedelta(hours=1)
            stuck_pages = await db.execute(
                select(func.count(PageV2.id)).where(
                    and_(
                        PageV2.processed is False,
                        PageV2.created_at < hour_ago,
                        PageV2.error_message.is_(None)
                    )
                )
            )
            
            stuck_count = stuck_pages.scalar() or 0
            health["metrics"]["stuck_processing_pages"] = stuck_count
            
            if stuck_count > 50:
                health["warnings"].append(f"Found {stuck_count} pages stuck in processing (>1 hour)")
                if health["status"] == "healthy":
                    health["status"] = "degraded"
            
            # Check error rate
            day_ago = datetime.utcnow() - timedelta(days=1)
            recent_errors = await db.execute(
                select(func.count(PageV2.id)).where(
                    and_(
                        PageV2.error_message.isnot(None),
                        PageV2.updated_at >= day_ago
                    )
                )
            )
            
            recent_total = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.updated_at >= day_ago)
            )
            
            error_count = recent_errors.scalar() or 0
            total_recent = recent_total.scalar() or 0
            
            if total_recent > 0:
                error_rate = (error_count / total_recent) * 100
                health["metrics"]["error_rate_24h"] = round(error_rate, 2)
                
                if error_rate > 20:
                    health["issues"].append(f"High error rate: {error_rate:.1f}% in last 24 hours")
                    health["status"] = "critical"
                elif error_rate > 10:
                    health["warnings"].append(f"Elevated error rate: {error_rate:.1f}% in last 24 hours")
                    if health["status"] == "healthy":
                        health["status"] = "degraded"
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append(f"Processing pipeline check failed: {str(e)}")
        
        return health

    @staticmethod
    async def _check_search_integration_health(db: AsyncSession) -> Dict[str, Any]:
        """Check search integration health for shared pages"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": []
        }
        
        try:
            # Check indexing status
            processed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.processed is True)
            )
            
            indexed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.indexed is True)
            )
            
            processed_count = processed_pages.scalar() or 0
            indexed_count = indexed_pages.scalar() or 0
            
            health["metrics"]["processed_pages"] = processed_count
            health["metrics"]["indexed_pages"] = indexed_count
            
            if processed_count > 0:
                indexing_rate = (indexed_count / processed_count) * 100
                health["metrics"]["indexing_rate"] = round(indexing_rate, 2)
                
                if indexing_rate < 80:
                    health["warnings"].append(f"Low indexing rate: {indexing_rate:.1f}% of processed pages indexed")
                    health["status"] = "degraded"
            
            # Check for indexing backlog
            indexing_backlog = processed_count - indexed_count
            health["metrics"]["indexing_backlog"] = indexing_backlog
            
            if indexing_backlog > 500:
                health["issues"].append(f"Large indexing backlog: {indexing_backlog} processed but unindexed pages")
                health["status"] = "critical"
            elif indexing_backlog > 200:
                health["warnings"].append(f"Indexing backlog growing: {indexing_backlog} processed but unindexed pages")
                if health["status"] == "healthy":
                    health["status"] = "degraded"
            
            # Test Meilisearch connectivity
            try:
                meilisearch_health = await MeilisearchService.health_check()
                health["metrics"]["meilisearch_status"] = meilisearch_health["status"]
                
                if meilisearch_health["status"] != "healthy":
                    health["issues"].append("Meilisearch service is unhealthy")
                    health["status"] = "critical"
                    
            except Exception as e:
                health["issues"].append(f"Meilisearch connectivity failed: {str(e)}")
                health["status"] = "critical"
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append(f"Search integration check failed: {str(e)}")
        
        return health

    @staticmethod
    async def _check_performance_thresholds(db: AsyncSession) -> Dict[str, Any]:
        """Check performance metrics against thresholds"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": []
        }
        
        try:
            # Check average processing time
            avg_processing_time = await db.execute(
                text("""
                    SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_seconds
                    FROM pages_v2 
                    WHERE processed = true 
                    AND created_at >= NOW() - INTERVAL '24 hours'
                """)
            )
            
            avg_seconds = avg_processing_time.scalar() or 0
            health["metrics"]["avg_processing_time_seconds"] = round(avg_seconds, 2)
            
            if avg_seconds > 300:  # 5 minutes
                health["issues"].append(f"Slow processing: average {avg_seconds:.1f}s per page")
                health["status"] = "critical"
            elif avg_seconds > 120:  # 2 minutes
                health["warnings"].append(f"Processing slower than optimal: average {avg_seconds:.1f}s per page")
                health["status"] = "degraded"
            
            # Check database query performance (simulate key queries)
            start_time = time.time()
            await db.execute(
                select(PageV2.id, PageV2.url, PageV2.unix_timestamp)
                .limit(100)
                .order_by(PageV2.created_at.desc())
            )
            query_time = time.time() - start_time
            
            health["metrics"]["sample_query_time_seconds"] = round(query_time, 3)
            
            if query_time > 5.0:
                health["issues"].append(f"Slow database queries: {query_time:.2f}s for sample query")
                health["status"] = "critical"
            elif query_time > 2.0:
                health["warnings"].append(f"Database queries slower than optimal: {query_time:.2f}s")
                if health["status"] == "healthy":
                    health["status"] = "degraded"
            
            # Check Redis connectivity if available
            try:
                redis_start = time.time()
                # Create Redis client and test connectivity
                redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=6379,
                    db=2,
                    decode_responses=True,
                    socket_timeout=5.0
                )
                # Test with a simple ping
                await redis_client.ping()
                await redis_client.close()
                redis_time = time.time() - redis_start
                health["metrics"]["redis_response_time_seconds"] = round(redis_time, 3)
                
                if redis_time > 1.0:
                    health["warnings"].append(f"Slow Redis response: {redis_time:.2f}s")
                    if health["status"] == "healthy":
                        health["status"] = "degraded"
                        
            except Exception as e:
                health["warnings"].append(f"Redis connectivity test failed: {str(e)}")
                if health["status"] == "healthy":
                    health["status"] = "degraded"
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append(f"Performance threshold check failed: {str(e)}")
        
        return health

    @staticmethod
    async def get_shared_pages_business_metrics(db: AsyncSession, days: int = 30) -> Dict[str, Any]:
        """Get business metrics for shared pages architecture adoption and efficiency"""
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Calculate API call reduction from page sharing
        sharing_impact = await db.execute(
            text("""
                SELECT 
                    COUNT(DISTINCT pp.page_id) as unique_pages,
                    COUNT(pp.id) as total_associations,
                    COUNT(pp.id) - COUNT(DISTINCT pp.page_id) as api_calls_saved
                FROM project_pages pp
                JOIN pages_v2 p ON pp.page_id = p.id
                WHERE pp.added_at >= :start_date
            """),
            {"start_date": start_date}
        )
        
        impact_result = sharing_impact.first()
        unique_pages = impact_result.unique_pages if impact_result else 0
        total_associations = impact_result.total_associations if impact_result else 0
        api_calls_saved = impact_result.api_calls_saved if impact_result else 0
        
        # Calculate storage efficiency
        storage_efficiency = await db.execute(
            text("""
                SELECT 
                    SUM(CASE WHEN p.content IS NOT NULL THEN LENGTH(p.content) ELSE 0 END) as total_content_bytes,
                    COUNT(pp.id) as total_references,
                    AVG(LENGTH(p.content)) as avg_content_size
                FROM pages_v2 p
                JOIN project_pages pp ON p.id = pp.page_id
                WHERE pp.added_at >= :start_date
                AND p.content IS NOT NULL
            """),
            {"start_date": start_date}
        )
        
        storage_result = storage_efficiency.first()
        total_content_bytes = storage_result.total_content_bytes if storage_result else 0
        total_references = storage_result.total_references if storage_result else 0
        avg_content_size = storage_result.avg_content_size if storage_result else 0
        
        # Estimate storage savings
        estimated_duplicate_storage = 0
        if unique_pages > 0 and total_references > unique_pages:
            duplicate_references = total_references - unique_pages
            estimated_duplicate_storage = duplicate_references * (avg_content_size or 0)
        
        # User adoption metrics
        adoption_metrics = await db.execute(
            text("""
                SELECT 
                    COUNT(DISTINCT pr.user_id) as users_with_shared_pages,
                    COUNT(DISTINCT pp.project_id) as projects_using_sharing
                FROM project_pages pp
                JOIN projects pr ON pp.project_id = pr.id
                WHERE pp.added_at >= :start_date
            """),
            {"start_date": start_date}
        )
        
        adoption_result = adoption_metrics.first()
        users_with_shared_pages = adoption_result.users_with_shared_pages if adoption_result else 0
        projects_using_sharing = adoption_result.projects_using_sharing if adoption_result else 0
        
        # Performance improvement metrics
        performance_metrics = await db.execute(
            text("""
                SELECT 
                    AVG(EXTRACT(EPOCH FROM (p.updated_at - p.created_at))) as avg_processing_time,
                    COUNT(*) as total_processed
                FROM pages_v2 p
                WHERE p.processed = true
                AND p.created_at >= :start_date
            """),
            {"start_date": start_date}
        )
        
        perf_result = performance_metrics.first()
        avg_processing_time = perf_result.avg_processing_time if perf_result else 0
        total_processed = perf_result.total_processed if perf_result else 0
        
        return {
            "period_days": days,
            "start_date": start_date.isoformat(),
            "api_efficiency": {
                "unique_pages_created": unique_pages,
                "total_page_associations": total_associations,
                "api_calls_saved": api_calls_saved,
                "api_reduction_percentage": round((api_calls_saved / total_associations * 100) if total_associations > 0 else 0, 2),
                "estimated_wayback_calls_saved": api_calls_saved * 5000  # Assuming 5000 calls per scraping session
            },
            "storage_efficiency": {
                "total_content_stored_bytes": int(total_content_bytes),
                "total_content_stored_mb": round(total_content_bytes / (1024 * 1024), 2),
                "estimated_duplicate_storage_avoided_bytes": int(estimated_duplicate_storage),
                "estimated_duplicate_storage_avoided_mb": round(estimated_duplicate_storage / (1024 * 1024), 2),
                "storage_efficiency_percentage": round((estimated_duplicate_storage / (total_content_bytes + estimated_duplicate_storage) * 100) if (total_content_bytes + estimated_duplicate_storage) > 0 else 0, 2)
            },
            "adoption_metrics": {
                "users_utilizing_shared_pages": users_with_shared_pages,
                "projects_using_sharing": projects_using_sharing,
                "avg_associations_per_project": round(total_associations / projects_using_sharing, 2) if projects_using_sharing > 0 else 0
            },
            "performance_metrics": {
                "avg_processing_time_seconds": round(avg_processing_time, 2),
                "total_pages_processed": total_processed,
                "processing_throughput_per_day": round(total_processed / days, 2) if days > 0 else 0
            },
            "generated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    async def get_comprehensive_system_health() -> Dict[str, Any]:
        """Get comprehensive system health including all services and infrastructure"""
        
        health_status = {
            "overall": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {},
            "infrastructure": {},
            "performance": {},
            "issues": [],
            "warnings": []
        }
        
        # Database health with performance metrics
        db_health = await MonitoringService._check_database_health()
        health_status["services"]["database"] = db_health
        
        # Redis health and memory usage
        redis_health = await MonitoringService._check_redis_health()
        health_status["services"]["redis"] = redis_health
        
        # Meilisearch health and indexing status
        meilisearch_health = await MonitoringService._check_meilisearch_health()
        health_status["services"]["meilisearch"] = meilisearch_health
        
        # Firecrawl API and worker status
        firecrawl_health = await MonitoringService._check_firecrawl_health()
        health_status["services"]["firecrawl"] = firecrawl_health
        
        # System metrics (CPU, memory, disk, network)
        system_metrics = await MonitoringService._get_system_metrics()
        health_status["infrastructure"]["system"] = system_metrics
        
        # Docker container metrics
        docker_metrics = await MonitoringService._get_docker_metrics()
        health_status["infrastructure"]["containers"] = docker_metrics
        
        # Performance metrics
        performance_metrics = await MonitoringService._get_performance_metrics()
        health_status["performance"] = performance_metrics
        
        # Aggregate health status
        all_services = list(health_status["services"].values())
        if any(s.get("status") == "critical" for s in all_services):
            health_status["overall"] = "critical"
        elif any(s.get("status") == "unhealthy" for s in all_services):
            health_status["overall"] = "unhealthy"
        elif any(s.get("status") == "degraded" for s in all_services):
            health_status["overall"] = "degraded"
        
        # Collect all issues and warnings
        for category in ["services", "infrastructure", "performance"]:
            for component in health_status[category].values():
                if isinstance(component, dict):
                    health_status["issues"].extend(component.get("issues", []))
                    health_status["warnings"].extend(component.get("warnings", []))
        
        return health_status
    
    @staticmethod
    async def _check_database_health() -> Dict[str, Any]:
        """Check PostgreSQL health and performance"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": [],
            "response_time_ms": 0
        }
        
        try:
            # Import here to avoid circular imports
            from app.core.database import get_db
            
            start_time = time.time()
            async for db in get_db():
                # Test basic connectivity
                await db.execute(select(1))
                
                # Check connection pool status
                pool_info = await db.execute(
                    text("SELECT COUNT(*) as active_connections FROM pg_stat_activity WHERE state = 'active'")
                )
                active_connections = pool_info.scalar() or 0
                
                # Check database size
                db_size = await db.execute(
                    text("SELECT pg_size_pretty(pg_database_size(current_database())) as size")
                )
                database_size = db_size.scalar() or "Unknown"
                
                # Check for long-running queries
                long_queries = await db.execute(
                    text("""
                        SELECT COUNT(*) as count
                        FROM pg_stat_activity 
                        WHERE state = 'active' 
                        AND query_start < NOW() - INTERVAL '5 minutes'
                        AND query NOT LIKE '%pg_stat_activity%'
                    """)
                )
                long_query_count = long_queries.scalar() or 0
                
                response_time = (time.time() - start_time) * 1000
                health["response_time_ms"] = round(response_time, 2)
                
                health["metrics"].update({
                    "active_connections": active_connections,
                    "database_size": database_size,
                    "long_running_queries": long_query_count,
                    "response_time_ms": health["response_time_ms"]
                })
                
                # Health checks
                if active_connections > 50:
                    health["warnings"].append(f"High connection count: {active_connections}")
                    health["status"] = "degraded"
                
                if long_query_count > 0:
                    health["warnings"].append(f"Long-running queries detected: {long_query_count}")
                    if health["status"] == "healthy":
                        health["status"] = "degraded"
                
                if response_time > 1000:  # 1 second
                    health["issues"].append(f"Slow database response: {response_time:.0f}ms")
                    health["status"] = "critical"
                elif response_time > 500:  # 500ms
                    health["warnings"].append(f"Elevated database response time: {response_time:.0f}ms")
                    if health["status"] == "healthy":
                        health["status"] = "degraded"
                
                break
                
        except Exception as e:
            health["status"] = "critical"
            health["issues"].append(f"Database connection failed: {str(e)}")
        
        return health
    
    @staticmethod
    async def _check_redis_health() -> Dict[str, Any]:
        """Check Redis health and memory usage"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": [],
            "response_time_ms": 0
        }
        
        try:
            start_time = time.time()
            
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=6379,
                db=0,
                decode_responses=True,
                socket_timeout=5.0
            )
            
            # Test connectivity
            await redis_client.ping()
            
            # Get server info
            info = await redis_client.info()
            
            response_time = (time.time() - start_time) * 1000
            health["response_time_ms"] = round(response_time, 2)
            
            # Extract key metrics
            health["metrics"].update({
                "memory_used_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
                "memory_peak_mb": round(info.get("used_memory_peak", 0) / 1024 / 1024, 2),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "response_time_ms": health["response_time_ms"]
            })
            
            # Calculate hit rate
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            if hits + misses > 0:
                hit_rate = (hits / (hits + misses)) * 100
                health["metrics"]["hit_rate_percent"] = round(hit_rate, 2)
                
                if hit_rate < 70:
                    health["warnings"].append(f"Low cache hit rate: {hit_rate:.1f}%")
                    health["status"] = "degraded"
            
            # Memory warnings
            memory_mb = health["metrics"]["memory_used_mb"]
            if memory_mb > 512:  # 512MB threshold
                health["warnings"].append(f"High memory usage: {memory_mb}MB")
                health["status"] = "degraded"
            
            # Response time warnings
            if response_time > 100:  # 100ms
                health["warnings"].append(f"Slow Redis response: {response_time:.0f}ms")
                if health["status"] == "healthy":
                    health["status"] = "degraded"
            
            await redis_client.close()
            
        except Exception as e:
            health["status"] = "critical"
            health["issues"].append(f"Redis connection failed: {str(e)}")
        
        return health
    
    @staticmethod
    async def _check_meilisearch_health() -> Dict[str, Any]:
        """Check Meilisearch health and indexing status"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": [],
            "response_time_ms": 0
        }
        
        try:
            start_time = time.time()
            
            # Use MeilisearchService for health check
            meilisearch_health = await MeilisearchService.health_check()
            
            response_time = (time.time() - start_time) * 1000
            health["response_time_ms"] = round(response_time, 2)
            
            health["status"] = meilisearch_health.get("status", "unknown")
            health["metrics"] = meilisearch_health.get("metrics", {})
            health["metrics"]["response_time_ms"] = health["response_time_ms"]
            
            # Additional checks
            if response_time > 2000:  # 2 seconds
                health["issues"].append(f"Slow Meilisearch response: {response_time:.0f}ms")
                health["status"] = "critical"
            elif response_time > 1000:  # 1 second
                health["warnings"].append(f"Elevated Meilisearch response time: {response_time:.0f}ms")
                if health["status"] == "healthy":
                    health["status"] = "degraded"
            
        except Exception as e:
            health["status"] = "critical"
            health["issues"].append(f"Meilisearch health check failed: {str(e)}")
        
        return health
    
    @staticmethod
    async def _check_firecrawl_health() -> Dict[str, Any]:
        """Check Firecrawl API and worker status"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": [],
            "components": {}
        }
        
        firecrawl_url = getattr(settings, 'FIRECRAWL_BASE_URL', 'http://localhost:3002')
        
        # Check Firecrawl API
        api_health = await MonitoringService._check_http_service(
            f"{firecrawl_url}/health",
            "Firecrawl API",
            timeout=10
        )
        health["components"]["api"] = api_health
        
        # Check Firecrawl Worker (if separate)
        worker_health = await MonitoringService._check_http_service(
            "http://localhost:3000/health",  # Playwright service
            "Firecrawl Worker",
            timeout=10
        )
        health["components"]["worker"] = worker_health
        
        # Aggregate status
        component_statuses = [comp["status"] for comp in health["components"].values()]
        
        if "critical" in component_statuses:
            health["status"] = "critical"
        elif "unhealthy" in component_statuses:
            health["status"] = "unhealthy"
        elif "degraded" in component_statuses:
            health["status"] = "degraded"
        
        # Collect issues and warnings
        for component in health["components"].values():
            health["issues"].extend(component.get("issues", []))
            health["warnings"].extend(component.get("warnings", []))
        
        return health
    
    @staticmethod
    async def _check_http_service(url: str, service_name: str, timeout: int = 5) -> Dict[str, Any]:
        """Check HTTP service health"""
        
        health = {
            "status": "healthy",
            "metrics": {},
            "issues": [],
            "warnings": [],
            "response_time_ms": 0
        }
        
        try:
            start_time = time.time()
            
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                
            response_time = (time.time() - start_time) * 1000
            health["response_time_ms"] = round(response_time, 2)
            
            health["metrics"].update({
                "status_code": response.status_code,
                "response_time_ms": health["response_time_ms"]
            })
            
            if response.status_code != 200:
                health["issues"].append(f"{service_name} returned status {response.status_code}")
                health["status"] = "unhealthy"
            elif response_time > 5000:  # 5 seconds
                health["issues"].append(f"{service_name} slow response: {response_time:.0f}ms")
                health["status"] = "degraded"
            elif response_time > 2000:  # 2 seconds
                health["warnings"].append(f"{service_name} elevated response time: {response_time:.0f}ms")
                health["status"] = "degraded"
            
        except Exception as e:
            health["status"] = "critical"
            health["issues"].append(f"{service_name} unreachable: {str(e)}")
        
        return health
    
    @staticmethod
    async def _get_system_metrics() -> Dict[str, Any]:
        """Get comprehensive system metrics"""
        
        metrics = {
            "status": "healthy",
            "cpu": {},
            "memory": {},
            "disk": {},
            "network": {},
            "load": {},
            "issues": [],
            "warnings": []
        }
        
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            metrics["cpu"].update({
                "usage_percent": cpu_percent,
                "count": cpu_count,
                "frequency_mhz": round(cpu_freq.current, 0) if cpu_freq else None
            })
            
            # Memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            metrics["memory"].update({
                "total_gb": round(memory.total / 1024**3, 2),
                "available_gb": round(memory.available / 1024**3, 2),
                "used_gb": round(memory.used / 1024**3, 2),
                "usage_percent": memory.percent,
                "swap_total_gb": round(swap.total / 1024**3, 2),
                "swap_used_gb": round(swap.used / 1024**3, 2),
                "swap_percent": swap.percent
            })
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            disk_io = psutil.disk_io_counters()
            
            metrics["disk"].update({
                "total_gb": round(disk.total / 1024**3, 2),
                "used_gb": round(disk.used / 1024**3, 2),
                "free_gb": round(disk.free / 1024**3, 2),
                "usage_percent": round((disk.used / disk.total) * 100, 1),
                "read_mb": round(disk_io.read_bytes / 1024**2, 2) if disk_io else 0,
                "write_mb": round(disk_io.write_bytes / 1024**2, 2) if disk_io else 0
            })
            
            # Network metrics
            network = psutil.net_io_counters()
            
            metrics["network"].update({
                "bytes_sent_mb": round(network.bytes_sent / 1024**2, 2),
                "bytes_recv_mb": round(network.bytes_recv / 1024**2, 2),
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv,
                "errors_in": network.errin,
                "errors_out": network.errout
            })
            
            # Load averages (Unix/Linux only)
            if hasattr(psutil, "getloadavg"):
                load1, load5, load15 = psutil.getloadavg()
                metrics["load"].update({
                    "load_1m": round(load1, 2),
                    "load_5m": round(load5, 2),
                    "load_15m": round(load15, 2)
                })
            
            # Health checks
            if cpu_percent > 90:
                metrics["issues"].append(f"Critical CPU usage: {cpu_percent:.1f}%")
                metrics["status"] = "critical"
            elif cpu_percent > 75:
                metrics["warnings"].append(f"High CPU usage: {cpu_percent:.1f}%")
                metrics["status"] = "degraded"
            
            if memory.percent > 90:
                metrics["issues"].append(f"Critical memory usage: {memory.percent:.1f}%")
                metrics["status"] = "critical"
            elif memory.percent > 80:
                metrics["warnings"].append(f"High memory usage: {memory.percent:.1f}%")
                if metrics["status"] == "healthy":
                    metrics["status"] = "degraded"
            
            disk_percent = (disk.used / disk.total) * 100
            if disk_percent > 95:
                metrics["issues"].append(f"Critical disk usage: {disk_percent:.1f}%")
                metrics["status"] = "critical"
            elif disk_percent > 85:
                metrics["warnings"].append(f"High disk usage: {disk_percent:.1f}%")
                if metrics["status"] == "healthy":
                    metrics["status"] = "degraded"
            
        except Exception as e:
            metrics["status"] = "unknown"
            metrics["issues"].append(f"System metrics collection failed: {str(e)}")
        
        return metrics
    
    @staticmethod
    async def _get_docker_metrics() -> Dict[str, Any]:
        """Get Docker container resource usage metrics"""
        
        metrics = {
            "status": "healthy",
            "containers": {},
            "summary": {},
            "issues": [],
            "warnings": []
        }
        
        try:
            # Get docker stats for all containers
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
                
                total_containers = len(lines)
                running_containers = 0
                
                for line in lines:
                    if line.strip():
                        parts = line.split('\t')
                        if len(parts) >= 4:
                            container = parts[0]
                            cpu_percent = parts[1].replace('%', '')
                            mem_usage = parts[2]
                            net_io = parts[3]
                            block_io = parts[4] if len(parts) > 4 else "N/A"
                            
                            running_containers += 1
                            
                            metrics["containers"][container] = {
                                "cpu_percent": cpu_percent,
                                "memory_usage": mem_usage,
                                "network_io": net_io,
                                "block_io": block_io
                            }
                            
                            # Check for high resource usage
                            try:
                                cpu_val = float(cpu_percent)
                                if cpu_val > 90:
                                    metrics["issues"].append(f"Container {container} high CPU: {cpu_val:.1f}%")
                                    metrics["status"] = "degraded"
                                elif cpu_val > 75:
                                    metrics["warnings"].append(f"Container {container} elevated CPU: {cpu_val:.1f}%")
                            except ValueError:
                                pass
                
                metrics["summary"].update({
                    "total_containers": total_containers,
                    "running_containers": running_containers
                })
                
            else:
                metrics["warnings"].append("Unable to collect Docker stats")
                metrics["status"] = "degraded"
                
        except subprocess.TimeoutExpired:
            metrics["warnings"].append("Docker stats command timed out")
            metrics["status"] = "degraded"
        except FileNotFoundError:
            metrics["warnings"].append("Docker command not found")
            metrics["status"] = "degraded"
        except Exception as e:
            metrics["warnings"].append(f"Docker metrics collection failed: {str(e)}")
            metrics["status"] = "degraded"
        
        return metrics
    
    @staticmethod
    async def _get_performance_metrics() -> Dict[str, Any]:
        """Get application performance metrics"""
        
        metrics = {
            "status": "healthy",
            "api_response_times": {},
            "throughput": {},
            "errors": {},
            "issues": [],
            "warnings": []
        }
        
        try:
            # Test API endpoints performance
            api_endpoints = [
                ("/api/v1/health", "health_check"),
                ("/api/v1/auth/me", "auth_endpoint"),  # This might fail without auth, but measures response time
            ]
            
            for endpoint, name in api_endpoints:
                try:
                    start_time = time.time()
                    async with httpx.AsyncClient(timeout=5.0) as client:
                        response = await client.get(f"http://localhost:8000{endpoint}")
                    
                    response_time = (time.time() - start_time) * 1000
                    metrics["api_response_times"][name] = {
                        "response_time_ms": round(response_time, 2),
                        "status_code": response.status_code
                    }
                    
                    if response_time > 2000:  # 2 seconds
                        metrics["issues"].append(f"Slow {name}: {response_time:.0f}ms")
                        metrics["status"] = "degraded"
                    elif response_time > 1000:  # 1 second
                        metrics["warnings"].append(f"Elevated {name} response time: {response_time:.0f}ms")
                        if metrics["status"] == "healthy":
                            metrics["status"] = "degraded"
                            
                except Exception as e:
                    metrics["api_response_times"][name] = {
                        "error": str(e),
                        "status": "failed"
                    }
                    metrics["warnings"].append(f"{name} test failed: {str(e)}")
            
        except Exception as e:
            metrics["warnings"].append(f"Performance metrics collection failed: {str(e)}")
            metrics["status"] = "degraded"
        
        return metrics
    
    @staticmethod
    async def get_celery_monitoring_metrics() -> Dict[str, Any]:
        """Get comprehensive Celery task monitoring metrics"""
        
        metrics = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "workers": {},
            "queues": {},
            "tasks": {},
            "performance": {},
            "issues": [],
            "warnings": []
        }
        
        try:
            # Get Celery inspector
            i = Inspect(current_app)
            
            # Worker status
            active_workers = i.active()
            i.reserved()
            worker_stats = i.stats()
            
            if active_workers:
                metrics["workers"]["count"] = len(active_workers)
                metrics["workers"]["active_tasks"] = sum(len(tasks) for tasks in active_workers.values())
                
                for worker, tasks in active_workers.items():
                    metrics["workers"][worker] = {
                        "active_tasks": len(tasks),
                        "task_names": [task["name"] for task in tasks[:5]]  # First 5 task names
                    }
                    
                    # Add worker stats if available
                    if worker_stats and worker in worker_stats:
                        worker_info = worker_stats[worker]
                        metrics["workers"][worker].update({
                            "total_tasks": worker_info.get("total", 0),
                            "pool_processes": worker_info.get("pool", {}).get("processes", 0)
                        })
            else:
                metrics["issues"].append("No active Celery workers found")
                metrics["status"] = "critical"
            
            # Queue analysis
            queue_lengths = await MonitoringService._get_redis_queue_lengths()
            metrics["queues"] = queue_lengths
            
            # Check for long queues
            for queue_name, length in queue_lengths.items():
                if isinstance(length, int):
                    if length > 100:
                        metrics["issues"].append(f"Large queue backlog in {queue_name}: {length} tasks")
                        metrics["status"] = "degraded"
                    elif length > 50:
                        metrics["warnings"].append(f"Growing queue in {queue_name}: {length} tasks")
                        if metrics["status"] == "healthy":
                            metrics["status"] = "degraded"
            
            # Task execution analysis (from Redis if available)
            task_metrics = await MonitoringService._get_task_execution_metrics()
            metrics["tasks"] = task_metrics
            
        except Exception as e:
            metrics["status"] = "critical"
            metrics["issues"].append(f"Celery monitoring failed: {str(e)}")
        
        return metrics
    
    @staticmethod
    async def _get_redis_queue_lengths() -> Dict[str, Any]:
        """Get Redis queue lengths for Celery"""
        
        queue_info = {}
        
        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=6379,
                db=0,
                decode_responses=True,
                socket_timeout=5.0
            )
            
            # Check common Celery queues
            queue_names = ["celery", "scraping", "indexing", "quick"]
            
            for queue_name in queue_names:
                length = await redis_client.llen(queue_name)
                queue_info[queue_name] = length
            
            # Get total pending tasks across all queues
            queue_info["total_pending"] = sum(v for v in queue_info.values() if isinstance(v, int))
            
            await redis_client.close()
            
        except Exception as e:
            queue_info["error"] = str(e)
        
        return queue_info
    
    @staticmethod
    async def _get_task_execution_metrics() -> Dict[str, Any]:
        """Get task execution metrics from recent history"""
        
        metrics = {
            "recent_completions": 0,
            "recent_failures": 0,
            "avg_execution_time_seconds": 0,
            "success_rate_percent": 0
        }
        
        try:
            # This would typically query a task result backend or monitoring system
            # For now, we'll provide a basic implementation
            
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=6379,
                db=0,
                decode_responses=True,
                socket_timeout=5.0
            )
            
            # Check for task result keys (basic implementation)
            keys = await redis_client.keys("celery-task-meta-*")
            
            if keys:
                # Sample a subset for performance
                sample_size = min(100, len(keys))
                sample_keys = keys[:sample_size]
                
                success_count = 0
                failure_count = 0
                
                for key in sample_keys:
                    try:
                        result = await redis_client.get(key)
                        if result:
                            task_data = json.loads(result)
                            status = task_data.get("status", "UNKNOWN")
                            
                            if status == "SUCCESS":
                                success_count += 1
                            elif status in ["FAILURE", "RETRY", "REVOKED"]:
                                failure_count += 1
                    except (json.JSONDecodeError, KeyError):
                        continue
                
                total_tasks = success_count + failure_count
                if total_tasks > 0:
                    metrics["recent_completions"] = success_count
                    metrics["recent_failures"] = failure_count
                    metrics["success_rate_percent"] = round((success_count / total_tasks) * 100, 2)
            
            await redis_client.close()
            
        except Exception as e:
            metrics["error"] = str(e)
        
        return metrics
    
    @staticmethod
    async def get_application_metrics(db: AsyncSession, days: int = 7) -> Dict[str, Any]:
        """Get comprehensive application metrics and usage statistics"""
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        metrics = {
            "period_days": days,
            "start_date": start_date.isoformat(),
            "end_date": datetime.utcnow().isoformat(),
            "user_activity": {},
            "scraping_performance": {},
            "entity_extraction": {},
            "search_usage": {},
            "errors": {},
            "generated_at": datetime.utcnow().isoformat()
        }
        
        try:
            # User registration and login rates
            user_registrations = await db.execute(
                select(func.count(User.id)).where(User.created_at >= start_date)
            )
            
            active_users = await db.execute(
                select(func.count(User.id)).where(
                    and_(
                        User.last_login >= start_date,
                        User.is_active is True
                    )
                )
            )
            
            metrics["user_activity"] = {
                "new_registrations": user_registrations.scalar() or 0,
                "active_users": active_users.scalar() or 0
            }
            
            # Scraping session statistics
            scraping_sessions = await db.execute(
                select(func.count(ScrapeSession.id)).where(ScrapeSession.created_at >= start_date)
            )
            
            pages_scraped = await db.execute(
                select(func.count(Page.id)).where(Page.scraped_at >= start_date)
            )
            
            # Average processing time
            avg_processing = await db.execute(
                text("""
                    SELECT AVG(EXTRACT(EPOCH FROM (processed_at - scraped_at))) as avg_seconds
                    FROM pages 
                    WHERE processed_at IS NOT NULL 
                    AND scraped_at >= :start_date
                """),
                {"start_date": start_date}
            )
            
            metrics["scraping_performance"] = {
                "total_sessions": scraping_sessions.scalar() or 0,
                "pages_scraped": pages_scraped.scalar() or 0,
                "avg_processing_time_seconds": round(avg_processing.scalar() or 0, 2)
            }
            
            # Entity extraction performance (if entities table exists)
            try:
                from app.models.entities import ExtractedEntity
                
                entities_extracted = await db.execute(
                    select(func.count(ExtractedEntity.id)).where(
                        ExtractedEntity.extracted_at >= start_date
                    )
                )
                
                avg_confidence = await db.execute(
                    select(func.avg(ExtractedEntity.extraction_confidence)).where(
                        ExtractedEntity.extracted_at >= start_date
                    )
                )
                
                metrics["entity_extraction"] = {
                    "total_entities": entities_extracted.scalar() or 0,
                    "avg_confidence": round(avg_confidence.scalar() or 0, 3)
                }
                
            except ImportError:
                metrics["entity_extraction"] = {"status": "not_available"}
            
            # Search query volumes (would need search log table)
            metrics["search_usage"] = {
                "status": "not_implemented",
                "note": "Requires search query logging implementation"
            }
            
            # Error analysis
            error_pages = await db.execute(
                select(func.count(Page.id)).where(
                    and_(
                        Page.scraped_at >= start_date,
                        Page.processed is False,
                        Page.scraped_at.isnot(None)
                    )
                )
            )
            
            metrics["errors"] = {
                "failed_page_processing": error_pages.scalar() or 0
            }
            
        except Exception as e:
            metrics["error"] = f"Application metrics collection failed: {str(e)}"
        
        return metrics
    
    @staticmethod
    async def get_error_log_aggregation(db: AsyncSession, hours: int = 24) -> Dict[str, Any]:
        """Get error log aggregation and analysis"""
        
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        error_analysis = {
            "period_hours": hours,
            "start_time": start_time.isoformat(),
            "end_time": datetime.utcnow().isoformat(),
            "database_errors": {},
            "processing_errors": {},
            "critical_alerts": [],
            "error_trends": [],
            "generated_at": datetime.utcnow().isoformat()
        }
        
        try:
            # Database-level errors (pages that failed processing)
            failed_pages = await db.execute(
                select(
                    Page.id,
                    Page.original_url,
                    Page.scraped_at,
                    Page.error_message
                ).where(
                    and_(
                        Page.scraped_at >= start_time,
                        Page.processed is False,
                        Page.error_message.isnot(None)
                    )
                ).limit(50)  # Limit for performance
            )
            
            failed_pages_list = []
            error_types = {}
            
            for page_id, url, scraped_at, error_msg in failed_pages:
                failed_pages_list.append({
                    "page_id": page_id,
                    "url": url[:100] + "..." if len(url) > 100 else url,
                    "scraped_at": scraped_at.isoformat() if scraped_at else None,
                    "error": error_msg[:200] + "..." if error_msg and len(error_msg) > 200 else error_msg
                })
                
                # Categorize error types
                if error_msg:
                    error_key = error_msg.split(':')[0].strip()  # Get first part of error
                    error_types[error_key] = error_types.get(error_key, 0) + 1
            
            error_analysis["database_errors"] = {
                "total_failed_pages": len(failed_pages_list),
                "recent_failures": failed_pages_list[:10],  # Most recent 10
                "error_types": error_types
            }
            
            # Processing pipeline errors (shared pages)
            try:
                from app.models.shared_pages import PageV2
                
                shared_page_errors = await db.execute(
                    select(
                        func.count(PageV2.id),
                        PageV2.error_message
                    ).where(
                        and_(
                            PageV2.updated_at >= start_time,
                            PageV2.error_message.isnot(None)
                        )
                    ).group_by(PageV2.error_message)
                    .order_by(func.count(PageV2.id).desc())
                    .limit(20)
                )
                
                processing_errors = []
                for count, error_msg in shared_page_errors:
                    processing_errors.append({
                        "count": count,
                        "error": error_msg[:150] + "..." if error_msg and len(error_msg) > 150 else error_msg
                    })
                
                error_analysis["processing_errors"] = {
                    "total_types": len(processing_errors),
                    "top_errors": processing_errors
                }
                
            except ImportError:
                error_analysis["processing_errors"] = {"status": "not_available"}
            
            # Critical alerts (high-frequency errors)
            critical_threshold = 10  # errors per hour
            
            for error_type, count in error_types.items():
                error_rate = count / hours
                if error_rate >= critical_threshold:
                    error_analysis["critical_alerts"].append({
                        "type": error_type,
                        "count": count,
                        "rate_per_hour": round(error_rate, 2),
                        "severity": "critical" if error_rate >= 20 else "high"
                    })
            
            # Error trends (hourly breakdown)
            hourly_errors = await db.execute(
                text("""
                    SELECT 
                        DATE_TRUNC('hour', scraped_at) as hour,
                        COUNT(*) as error_count
                    FROM pages 
                    WHERE scraped_at >= :start_time
                    AND processed = false
                    AND error_message IS NOT NULL
                    GROUP BY DATE_TRUNC('hour', scraped_at)
                    ORDER BY hour
                """),
                {"start_time": start_time}
            )
            
            trends = []
            for hour, count in hourly_errors:
                trends.append({
                    "hour": hour.isoformat() if hour else None,
                    "error_count": count
                })
            
            error_analysis["error_trends"] = trends
            
        except Exception as e:
            error_analysis["collection_error"] = f"Error log aggregation failed: {str(e)}"
        
        return error_analysis