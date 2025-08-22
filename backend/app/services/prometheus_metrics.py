"""
Prometheus metrics service for shared pages architecture monitoring
"""
from typing import Dict, Any, List
from datetime import datetime, timedelta
from sqlmodel import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.shared_pages import PageV2, ProjectPage, CDXPageRegistry, ScrapeStatus
from app.models.project import Project, Domain, Page, ProjectStatus
from app.models.user import User

logger = logging.getLogger(__name__)


class PrometheusMetricsService:
    """Service for generating Prometheus metrics"""
    
    @staticmethod
    async def generate_shared_pages_metrics(db: AsyncSession) -> str:
        """Generate Prometheus metrics for shared pages architecture"""
        
        metrics_lines = []
        
        try:
            # Core shared pages metrics
            total_pages_v2 = await db.execute(select(func.count(PageV2.id)))
            total_project_pages = await db.execute(select(func.count(ProjectPage.id)))
            total_cdx_registry = await db.execute(select(func.count(CDXPageRegistry.id)))
            
            metrics_lines.extend([
                "# HELP chrono_shared_pages_total Total number of shared pages",
                "# TYPE chrono_shared_pages_total gauge",
                f"chrono_shared_pages_total {total_pages_v2.scalar() or 0}",
                "",
                "# HELP chrono_project_associations_total Total number of project-page associations",
                "# TYPE chrono_project_associations_total gauge", 
                f"chrono_project_associations_total {total_project_pages.scalar() or 0}",
                "",
                "# HELP chrono_cdx_registry_total Total number of CDX registry entries",
                "# TYPE chrono_cdx_registry_total gauge",
                f"chrono_cdx_registry_total {total_cdx_registry.scalar() or 0}",
                ""
            ])
            
            # Processing status metrics
            processed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.processed == True)
            )
            indexed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.indexed == True)
            )
            failed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.error_message.isnot(None))
            )
            
            metrics_lines.extend([
                "# HELP chrono_pages_processed_total Total number of processed pages",
                "# TYPE chrono_pages_processed_total gauge",
                f"chrono_pages_processed_total {processed_pages.scalar() or 0}",
                "",
                "# HELP chrono_pages_indexed_total Total number of indexed pages",
                "# TYPE chrono_pages_indexed_total gauge",
                f"chrono_pages_indexed_total {indexed_pages.scalar() or 0}",
                "",
                "# HELP chrono_pages_failed_total Total number of failed pages",
                "# TYPE chrono_pages_failed_total gauge",
                f"chrono_pages_failed_total {failed_pages.scalar() or 0}",
                ""
            ])
            
            # CDX deduplication efficiency
            cdx_with_pages = await db.execute(
                select(func.count(CDXPageRegistry.id)).where(CDXPageRegistry.page_id.isnot(None))
            )
            
            cdx_total = total_cdx_registry.scalar() or 0
            cdx_linked = cdx_with_pages.scalar() or 0
            deduplication_rate = (cdx_linked / cdx_total * 100) if cdx_total > 0 else 0
            
            metrics_lines.extend([
                "# HELP chrono_cdx_deduplication_rate_percent CDX deduplication efficiency rate",
                "# TYPE chrono_cdx_deduplication_rate_percent gauge",
                f"chrono_cdx_deduplication_rate_percent {round(deduplication_rate, 2)}",
                "",
                "# HELP chrono_cdx_linked_entries Total CDX entries linked to pages",
                "# TYPE chrono_cdx_linked_entries gauge",
                f"chrono_cdx_linked_entries {cdx_linked}",
                ""
            ])
            
            # Sharing efficiency metrics
            sharing_stats = await db.execute(
                text("""
                    SELECT 
                        COUNT(DISTINCT pp.page_id) as unique_pages,
                        COUNT(pp.id) as total_associations
                    FROM project_pages pp
                """)
            )
            
            sharing_result = sharing_stats.first()
            unique_pages = sharing_result.unique_pages if sharing_result else 0
            total_associations = sharing_result.total_associations if sharing_result else 0
            
            sharing_efficiency = 0
            if total_associations > 0 and unique_pages > 0:
                sharing_efficiency = ((total_associations - unique_pages) / total_associations * 100)
            
            api_calls_saved = total_associations - unique_pages if total_associations > unique_pages else 0
            
            metrics_lines.extend([
                "# HELP chrono_sharing_efficiency_percent Page sharing efficiency percentage",
                "# TYPE chrono_sharing_efficiency_percent gauge",
                f"chrono_sharing_efficiency_percent {round(sharing_efficiency, 2)}",
                "",
                "# HELP chrono_api_calls_saved_total Estimated API calls saved through sharing",
                "# TYPE chrono_api_calls_saved_total gauge",
                f"chrono_api_calls_saved_total {api_calls_saved}",
                ""
            ])
            
            # Performance metrics
            avg_processing_time = await db.execute(
                text("""
                    SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) as avg_seconds
                    FROM pages_v2 
                    WHERE processed = true 
                    AND created_at >= NOW() - INTERVAL '24 hours'
                """)
            )
            
            avg_seconds = avg_processing_time.scalar() or 0
            
            metrics_lines.extend([
                "# HELP chrono_avg_processing_time_seconds Average page processing time in seconds",
                "# TYPE chrono_avg_processing_time_seconds gauge",
                f"chrono_avg_processing_time_seconds {round(avg_seconds, 2)}",
                ""
            ])
            
            # Recent activity metrics (last 24 hours)
            day_ago = datetime.utcnow() - timedelta(days=1)
            
            recent_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.created_at >= day_ago)
            )
            recent_associations = await db.execute(
                select(func.count(ProjectPage.id)).where(ProjectPage.added_at >= day_ago)
            )
            recent_cdx = await db.execute(
                select(func.count(CDXPageRegistry.id)).where(CDXPageRegistry.first_seen_at >= day_ago)
            )
            
            metrics_lines.extend([
                "# HELP chrono_pages_created_24h Pages created in last 24 hours",
                "# TYPE chrono_pages_created_24h gauge",
                f"chrono_pages_created_24h {recent_pages.scalar() or 0}",
                "",
                "# HELP chrono_associations_created_24h Project associations created in last 24 hours",
                "# TYPE chrono_associations_created_24h gauge",
                f"chrono_associations_created_24h {recent_associations.scalar() or 0}",
                "",
                "# HELP chrono_cdx_entries_24h CDX entries created in last 24 hours",
                "# TYPE chrono_cdx_entries_24h gauge",
                f"chrono_cdx_entries_24h {recent_cdx.scalar() or 0}",
                ""
            ])
            
            # Error rate metrics
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
            error_rate = (error_count / total_recent * 100) if total_recent > 0 else 0
            
            metrics_lines.extend([
                "# HELP chrono_error_rate_24h_percent Error rate in last 24 hours",
                "# TYPE chrono_error_rate_24h_percent gauge",
                f"chrono_error_rate_24h_percent {round(error_rate, 2)}",
                "",
                "# HELP chrono_errors_24h Total errors in last 24 hours",
                "# TYPE chrono_errors_24h gauge",
                f"chrono_errors_24h {error_count}",
                ""
            ])
            
            # Processing backlog metrics
            unprocessed_pages = await db.execute(
                select(func.count(PageV2.id)).where(PageV2.processed == False)
            )
            
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
            
            metrics_lines.extend([
                "# HELP chrono_processing_backlog Total unprocessed pages",
                "# TYPE chrono_processing_backlog gauge",
                f"chrono_processing_backlog {unprocessed_pages.scalar() or 0}",
                "",
                "# HELP chrono_stuck_pages Pages stuck in processing (>1 hour)",
                "# TYPE chrono_stuck_pages gauge",
                f"chrono_stuck_pages {stuck_pages.scalar() or 0}",
                ""
            ])
            
            # Indexing metrics
            indexing_backlog = (processed_pages.scalar() or 0) - (indexed_pages.scalar() or 0)
            
            metrics_lines.extend([
                "# HELP chrono_indexing_backlog Pages processed but not indexed",
                "# TYPE chrono_indexing_backlog gauge",
                f"chrono_indexing_backlog {indexing_backlog}",
                ""
            ])
            
            # CDX status breakdown
            cdx_status_counts = await db.execute(
                select(CDXPageRegistry.scrape_status, func.count(CDXPageRegistry.id))
                .group_by(CDXPageRegistry.scrape_status)
            )
            
            for status, count in cdx_status_counts:
                metrics_lines.extend([
                    f"# HELP chrono_cdx_status_{status.value} CDX entries with status {status.value}",
                    f"# TYPE chrono_cdx_status_{status.value} gauge",
                    f"chrono_cdx_status_{status.value} {count}",
                    ""
                ])
            
        except Exception as e:
            logger.error(f"Error generating shared pages metrics: {str(e)}")
            metrics_lines.extend([
                "# HELP chrono_metrics_error Metrics generation error",
                "# TYPE chrono_metrics_error gauge",
                "chrono_metrics_error 1",
                ""
            ])
        
        return "\n".join(metrics_lines)
    
    @staticmethod
    async def generate_health_metrics(db: AsyncSession) -> str:
        """Generate Prometheus health metrics"""
        
        metrics_lines = []
        
        try:
            # Database connectivity
            try:
                await db.execute(text("SELECT 1"))
                db_healthy = 1
            except Exception:
                db_healthy = 0
            
            metrics_lines.extend([
                "# HELP chrono_database_healthy Database connectivity status (1=healthy, 0=unhealthy)",
                "# TYPE chrono_database_healthy gauge",
                f"chrono_database_healthy {db_healthy}",
                ""
            ])
            
            # Shared pages tables accessibility
            try:
                await db.execute(text("SELECT COUNT(*) FROM pages_v2 LIMIT 1"))
                pages_v2_accessible = 1
            except Exception:
                pages_v2_accessible = 0
            
            try:
                await db.execute(text("SELECT COUNT(*) FROM project_pages LIMIT 1"))
                project_pages_accessible = 1
            except Exception:
                project_pages_accessible = 0
            
            try:
                await db.execute(text("SELECT COUNT(*) FROM cdx_page_registry LIMIT 1"))
                cdx_registry_accessible = 1
            except Exception:
                cdx_registry_accessible = 0
            
            metrics_lines.extend([
                "# HELP chrono_pages_v2_table_accessible Pages v2 table accessibility",
                "# TYPE chrono_pages_v2_table_accessible gauge",
                f"chrono_pages_v2_table_accessible {pages_v2_accessible}",
                "",
                "# HELP chrono_project_pages_table_accessible Project pages table accessibility",
                "# TYPE chrono_project_pages_table_accessible gauge",
                f"chrono_project_pages_table_accessible {project_pages_accessible}",
                "",
                "# HELP chrono_cdx_registry_table_accessible CDX registry table accessibility",
                "# TYPE chrono_cdx_registry_table_accessible gauge",
                f"chrono_cdx_registry_table_accessible {cdx_registry_accessible}",
                ""
            ])
            
            # Overall shared pages health
            shared_pages_healthy = 1 if all([
                db_healthy, pages_v2_accessible, project_pages_accessible, cdx_registry_accessible
            ]) else 0
            
            metrics_lines.extend([
                "# HELP chrono_shared_pages_healthy Overall shared pages architecture health",
                "# TYPE chrono_shared_pages_healthy gauge",
                f"chrono_shared_pages_healthy {shared_pages_healthy}",
                ""
            ])
            
        except Exception as e:
            logger.error(f"Error generating health metrics: {str(e)}")
            metrics_lines.extend([
                "# HELP chrono_health_metrics_error Health metrics generation error",
                "# TYPE chrono_health_metrics_error gauge",
                "chrono_health_metrics_error 1",
                ""
            ])
        
        return "\n".join(metrics_lines)
    
    @staticmethod
    async def generate_business_metrics(db: AsyncSession, days: int = 30) -> str:
        """Generate Prometheus business metrics"""
        
        metrics_lines = []
        start_date = datetime.utcnow() - timedelta(days=days)
        
        try:
            # API efficiency metrics
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
            
            api_reduction_percentage = (api_calls_saved / total_associations * 100) if total_associations > 0 else 0
            estimated_wayback_calls_saved = api_calls_saved * 5000  # Assuming 5000 calls per session
            
            metrics_lines.extend([
                f"# HELP chrono_api_reduction_percentage_{days}d API call reduction percentage over {days} days",
                f"# TYPE chrono_api_reduction_percentage_{days}d gauge",
                f"chrono_api_reduction_percentage_{days}d {round(api_reduction_percentage, 2)}",
                "",
                f"# HELP chrono_wayback_calls_saved_{days}d Estimated Wayback Machine calls saved over {days} days",
                f"# TYPE chrono_wayback_calls_saved_{days}d gauge",
                f"chrono_wayback_calls_saved_{days}d {estimated_wayback_calls_saved}",
                ""
            ])
            
            # Storage efficiency metrics
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
            
            storage_efficiency_percentage = (estimated_duplicate_storage / (total_content_bytes + estimated_duplicate_storage) * 100) if (total_content_bytes + estimated_duplicate_storage) > 0 else 0
            
            metrics_lines.extend([
                f"# HELP chrono_storage_efficiency_percentage_{days}d Storage efficiency percentage over {days} days",
                f"# TYPE chrono_storage_efficiency_percentage_{days}d gauge",
                f"chrono_storage_efficiency_percentage_{days}d {round(storage_efficiency_percentage, 2)}",
                "",
                f"# HELP chrono_storage_saved_bytes_{days}d Storage bytes saved through deduplication over {days} days",
                f"# TYPE chrono_storage_saved_bytes_{days}d gauge",
                f"chrono_storage_saved_bytes_{days}d {int(estimated_duplicate_storage)}",
                ""
            ])
            
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
            
            avg_associations_per_project = (total_associations / projects_using_sharing) if projects_using_sharing > 0 else 0
            
            metrics_lines.extend([
                f"# HELP chrono_users_using_sharing_{days}d Users utilizing shared pages over {days} days",
                f"# TYPE chrono_users_using_sharing_{days}d gauge",
                f"chrono_users_using_sharing_{days}d {users_with_shared_pages}",
                "",
                f"# HELP chrono_projects_using_sharing_{days}d Projects using sharing over {days} days",
                f"# TYPE chrono_projects_using_sharing_{days}d gauge",
                f"chrono_projects_using_sharing_{days}d {projects_using_sharing}",
                "",
                f"# HELP chrono_avg_associations_per_project_{days}d Average associations per project over {days} days",
                f"# TYPE chrono_avg_associations_per_project_{days}d gauge",
                f"chrono_avg_associations_per_project_{days}d {round(avg_associations_per_project, 2)}",
                ""
            ])
            
        except Exception as e:
            logger.error(f"Error generating business metrics: {str(e)}")
            metrics_lines.extend([
                "# HELP chrono_business_metrics_error Business metrics generation error",
                "# TYPE chrono_business_metrics_error gauge",
                "chrono_business_metrics_error 1",
                ""
            ])
        
        return "\n".join(metrics_lines)