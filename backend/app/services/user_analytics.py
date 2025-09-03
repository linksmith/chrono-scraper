"""
User analytics service for admin reporting and insights
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case

from app.models.user import User
from app.models.project import Project
from app.models.shared_pages import PageV2
from app.models.library import SearchHistory
from app.models.audit_log import AuditLog
from app.models.bulk_operations import UserAnalyticsRequest, UserAnalyticsResponse, UserActivitySummary


class UserAnalyticsService:
    """Service for generating user analytics and reports"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def generate_user_analytics(
        self, 
        request: UserAnalyticsRequest
    ) -> UserAnalyticsResponse:
        """Generate comprehensive user analytics"""
        
        # Set default date range if not provided
        end_date = request.date_range_end or datetime.utcnow()
        start_date = request.date_range_start or (end_date - timedelta(days=30))
        
        # Generate summary statistics
        summary = await self._generate_summary_stats(start_date, end_date, request)
        
        # Generate time series data
        time_series = await self._generate_time_series(start_date, end_date, request)
        
        # Generate breakdown data
        breakdowns = await self._generate_breakdowns(start_date, end_date, request)
        
        return UserAnalyticsResponse(
            summary=summary,
            time_series=time_series,
            breakdowns=breakdowns
        )
    
    async def _generate_summary_stats(
        self, 
        start_date: datetime, 
        end_date: datetime,
        request: UserAnalyticsRequest
    ) -> Dict[str, Any]:
        """Generate summary statistics"""
        
        # Base user query with filters
        base_query = select(User)
        if not request.include_inactive:
            base_query = base_query.where(User.is_active is True)
        
        # Total users
        total_users_result = await self.db.execute(select(func.count(User.id)))
        total_users = total_users_result.scalar() or 0
        
        # Users in date range
        users_in_range_query = base_query.where(
            and_(User.created_at >= start_date, User.created_at <= end_date)
        )
        users_in_range_result = await self.db.execute(select(func.count()).select_from(users_in_range_query.subquery()))
        users_in_range = users_in_range_result.scalar() or 0
        
        # Approval statistics
        approval_stats = await self._get_approval_stats(start_date, end_date, request)
        
        # Activity statistics
        activity_stats = await self._get_activity_stats(start_date, end_date, request)
        
        # Growth rate calculation
        previous_period_start = start_date - (end_date - start_date)
        previous_period_query = base_query.where(
            and_(User.created_at >= previous_period_start, User.created_at < start_date)
        )
        previous_period_result = await self.db.execute(select(func.count()).select_from(previous_period_query.subquery()))
        previous_period_users = previous_period_result.scalar() or 0
        
        growth_rate = 0
        if previous_period_users > 0:
            growth_rate = ((users_in_range - previous_period_users) / previous_period_users) * 100
        
        return {
            "total_users": total_users,
            "new_users_period": users_in_range,
            "growth_rate_percent": round(growth_rate, 2),
            "approval_stats": approval_stats,
            "activity_stats": activity_stats,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat()
        }
    
    async def _get_approval_stats(
        self, 
        start_date: datetime, 
        end_date: datetime,
        request: UserAnalyticsRequest
    ) -> Dict[str, Any]:
        """Get user approval statistics"""
        
        # Approval status counts
        approval_query = select(
            User.approval_status,
            func.count(User.id).label('count')
        ).where(
            and_(User.created_at >= start_date, User.created_at <= end_date)
        ).group_by(User.approval_status)
        
        if not request.include_inactive:
            approval_query = approval_query.where(User.is_active is True)
        
        approval_result = await self.db.execute(approval_query)
        approval_counts = {row.approval_status: row.count for row in approval_result}
        
        # Average approval time (for approved users)
        avg_approval_time_query = select(
            func.avg(
                func.extract('epoch', User.approval_date - User.created_at)
            ).label('avg_seconds')
        ).where(
            and_(
                User.approval_status == 'approved',
                User.approval_date.isnot(None),
                User.created_at >= start_date,
                User.created_at <= end_date
            )
        )
        
        avg_time_result = await self.db.execute(avg_approval_time_query)
        avg_approval_seconds = avg_time_result.scalar() or 0
        avg_approval_hours = round(avg_approval_seconds / 3600, 2) if avg_approval_seconds else 0
        
        return {
            "pending": approval_counts.get('pending', 0),
            "approved": approval_counts.get('approved', 0),
            "rejected": approval_counts.get('rejected', 0),
            "avg_approval_time_hours": avg_approval_hours,
            "approval_rate_percent": round(
                (approval_counts.get('approved', 0) / max(sum(approval_counts.values()), 1)) * 100, 2
            )
        }
    
    async def _get_activity_stats(
        self, 
        start_date: datetime, 
        end_date: datetime,
        request: UserAnalyticsRequest
    ) -> Dict[str, Any]:
        """Get user activity statistics"""
        
        # Active users (logged in within period)
        active_users_query = select(func.count(User.id)).where(
            and_(
                User.last_login >= start_date,
                User.last_login <= end_date,
                User.is_active is True
            )
        )
        active_users_result = await self.db.execute(active_users_query)
        active_users = active_users_result.scalar() or 0
        
        # Users with projects
        users_with_projects_query = select(func.count(func.distinct(Project.user_id))).where(
            and_(Project.created_at >= start_date, Project.created_at <= end_date)
        )
        users_with_projects_result = await self.db.execute(users_with_projects_query)
        users_with_projects = users_with_projects_result.scalar() or 0
        
        # Average login frequency
        avg_logins_query = select(func.avg(User.login_count)).where(
            and_(
                User.last_login >= start_date,
                User.is_active is True
            )
        )
        avg_logins_result = await self.db.execute(avg_logins_query)
        avg_logins = round(avg_logins_result.scalar() or 0, 2)
        
        return {
            "active_users": active_users,
            "users_with_projects": users_with_projects,
            "avg_login_count": avg_logins,
            "engagement_rate_percent": round((active_users / max(active_users, 1)) * 100, 2)
        }
    
    async def _generate_time_series(
        self, 
        start_date: datetime, 
        end_date: datetime,
        request: UserAnalyticsRequest
    ) -> List[Dict[str, Any]]:
        """Generate time series data for charts"""
        
        time_series_data = []
        
        # Determine time interval
        if request.group_by == "day":
            interval = timedelta(days=1)
            date_format = "%Y-%m-%d"
        elif request.group_by == "week":
            interval = timedelta(weeks=1)
            date_format = "%Y-W%U"
        else:  # month
            interval = timedelta(days=30)  # Approximate
            date_format = "%Y-%m"
        
        # Generate data points
        current_date = start_date
        while current_date <= end_date:
            next_date = current_date + interval
            
            data_point = {
                "period": current_date.strftime(date_format),
                "date": current_date.isoformat(),
            }
            
            # Add requested metrics
            if "registrations" in request.metrics:
                reg_query = select(func.count(User.id)).where(
                    and_(User.created_at >= current_date, User.created_at < next_date)
                )
                reg_result = await self.db.execute(reg_query)
                data_point["registrations"] = reg_result.scalar() or 0
            
            if "approvals" in request.metrics:
                app_query = select(func.count(User.id)).where(
                    and_(
                        User.approval_date >= current_date,
                        User.approval_date < next_date,
                        User.approval_status == 'approved'
                    )
                )
                app_result = await self.db.execute(app_query)
                data_point["approvals"] = app_result.scalar() or 0
            
            if "logins" in request.metrics:
                login_query = select(func.count(User.id)).where(
                    and_(
                        User.last_login >= current_date,
                        User.last_login < next_date
                    )
                )
                login_result = await self.db.execute(login_query)
                data_point["logins"] = login_result.scalar() or 0
            
            time_series_data.append(data_point)
            current_date = next_date
        
        return time_series_data
    
    async def _generate_breakdowns(
        self, 
        start_date: datetime, 
        end_date: datetime,
        request: UserAnalyticsRequest
    ) -> Dict[str, Dict[str, Any]]:
        """Generate breakdown statistics by various dimensions"""
        
        breakdowns = {}
        
        # Approval status breakdown
        approval_breakdown_query = select(
            User.approval_status,
            func.count(User.id).label('count')
        ).where(
            and_(User.created_at >= start_date, User.created_at <= end_date)
        ).group_by(User.approval_status)
        
        approval_result = await self.db.execute(approval_breakdown_query)
        breakdowns["approval_status"] = {
            row.approval_status: row.count for row in approval_result
        }
        
        # User type breakdown (based on research interests or affiliation)
        user_type_query = select(
            case(
                (User.academic_affiliation.isnot(None), 'Academic'),
                (User.professional_title.isnot(None), 'Professional'),
                else_='General'
            ).label('user_type'),
            func.count(User.id).label('count')
        ).where(
            and_(User.created_at >= start_date, User.created_at <= end_date)
        ).group_by('user_type')
        
        user_type_result = await self.db.execute(user_type_query)
        breakdowns["user_type"] = {
            row.user_type: row.count for row in user_type_result
        }
        
        # Geographic breakdown (if we had location data)
        # For now, we'll create a placeholder
        breakdowns["geographic"] = {
            "Unknown": len(breakdowns["approval_status"])
        }
        
        # Activity level breakdown
        activity_breakdown_query = select(
            case(
                (User.login_count > 10, 'High Activity'),
                (User.login_count > 3, 'Medium Activity'),
                (User.login_count > 0, 'Low Activity'),
                else_='No Activity'
            ).label('activity_level'),
            func.count(User.id).label('count')
        ).where(
            and_(User.created_at >= start_date, User.created_at <= end_date)
        ).group_by('activity_level')
        
        activity_result = await self.db.execute(activity_breakdown_query)
        breakdowns["activity_level"] = {
            row.activity_level: row.count for row in activity_result
        }
        
        return breakdowns
    
    async def get_user_activity_summary(
        self, 
        user_ids: Optional[List[int]] = None,
        limit: int = 100
    ) -> List[UserActivitySummary]:
        """Get detailed activity summary for users"""
        
        # Base query
        base_query = select(User)
        if user_ids:
            base_query = base_query.where(User.id.in_(user_ids))
        
        base_query = base_query.limit(limit).order_by(User.last_login.desc().nullslast())
        
        result = await self.db.execute(base_query)
        users = list(result.scalars().all())
        
        summaries = []
        for user in users:
            # Get additional activity metrics
            projects_count = await self._get_user_projects_count(user.id)
            pages_count = await self._get_user_pages_count(user.id)
            searches_count = await self._get_user_searches_count(user.id)
            
            # Calculate engagement score
            engagement_score = await self._calculate_engagement_score(user, projects_count, searches_count)
            
            summary = UserActivitySummary(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                login_count=user.login_count,
                last_login=user.last_login,
                projects_created=projects_count,
                pages_scraped=pages_count,
                searches_performed=searches_count,
                approval_status=user.approval_status,
                is_active=user.is_active,
                is_verified=user.is_verified,
                created_at=user.created_at,
                engagement_score=engagement_score
            )
            summaries.append(summary)
        
        return summaries
    
    async def _get_user_projects_count(self, user_id: int) -> int:
        """Get count of projects created by user"""
        query = select(func.count(Project.id)).where(Project.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar() or 0
    
    async def _get_user_pages_count(self, user_id: int) -> int:
        """Get count of pages scraped by user (via projects)"""
        query = select(func.count(PageV2.id)).join(
            Project, Project.id == PageV2.project_id
        ).where(Project.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar() or 0
    
    async def _get_user_searches_count(self, user_id: int) -> int:
        """Get count of searches performed by user"""
        query = select(func.count(SearchHistory.id)).where(SearchHistory.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar() or 0
    
    async def _calculate_engagement_score(
        self, 
        user: User, 
        projects_count: int, 
        searches_count: int
    ) -> float:
        """Calculate user engagement score (0-100)"""
        score = 0.0
        
        # Login frequency (max 30 points)
        login_score = min(user.login_count * 3, 30)
        score += login_score
        
        # Project creation (max 25 points)
        project_score = min(projects_count * 5, 25)
        score += project_score
        
        # Search activity (max 20 points)
        search_score = min(searches_count * 2, 20)
        score += search_score
        
        # Recency bonus (max 15 points)
        if user.last_login:
            days_since_login = (datetime.utcnow() - user.last_login).days
            if days_since_login <= 7:
                recency_score = 15 - (days_since_login * 2)
                score += max(recency_score, 0)
        
        # Account status bonus (max 10 points)
        if user.is_verified:
            score += 5
        if user.approval_status == 'approved':
            score += 5
        
        return round(min(score, 100.0), 2)
    
    async def get_admin_audit_summary(
        self, 
        start_date: datetime, 
        end_date: datetime
    ) -> Dict[str, Any]:
        """Get summary of admin audit activities"""
        
        # Get audit log counts by action
        audit_query = select(
            AuditLog.action,
            func.count(AuditLog.id).label('count'),
            func.sum(AuditLog.affected_count).label('total_affected')
        ).where(
            and_(
                AuditLog.created_at >= start_date,
                AuditLog.created_at <= end_date,
                AuditLog.admin_user_id.isnot(None)
            )
        ).group_by(AuditLog.action)
        
        audit_result = await self.db.execute(audit_query)
        audit_summary = {}
        
        for row in audit_result:
            audit_summary[row.action] = {
                'operations_count': row.count,
                'total_affected': row.total_affected or 0
            }
        
        # Get most active admins
        admin_activity_query = select(
            AuditLog.admin_user_id,
            User.email,
            func.count(AuditLog.id).label('operations_count')
        ).join(
            User, User.id == AuditLog.admin_user_id
        ).where(
            and_(
                AuditLog.created_at >= start_date,
                AuditLog.created_at <= end_date
            )
        ).group_by(AuditLog.admin_user_id, User.email).order_by(
            func.count(AuditLog.id).desc()
        ).limit(10)
        
        admin_result = await self.db.execute(admin_activity_query)
        top_admins = [
            {
                'admin_id': row.admin_user_id,
                'email': row.email,
                'operations_count': row.operations_count
            }
            for row in admin_result
        ]
        
        return {
            'audit_summary': audit_summary,
            'top_active_admins': top_admins,
            'period_start': start_date.isoformat(),
            'period_end': end_date.isoformat()
        }