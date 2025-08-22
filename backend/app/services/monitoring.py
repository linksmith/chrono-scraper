"""
Monitoring and statistics services with shared pages architecture support
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlmodel import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import time
import redis.asyncio as redis
import asyncio

from app.models.project import Project, Domain, Page, ScrapeSession, ProjectStatus, DomainStatus
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

    @staticmethod
    async def get_shared_pages_metrics(db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive shared pages architecture metrics"""
        
        # Core shared pages statistics
        total_pages_v2 = await db.execute(select(func.count(PageV2.id)))
        total_project_pages = await db.execute(select(func.count(ProjectPage.id)))
        total_cdx_registry = await db.execute(select(func.count(CDXPageRegistry.id)))
        
        # Processing status breakdown
        processed_pages = await db.execute(
            select(func.count(PageV2.id)).where(PageV2.processed == True)
        )
        
        indexed_pages = await db.execute(
            select(func.count(PageV2.id)).where(PageV2.indexed == True)
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
                select(func.count(PageV2.id)).where(PageV2.processed == False)
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
                        PageV2.processed == False,
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
                select(func.count(PageV2.id)).where(PageV2.processed == True)
            )
            
            indexed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.indexed == True)
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