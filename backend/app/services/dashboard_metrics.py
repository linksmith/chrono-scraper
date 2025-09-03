"""
Dashboard metrics service for comprehensive admin dashboard
Aggregates data from monitoring, audit, user analytics, and system services
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, desc, and_

from app.models.user import User
from app.models.project import Project, Domain
from app.models.shared_pages import PageV2, ProjectPage
from app.models.entities import CanonicalEntity, ExtractedEntity
from app.models.audit_log import AuditLog, SeverityLevel, AuditCategory
from app.services.monitoring import MonitoringService

logger = logging.getLogger(__name__)


class DashboardMetricsService:
    """Service for aggregating comprehensive dashboard metrics"""
    
    @staticmethod
    async def get_executive_summary(db: AsyncSession, cache_ttl: int = 300) -> Dict[str, Any]:
        """Get high-level executive summary metrics"""
        cache_key = "dashboard:executive_summary"
        
        # Try to get from cache first
        cached_data = await CacheService.get(cache_key)
        if cached_data:
            return cached_data
        
        try:
            # Get current timestamp
            now = datetime.utcnow()
            
            # Parallel execution of all summary metrics
            tasks = [
                DashboardMetricsService._get_user_metrics(db),
                DashboardMetricsService._get_content_metrics(db),
                DashboardMetricsService._get_system_health_summary(),
                DashboardMetricsService._get_security_summary(db),
                DashboardMetricsService._get_activity_trends(db),
                DashboardMetricsService._get_performance_summary()
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle exceptions
            user_metrics = results[0] if not isinstance(results[0], Exception) else {}
            content_metrics = results[1] if not isinstance(results[1], Exception) else {}
            system_health = results[2] if not isinstance(results[2], Exception) else {}
            security_summary = results[3] if not isinstance(results[3], Exception) else {}
            activity_trends = results[4] if not isinstance(results[4], Exception) else {}
            performance_summary = results[5] if not isinstance(results[5], Exception) else {}
            
            # Calculate key performance indicators
            kpis = {
                "total_users": user_metrics.get("total_users", 0),
                "active_users_24h": user_metrics.get("active_24h", 0),
                "total_pages": content_metrics.get("total_pages", 0),
                "pages_processed_24h": content_metrics.get("processed_24h", 0),
                "system_health_score": system_health.get("health_score", 0),
                "security_incidents_24h": security_summary.get("incidents_24h", 0),
                "avg_response_time": performance_summary.get("avg_response_time", 0),
                "task_queue_size": performance_summary.get("queue_size", 0)
            }
            
            # Calculate growth rates (24h vs previous 24h)
            growth_rates = await DashboardMetricsService._calculate_growth_rates(db)
            
            summary = {
                "timestamp": now.isoformat(),
                "kpis": kpis,
                "growth_rates": growth_rates,
                "user_metrics": user_metrics,
                "content_metrics": content_metrics,
                "system_health": system_health,
                "security_summary": security_summary,
                "activity_trends": activity_trends,
                "performance_summary": performance_summary,
                "alerts": await DashboardMetricsService._get_active_alerts(db),
                "recent_activity": await DashboardMetricsService._get_recent_activity(db, limit=10)
            }
            
            # Cache the result
            await CacheService.set(cache_key, summary, expire=cache_ttl)
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting executive summary: {str(e)}")
            return {
                "error": str(e),
                "timestamp": now.isoformat(),
                "kpis": {},
                "alerts": []
            }
    
    @staticmethod
    async def get_real_time_metrics(db: AsyncSession) -> Dict[str, Any]:
        """Get real-time metrics for live updates"""
        try:
            now = datetime.utcnow()
            
            # Quick parallel execution of real-time metrics
            tasks = [
                DashboardMetricsService._get_current_active_users(db),
                DashboardMetricsService._get_current_task_status(),
                DashboardMetricsService._get_system_resources(),
                DashboardMetricsService._get_recent_errors(db, minutes=5)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            return {
                "timestamp": now.isoformat(),
                "active_users": results[0] if not isinstance(results[0], Exception) else 0,
                "task_status": results[1] if not isinstance(results[1], Exception) else {},
                "system_resources": results[2] if not isinstance(results[2], Exception) else {},
                "recent_errors": results[3] if not isinstance(results[3], Exception) else []
            }
            
        except Exception as e:
            logger.error(f"Error getting real-time metrics: {str(e)}")
            return {"error": str(e), "timestamp": now.isoformat()}
    
    @staticmethod
    async def get_analytics_dashboard_data(
        db: AsyncSession, 
        time_range: str = "7d"
    ) -> Dict[str, Any]:
        """Get comprehensive analytics data for dashboard charts"""
        try:
            # Parse time range
            days = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}.get(time_range, 7)
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Get analytics data in parallel
            tasks = [
                DashboardMetricsService._get_user_activity_chart(db, start_date, end_date),
                DashboardMetricsService._get_content_processing_chart(db, start_date, end_date),
                DashboardMetricsService._get_entity_extraction_chart(db, start_date, end_date),
                DashboardMetricsService._get_security_events_chart(db, start_date, end_date),
                DashboardMetricsService._get_system_performance_chart(start_date, end_date),
                DashboardMetricsService._get_geographic_distribution(db),
                DashboardMetricsService._get_top_domains_and_projects(db, days)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            return {
                "time_range": time_range,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "user_activity": results[0] if not isinstance(results[0], Exception) else [],
                "content_processing": results[1] if not isinstance(results[1], Exception) else [],
                "entity_extraction": results[2] if not isinstance(results[2], Exception) else [],
                "security_events": results[3] if not isinstance(results[3], Exception) else [],
                "system_performance": results[4] if not isinstance(results[4], Exception) else [],
                "geographic_distribution": results[5] if not isinstance(results[5], Exception) else [],
                "top_domains_projects": results[6] if not isinstance(results[6], Exception) else {}
            }
            
        except Exception as e:
            logger.error(f"Error getting analytics dashboard data: {str(e)}")
            return {"error": str(e)}
    
    # Helper methods for specific metrics
    
    @staticmethod
    async def _get_user_metrics(db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive user metrics"""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)
        
        # Total users
        total_users = await db.execute(select(func.count(User.id)))
        total_count = total_users.scalar()
        
        # Active users (last 24h)
        active_users = await db.execute(
            select(func.count(User.id)).where(User.last_login >= yesterday)
        )
        active_24h = active_users.scalar()
        
        # New users (last 7 days)
        new_users = await db.execute(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )
        new_7d = new_users.scalar()
        
        # User status distribution
        user_status = await db.execute(
            select(
                User.approval_status,
                func.count(User.id).label('count')
            ).group_by(User.approval_status)
        )
        status_distribution = {row.approval_status: row.count for row in user_status}
        
        # Verified users
        verified_users = await db.execute(
            select(func.count(User.id)).where(User.is_verified is True)
        )
        verified_count = verified_users.scalar()
        
        return {
            "total_users": total_count,
            "active_24h": active_24h,
            "new_7d": new_7d,
            "verified_users": verified_count,
            "status_distribution": status_distribution,
            "activity_rate": round((active_24h / total_count * 100) if total_count > 0 else 0, 2),
            "verification_rate": round((verified_count / total_count * 100) if total_count > 0 else 0, 2)
        }
    
    @staticmethod
    async def _get_content_metrics(db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive content metrics"""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        
        # Total pages (both Page and PageV2)
        total_pages_v2 = await db.execute(select(func.count(PageV2.id)))
        total_v2 = total_pages_v2.scalar()
        
        # Pages processed in last 24h
        processed_24h = await db.execute(
            select(func.count(PageV2.id)).where(
                and_(
                    PageV2.updated_at >= yesterday,
                    PageV2.processed is True
                )
            )
        )
        processed_count = processed_24h.scalar()
        
        # Total entities
        total_entities = await db.execute(select(func.count(CanonicalEntity.id)))
        entities_count = total_entities.scalar()
        
        # Entity extraction rate
        extracted_entities = await db.execute(
            select(func.count(ExtractedEntity.id)).where(
                ExtractedEntity.extracted_at >= yesterday
            )
        )
        extracted_24h = extracted_entities.scalar()
        
        # Content quality metrics
        avg_quality = await db.execute(
            select(func.avg(PageV2.quality_score)).where(PageV2.quality_score.is_not(None))
        )
        avg_quality_score = avg_quality.scalar() or 0
        
        # Word count statistics
        word_stats = await db.execute(
            select(
                func.avg(PageV2.word_count).label('avg_words'),
                func.sum(PageV2.word_count).label('total_words')
            ).where(PageV2.word_count.is_not(None))
        )
        word_data = word_stats.first()
        
        return {
            "total_pages": total_v2,
            "processed_24h": processed_count,
            "total_entities": entities_count,
            "extracted_entities_24h": extracted_24h,
            "avg_quality_score": round(float(avg_quality_score), 2),
            "avg_word_count": int(word_data.avg_words or 0),
            "total_words": int(word_data.total_words or 0),
            "processing_rate": round((processed_count / 1440 * 100) if processed_count > 0 else 0, 2)  # Per minute
        }
    
    @staticmethod
    async def _get_system_health_summary() -> Dict[str, Any]:
        """Get system health summary"""
        try:
            # Get comprehensive system health
            health_data = await MonitoringService.get_comprehensive_system_health()
            
            # Calculate health score based on service statuses
            services = health_data.get("services", {})
            total_services = len(services)
            healthy_services = sum(1 for status in services.values() if status.get("status") == "healthy")
            
            health_score = round((healthy_services / total_services * 100) if total_services > 0 else 0, 1)
            
            return {
                "overall_status": health_data.get("overall", "unknown"),
                "health_score": health_score,
                "healthy_services": healthy_services,
                "total_services": total_services,
                "issues_count": len(health_data.get("issues", [])),
                "warnings_count": len(health_data.get("warnings", [])),
                "services": services
            }
        except Exception as e:
            logger.error(f"Error getting system health summary: {str(e)}")
            return {
                "overall_status": "unknown",
                "health_score": 0,
                "error": str(e)
            }
    
    @staticmethod
    async def _get_security_summary(db: AsyncSession) -> Dict[str, Any]:
        """Get security summary for last 24h"""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        
        # Security incidents
        incidents = await db.execute(
            select(func.count(AuditLog.id)).where(
                and_(
                    AuditLog.created_at >= yesterday,
                    AuditLog.category == AuditCategory.SECURITY_EVENT,
                    AuditLog.severity.in_([SeverityLevel.HIGH, SeverityLevel.CRITICAL])
                )
            )
        )
        incidents_24h = incidents.scalar()
        
        # Failed login attempts
        failed_logins = await db.execute(
            select(func.count(AuditLog.id)).where(
                and_(
                    AuditLog.created_at >= yesterday,
                    AuditLog.action.contains("LOGIN_FAILED")
                )
            )
        )
        failed_logins_24h = failed_logins.scalar()
        
        # Unique suspicious IPs
        suspicious_ips = await db.execute(
            select(func.count(func.distinct(AuditLog.ip_address))).where(
                and_(
                    AuditLog.created_at >= yesterday,
                    AuditLog.success is False,
                    AuditLog.ip_address.is_not(None)
                )
            )
        )
        suspicious_ip_count = suspicious_ips.scalar()
        
        return {
            "incidents_24h": incidents_24h,
            "failed_logins_24h": failed_logins_24h,
            "suspicious_ips": suspicious_ip_count,
            "threat_level": "low" if incidents_24h == 0 else ("medium" if incidents_24h < 5 else "high")
        }
    
    @staticmethod
    async def _get_activity_trends(db: AsyncSession) -> Dict[str, Any]:
        """Get activity trends for the last 7 days"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        
        # Daily activity counts
        daily_activity = await db.execute(
            select(
                func.date(AuditLog.created_at).label('date'),
                func.count(AuditLog.id).label('count')
            ).where(
                AuditLog.created_at >= start_date
            ).group_by(func.date(AuditLog.created_at)).order_by('date')
        )
        
        activity_data = [
            {"date": str(row.date), "count": row.count}
            for row in daily_activity
        ]
        
        return {
            "daily_activity": activity_data,
            "trend": "increasing" if len(activity_data) >= 2 and activity_data[-1]["count"] > activity_data[0]["count"] else "stable"
        }
    
    @staticmethod
    async def _get_performance_summary() -> Dict[str, Any]:
        """Get performance summary"""
        try:
            # Get Celery metrics
            celery_metrics = await MonitoringService.get_celery_monitoring_metrics()
            
            # Get API performance metrics
            api_metrics = await MonitoringService._get_performance_metrics()
            
            return {
                "avg_response_time": api_metrics.get("avg_response_time", 0),
                "queue_size": celery_metrics.get("active_queues", {}).get("total_tasks", 0),
                "worker_status": celery_metrics.get("worker_stats", {}),
                "api_status": api_metrics.get("status", "unknown")
            }
        except Exception as e:
            logger.error(f"Error getting performance summary: {str(e)}")
            return {
                "avg_response_time": 0,
                "queue_size": 0,
                "error": str(e)
            }
    
    @staticmethod
    async def _calculate_growth_rates(db: AsyncSession) -> Dict[str, float]:
        """Calculate growth rates comparing last 24h vs previous 24h"""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        day_before = now - timedelta(days=2)
        
        # Users growth
        current_new_users = await db.execute(
            select(func.count(User.id)).where(User.created_at >= yesterday)
        )
        current_users = current_new_users.scalar()
        
        previous_new_users = await db.execute(
            select(func.count(User.id)).where(
                and_(User.created_at >= day_before, User.created_at < yesterday)
            )
        )
        previous_users = previous_new_users.scalar()
        
        user_growth = ((current_users - previous_users) / previous_users * 100) if previous_users > 0 else 0
        
        # Content growth
        current_pages = await db.execute(
            select(func.count(PageV2.id)).where(PageV2.created_at >= yesterday)
        )
        current_pages_count = current_pages.scalar()
        
        previous_pages = await db.execute(
            select(func.count(PageV2.id)).where(
                and_(PageV2.created_at >= day_before, PageV2.created_at < yesterday)
            )
        )
        previous_pages_count = previous_pages.scalar()
        
        content_growth = ((current_pages_count - previous_pages_count) / previous_pages_count * 100) if previous_pages_count > 0 else 0
        
        return {
            "user_growth_24h": round(user_growth, 2),
            "content_growth_24h": round(content_growth, 2)
        }
    
    @staticmethod
    async def _get_active_alerts(db: AsyncSession) -> List[Dict[str, Any]]:
        """Get active alerts and warnings"""
        now = datetime.utcnow()
        last_hour = now - timedelta(hours=1)
        
        # Get recent high severity events
        alerts = await db.execute(
            select(AuditLog).where(
                and_(
                    AuditLog.created_at >= last_hour,
                    AuditLog.severity.in_([SeverityLevel.HIGH, SeverityLevel.CRITICAL])
                )
            ).order_by(desc(AuditLog.created_at)).limit(5)
        )
        
        alert_list = []
        for alert in alerts.scalars():
            alert_list.append({
                "id": alert.id,
                "severity": alert.severity,
                "action": alert.action,
                "message": alert.error_message or alert.action,
                "timestamp": alert.created_at.isoformat(),
                "category": alert.category
            })
        
        return alert_list
    
    @staticmethod
    async def _get_recent_activity(db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent activity log"""
        recent_logs = await db.execute(
            select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)
        )
        
        activity_list = []
        for log in recent_logs.scalars():
            activity_list.append({
                "id": log.id,
                "action": log.action,
                "user_id": log.user_id,
                "timestamp": log.created_at.isoformat(),
                "success": log.success,
                "ip_address": log.ip_address
            })
        
        return activity_list
    
    @staticmethod
    async def _get_current_active_users(db: AsyncSession) -> int:
        """Get current active users count"""
        now = datetime.utcnow()
        last_5_minutes = now - timedelta(minutes=5)
        
        active = await db.execute(
            select(func.count(func.distinct(AuditLog.user_id))).where(
                and_(
                    AuditLog.created_at >= last_5_minutes,
                    AuditLog.user_id.is_not(None)
                )
            )
        )
        return active.scalar()
    
    @staticmethod
    async def _get_current_task_status() -> Dict[str, Any]:
        """Get current Celery task status"""
        try:
            celery_metrics = await MonitoringService.get_celery_monitoring_metrics()
            return celery_metrics.get("active_queues", {})
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    async def _get_system_resources() -> Dict[str, Any]:
        """Get current system resource usage"""
        try:
            system_metrics = await MonitoringService._get_system_metrics()
            return {
                "cpu_usage": system_metrics.get("cpu_percent", 0),
                "memory_usage": system_metrics.get("memory_percent", 0),
                "disk_usage": system_metrics.get("disk_percent", 0)
            }
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    async def _get_recent_errors(db: AsyncSession, minutes: int = 5) -> List[Dict[str, Any]]:
        """Get recent error logs"""
        now = datetime.utcnow()
        since = now - timedelta(minutes=minutes)
        
        errors = await db.execute(
            select(AuditLog).where(
                and_(
                    AuditLog.created_at >= since,
                    AuditLog.success is False,
                    AuditLog.error_message.is_not(None)
                )
            ).order_by(desc(AuditLog.created_at)).limit(5)
        )
        
        error_list = []
        for error in errors.scalars():
            error_list.append({
                "action": error.action,
                "error": error.error_message,
                "timestamp": error.created_at.isoformat()
            })
        
        return error_list
    
    @staticmethod
    async def _get_user_activity_chart(
        db: AsyncSession,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get user activity data for charts"""
        daily_users = await db.execute(
            select(
                func.date(AuditLog.created_at).label('date'),
                func.count(func.distinct(AuditLog.user_id)).label('active_users')
            ).where(
                and_(
                    AuditLog.created_at >= start_date,
                    AuditLog.created_at <= end_date,
                    AuditLog.user_id.is_not(None)
                )
            ).group_by(func.date(AuditLog.created_at)).order_by('date')
        )
        
        return [
            {"date": str(row.date), "active_users": row.active_users}
            for row in daily_users
        ]
    
    @staticmethod
    async def _get_content_processing_chart(
        db: AsyncSession,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get content processing data for charts"""
        daily_processing = await db.execute(
            select(
                func.date(PageV2.updated_at).label('date'),
                func.count(PageV2.id).label('pages_processed')
            ).where(
                and_(
                    PageV2.updated_at >= start_date,
                    PageV2.updated_at <= end_date,
                    PageV2.processed is True
                )
            ).group_by(func.date(PageV2.updated_at)).order_by('date')
        )
        
        return [
            {"date": str(row.date), "pages_processed": row.pages_processed}
            for row in daily_processing
        ]
    
    @staticmethod
    async def _get_entity_extraction_chart(
        db: AsyncSession,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get entity extraction data for charts"""
        daily_entities = await db.execute(
            select(
                func.date(ExtractedEntity.extracted_at).label('date'),
                func.count(ExtractedEntity.id).label('entities_extracted')
            ).where(
                and_(
                    ExtractedEntity.extracted_at >= start_date,
                    ExtractedEntity.extracted_at <= end_date
                )
            ).group_by(func.date(ExtractedEntity.extracted_at)).order_by('date')
        )
        
        return [
            {"date": str(row.date), "entities_extracted": row.entities_extracted}
            for row in daily_entities
        ]
    
    @staticmethod
    async def _get_security_events_chart(
        db: AsyncSession,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get security events data for charts"""
        daily_security = await db.execute(
            select(
                func.date(AuditLog.created_at).label('date'),
                func.count(AuditLog.id).label('security_events')
            ).where(
                and_(
                    AuditLog.created_at >= start_date,
                    AuditLog.created_at <= end_date,
                    AuditLog.category == AuditCategory.SECURITY_EVENT
                )
            ).group_by(func.date(AuditLog.created_at)).order_by('date')
        )
        
        return [
            {"date": str(row.date), "security_events": row.security_events}
            for row in daily_security
        ]
    
    @staticmethod
    async def _get_system_performance_chart(
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Get system performance data for charts (mock data for now)"""
        # This would ideally pull from a time-series database or monitoring system
        # For now, return mock data structure
        return [
            {"timestamp": start_date.isoformat(), "response_time": 250, "cpu_usage": 45},
            {"timestamp": end_date.isoformat(), "response_time": 280, "cpu_usage": 52}
        ]
    
    @staticmethod
    async def _get_geographic_distribution(db: AsyncSession) -> List[Dict[str, Any]]:
        """Get geographic distribution of users (mock data for now)"""
        # This would require IP geolocation data
        # For now, return mock data structure
        return [
            {"country": "United States", "users": 150, "percentage": 45.5},
            {"country": "United Kingdom", "users": 80, "percentage": 24.2},
            {"country": "Canada", "users": 50, "percentage": 15.2},
            {"country": "Australia", "users": 30, "percentage": 9.1},
            {"country": "Germany", "users": 20, "percentage": 6.0}
        ]
    
    @staticmethod
    async def _get_top_domains_and_projects(db: AsyncSession, days: int) -> Dict[str, List[Dict[str, Any]]]:
        """Get top domains and projects by activity"""
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Top domains by page count
        top_domains = await db.execute(
            select(
                Domain.domain_name,
                func.count(PageV2.id).label('page_count')
            ).select_from(
                Domain.__table__.join(
                    ProjectPage.__table__, 
                    ProjectPage.project_id == Domain.project_id
                ).join(
                    PageV2.__table__,
                    PageV2.id == ProjectPage.page_id
                )
            ).where(
                PageV2.created_at >= since_date
            ).group_by(Domain.domain_name).order_by(desc('page_count')).limit(10)
        )
        
        domains_data = [
            {"domain": row.domain_name, "page_count": row.page_count}
            for row in top_domains
        ]
        
        # Top projects by activity
        top_projects = await db.execute(
            select(
                Project.name,
                func.count(ProjectPage.id).label('activity_count')
            ).select_from(
                Project.__table__.join(ProjectPage.__table__)
            ).where(
                ProjectPage.added_at >= since_date
            ).group_by(Project.name).order_by(desc('activity_count')).limit(10)
        )
        
        projects_data = [
            {"project": row.name, "activity_count": row.activity_count}
            for row in top_projects
        ]
        
        return {
            "top_domains": domains_data,
            "top_projects": projects_data
        }