"""
Meilisearch Key Usage Analytics Service

Provides comprehensive analytics and metrics for Meilisearch key usage,
including usage patterns, performance metrics, and predictive insights.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from sqlmodel import select, and_, or_, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.meilisearch_audit import (
    MeilisearchKey, MeilisearchKeyType, MeilisearchUsageLog, MeilisearchSecurityEvent
)
from ..models.project import Project
from ..models.sharing import PublicSearchConfig, ProjectShare
from ..core.rate_limiter import rate_limiter, RateLimitType

logger = logging.getLogger(__name__)


class KeyAnalyticsService:
    """Service for analyzing Meilisearch key usage patterns and metrics"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_usage_overview(
        self, 
        days_back: int = 30
    ) -> Dict[str, Any]:
        """
        Get comprehensive usage overview across all keys
        
        Args:
            days_back: Number of days to analyze
            
        Returns:
            Dict containing usage statistics and trends
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Get overall usage statistics
        usage_stats_query = select(
            func.sum(MeilisearchKey.usage_count).label('total_requests'),
            func.avg(MeilisearchKey.usage_count).label('avg_requests_per_key'),
            func.count(MeilisearchKey.id).label('total_keys'),
            func.count(MeilisearchKey.id.op('FILTER')(
                MeilisearchKey.last_used_at >= cutoff_date
            )).label('active_keys'),
            func.count(MeilisearchKey.id.op('FILTER')(
                MeilisearchKey.last_used_at.is_(None)
            )).label('unused_keys')
        ).where(MeilisearchKey.is_active == True)
        
        usage_result = await self.db.execute(usage_stats_query)
        usage_stats = usage_result.first()
        
        # Get usage by key type
        usage_by_type_query = select(
            MeilisearchKey.key_type,
            func.sum(MeilisearchKey.usage_count).label('total_usage'),
            func.count(MeilisearchKey.id).label('key_count'),
            func.avg(MeilisearchKey.usage_count).label('avg_usage')
        ).where(
            MeilisearchKey.is_active == True
        ).group_by(MeilisearchKey.key_type)
        
        usage_by_type_result = await self.db.execute(usage_by_type_query)
        usage_by_type = usage_by_type_result.all()
        
        # Get top performing keys
        top_keys_query = select(
            MeilisearchKey,
            Project.name.label('project_name')
        ).join(Project, isouter=True).where(
            MeilisearchKey.is_active == True
        ).order_by(desc(MeilisearchKey.usage_count)).limit(10)
        
        top_keys_result = await self.db.execute(top_keys_query)
        top_keys = top_keys_result.all()
        
        # Calculate usage trends
        usage_trends = await self._calculate_usage_trends(days_back)
        
        # Get geographic distribution (if available from rate limiter)
        geographic_stats = await self._get_geographic_usage_stats()
        
        return {
            "period_days": days_back,
            "timestamp": datetime.utcnow(),
            "overview": {
                "total_requests": int(usage_stats.total_requests or 0),
                "average_requests_per_key": float(usage_stats.avg_requests_per_key or 0),
                "total_keys": int(usage_stats.total_keys or 0),
                "active_keys": int(usage_stats.active_keys or 0),
                "unused_keys": int(usage_stats.unused_keys or 0),
                "utilization_rate": (usage_stats.active_keys / usage_stats.total_keys * 100) if usage_stats.total_keys > 0 else 0
            },
            "usage_by_type": [
                {
                    "key_type": row.key_type.value,
                    "total_usage": int(row.total_usage or 0),
                    "key_count": int(row.key_count),
                    "average_usage": float(row.avg_usage or 0)
                }
                for row in usage_by_type
            ],
            "top_performing_keys": [
                {
                    "key_id": key.id,
                    "key_type": key.key_type.value,
                    "project_name": project_name,
                    "usage_count": key.usage_count,
                    "last_used_at": key.last_used_at,
                    "created_at": key.created_at
                }
                for key, project_name in top_keys
            ],
            "usage_trends": usage_trends,
            "geographic_stats": geographic_stats
        }
    
    async def get_project_analytics(
        self, 
        project_id: int, 
        days_back: int = 30
    ) -> Dict[str, Any]:
        """
        Get detailed analytics for a specific project
        
        Args:
            project_id: Project ID to analyze
            days_back: Number of days to analyze
            
        Returns:
            Dict containing project-specific analytics
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Get project keys
        project_keys_query = select(MeilisearchKey).where(
            and_(
                MeilisearchKey.project_id == project_id,
                MeilisearchKey.is_active == True
            )
        )
        
        keys_result = await self.db.execute(project_keys_query)
        project_keys = keys_result.scalars().all()
        
        if not project_keys:
            return {
                "project_id": project_id,
                "error": "No active keys found for project"
            }
        
        # Calculate usage statistics
        total_usage = sum(key.usage_count for key in project_keys)
        recent_usage = sum(
            key.usage_count for key in project_keys 
            if key.last_used_at and key.last_used_at >= cutoff_date
        )
        
        # Get sharing statistics
        sharing_stats = await self._get_project_sharing_stats(project_id)
        
        # Get performance metrics
        performance_metrics = await self._calculate_project_performance_metrics(
            project_id, project_keys, days_back
        )
        
        # Get usage patterns
        usage_patterns = await self._analyze_project_usage_patterns(project_keys, days_back)
        
        # Get security insights
        security_insights = await self._get_project_security_insights(project_id, days_back)
        
        return {
            "project_id": project_id,
            "period_days": days_back,
            "timestamp": datetime.utcnow(),
            "usage_summary": {
                "total_requests": total_usage,
                "recent_requests": recent_usage,
                "active_keys": len([k for k in project_keys if k.last_used_at and k.last_used_at >= cutoff_date]),
                "total_keys": len(project_keys),
                "usage_efficiency": (recent_usage / total_usage * 100) if total_usage > 0 else 0
            },
            "key_breakdown": [
                {
                    "key_type": key.key_type.value,
                    "usage_count": key.usage_count,
                    "last_used_at": key.last_used_at,
                    "age_days": (datetime.utcnow() - key.created_at).days,
                    "usage_rate": key.usage_count / max(1, (datetime.utcnow() - key.created_at).days)
                }
                for key in project_keys
            ],
            "sharing_statistics": sharing_stats,
            "performance_metrics": performance_metrics,
            "usage_patterns": usage_patterns,
            "security_insights": security_insights,
            "recommendations": await self._generate_project_recommendations(
                project_id, project_keys, sharing_stats, performance_metrics
            )
        }
    
    async def get_rate_limit_analytics(self, days_back: int = 7) -> Dict[str, Any]:
        """
        Get analytics on rate limiting effectiveness and patterns
        
        Args:
            days_back: Number of days to analyze
            
        Returns:
            Dict containing rate limiting analytics
        """
        try:
            # Get rate limiting statistics from Redis
            redis_client = await rate_limiter.get_redis()
            
            # Analyze rate limit patterns
            rate_limit_stats = {}
            blocked_identifiers = []
            
            # Scan for rate limit keys
            for rate_type in RateLimitType:
                pattern = f"rate_limit:{rate_type.value}:*"
                cursor = 0
                type_stats = {
                    "active_limits": 0,
                    "total_requests": 0,
                    "blocked_identifiers": 0
                }
                
                while True:
                    cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
                    
                    for key in keys:
                        try:
                            count = await redis_client.get(key)
                            if count:
                                type_stats["active_limits"] += 1
                                type_stats["total_requests"] += int(count)
                        except Exception as e:
                            logger.error(f"Error reading rate limit key {key}: {e}")
                    
                    if cursor == 0:
                        break
                
                # Check for blocked identifiers
                block_pattern = f"rate_limit_block:{rate_type.value}:*"
                cursor = 0
                
                while True:
                    cursor, block_keys = await redis_client.scan(cursor, match=block_pattern, count=100)
                    
                    for block_key in block_keys:
                        try:
                            block_info = await redis_client.get(block_key)
                            if block_info:
                                import json
                                block_data = json.loads(block_info)
                                
                                # Extract identifier from key
                                key_parts = block_key.split(':')
                                if len(key_parts) >= 4:
                                    identifier = ':'.join(key_parts[3:])
                                    
                                    blocked_identifiers.append({
                                        "identifier": identifier,
                                        "rate_type": rate_type.value,
                                        "blocked_at": block_data.get("blocked_at"),
                                        "reason": block_data.get("reason"),
                                        "remaining_seconds": max(0, block_data.get("blocked_until", 0) - int(datetime.utcnow().timestamp()))
                                    })
                                    
                                    type_stats["blocked_identifiers"] += 1
                        except Exception as e:
                            logger.error(f"Error reading block key {block_key}: {e}")
                    
                    if cursor == 0:
                        break
                
                rate_limit_stats[rate_type.value] = type_stats
            
            # Calculate effectiveness metrics
            total_requests = sum(stats["total_requests"] for stats in rate_limit_stats.values())
            total_blocked = len(blocked_identifiers)
            
            effectiveness_score = 100
            if total_requests > 0:
                block_rate = (total_blocked / total_requests) * 100
                if block_rate > 10:  # High block rate might indicate overly restrictive limits
                    effectiveness_score -= (block_rate - 10) * 2
                elif block_rate < 1:  # Very low block rate might indicate limits are too loose
                    effectiveness_score -= (1 - block_rate) * 5
            
            return {
                "period_days": days_back,
                "timestamp": datetime.utcnow(),
                "rate_limit_statistics": rate_limit_stats,
                "blocked_identifiers": blocked_identifiers,
                "effectiveness_metrics": {
                    "total_requests_monitored": total_requests,
                    "total_identifiers_blocked": total_blocked,
                    "block_rate_percentage": (total_blocked / total_requests * 100) if total_requests > 0 else 0,
                    "effectiveness_score": max(0, min(100, effectiveness_score))
                },
                "recommendations": self._generate_rate_limit_recommendations(
                    rate_limit_stats, blocked_identifiers, total_requests
                )
            }
            
        except Exception as e:
            logger.error(f"Failed to get rate limit analytics: {e}")
            return {
                "error": f"Failed to retrieve rate limit analytics: {str(e)}",
                "timestamp": datetime.utcnow()
            }
    
    async def generate_usage_forecast(
        self, 
        project_id: Optional[int] = None, 
        forecast_days: int = 30
    ) -> Dict[str, Any]:
        """
        Generate usage forecast based on historical patterns
        
        Args:
            project_id: Optional project ID to focus on
            forecast_days: Number of days to forecast
            
        Returns:
            Dict containing usage forecast and recommendations
        """
        # Get historical data (90 days for better prediction)
        historical_days = 90
        cutoff_date = datetime.utcnow() - timedelta(days=historical_days)
        
        if project_id:
            # Project-specific forecast
            keys_query = select(MeilisearchKey).where(
                and_(
                    MeilisearchKey.project_id == project_id,
                    MeilisearchKey.is_active == True,
                    MeilisearchKey.created_at <= cutoff_date
                )
            )
        else:
            # System-wide forecast
            keys_query = select(MeilisearchKey).where(
                and_(
                    MeilisearchKey.is_active == True,
                    MeilisearchKey.created_at <= cutoff_date
                )
            )
        
        keys_result = await self.db.execute(keys_query)
        keys = keys_result.scalars().all()
        
        if not keys:
            return {
                "error": "Insufficient historical data for forecasting",
                "timestamp": datetime.utcnow()
            }
        
        # Calculate usage trends
        usage_data = []
        for key in keys:
            key_age_days = (datetime.utcnow() - key.created_at).days
            if key_age_days > 0:
                daily_usage_rate = key.usage_count / key_age_days
                usage_data.append(daily_usage_rate)
        
        if not usage_data:
            return {
                "error": "No usage data available for forecasting",
                "timestamp": datetime.utcnow()
            }
        
        # Simple linear trend calculation
        avg_daily_usage = sum(usage_data) / len(usage_data)
        
        # Calculate growth trend (simplified)
        recent_usage = sum(
            key.usage_count for key in keys 
            if key.last_used_at and key.last_used_at >= datetime.utcnow() - timedelta(days=30)
        )
        older_usage = sum(
            key.usage_count for key in keys 
            if key.last_used_at and key.last_used_at < datetime.utcnow() - timedelta(days=30)
        )
        
        growth_rate = 0
        if older_usage > 0:
            growth_rate = (recent_usage - older_usage) / older_usage
        
        # Generate forecast
        forecasted_usage = []
        for day in range(1, forecast_days + 1):
            projected_daily_usage = avg_daily_usage * (1 + growth_rate * (day / 30))
            forecasted_usage.append({
                "day": day,
                "projected_requests": max(0, int(projected_daily_usage)),
                "confidence": max(0.3, 1.0 - (day / forecast_days) * 0.7)  # Decreasing confidence over time
            })
        
        total_projected = sum(day["projected_requests"] for day in forecasted_usage)
        
        return {
            "project_id": project_id,
            "forecast_days": forecast_days,
            "timestamp": datetime.utcnow(),
            "historical_analysis": {
                "data_points": len(usage_data),
                "average_daily_usage": avg_daily_usage,
                "growth_rate": growth_rate,
                "recent_period_usage": recent_usage,
                "historical_period_usage": older_usage
            },
            "forecast": forecasted_usage,
            "summary": {
                "total_projected_requests": total_projected,
                "average_daily_projection": total_projected / forecast_days,
                "peak_day_projection": max(day["projected_requests"] for day in forecasted_usage),
                "confidence_level": sum(day["confidence"] for day in forecasted_usage) / len(forecasted_usage)
            },
            "recommendations": self._generate_forecast_recommendations(
                total_projected, avg_daily_usage, growth_rate
            )
        }
    
    # Helper methods
    async def _calculate_usage_trends(self, days_back: int) -> Dict[str, Any]:
        """Calculate usage trends over time"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        midpoint = datetime.utcnow() - timedelta(days=days_back // 2)
        
        # Get recent vs older usage
        recent_usage_query = select(
            func.sum(MeilisearchKey.usage_count)
        ).where(
            and_(
                MeilisearchKey.is_active == True,
                MeilisearchKey.last_used_at >= midpoint
            )
        )
        
        older_usage_query = select(
            func.sum(MeilisearchKey.usage_count)
        ).where(
            and_(
                MeilisearchKey.is_active == True,
                MeilisearchKey.last_used_at >= cutoff_date,
                MeilisearchKey.last_used_at < midpoint
            )
        )
        
        recent_result = await self.db.execute(recent_usage_query)
        older_result = await self.db.execute(older_usage_query)
        
        recent_usage = recent_result.scalar() or 0
        older_usage = older_result.scalar() or 0
        
        if older_usage > 0:
            change_percentage = ((recent_usage - older_usage) / older_usage) * 100
        else:
            change_percentage = 100 if recent_usage > 0 else 0
        
        trend_direction = "increasing" if change_percentage > 5 else "decreasing" if change_percentage < -5 else "stable"
        
        return {
            "recent_period_usage": recent_usage,
            "previous_period_usage": older_usage,
            "change_percentage": round(change_percentage, 2),
            "trend_direction": trend_direction
        }
    
    async def _get_geographic_usage_stats(self) -> Dict[str, Any]:
        """Get geographic usage statistics from rate limiter if available"""
        try:
            # This would require extending the rate limiter to track geographic data
            # For now, return basic placeholder
            return {
                "geographic_tracking": "not_implemented",
                "note": "Geographic tracking requires IP geolocation integration"
            }
        except Exception as e:
            logger.error(f"Error getting geographic stats: {e}")
            return {"error": str(e)}
    
    async def _get_project_sharing_stats(self, project_id: int) -> Dict[str, Any]:
        """Get sharing statistics for a project"""
        # Get public search config
        public_config_query = select(PublicSearchConfig).where(
            PublicSearchConfig.project_id == project_id
        )
        public_result = await self.db.execute(public_config_query)
        public_config = public_result.scalar_one_or_none()
        
        # Get project shares
        shares_query = select(ProjectShare).where(
            ProjectShare.project_id == project_id
        )
        shares_result = await self.db.execute(shares_query)
        shares = shares_result.scalars().all()
        
        return {
            "public_search_enabled": bool(public_config and public_config.is_enabled),
            "total_shares": len(shares),
            "active_shares": len([s for s in shares if s.status.value == "active"]),
            "share_permissions": {
                perm: len([s for s in shares if s.permission.value == perm])
                for perm in set(s.permission.value for s in shares)
            } if shares else {}
        }
    
    async def _calculate_project_performance_metrics(
        self, 
        project_id: int, 
        keys: List[MeilisearchKey], 
        days_back: int
    ) -> Dict[str, Any]:
        """Calculate performance metrics for a project"""
        if not keys:
            return {"error": "No keys available for performance calculation"}
        
        # Calculate basic performance metrics
        total_usage = sum(key.usage_count for key in keys)
        key_ages = [(datetime.utcnow() - key.created_at).days for key in keys]
        avg_age = sum(key_ages) / len(key_ages) if key_ages else 0
        
        # Usage efficiency (usage per day per key)
        usage_efficiency = total_usage / (avg_age * len(keys)) if avg_age > 0 else 0
        
        return {
            "total_usage": total_usage,
            "average_key_age_days": round(avg_age, 1),
            "usage_efficiency": round(usage_efficiency, 2),
            "keys_per_type": {
                key_type.value: len([k for k in keys if k.key_type == key_type])
                for key_type in set(k.key_type for k in keys)
            }
        }
    
    async def _analyze_project_usage_patterns(
        self, 
        keys: List[MeilisearchKey], 
        days_back: int
    ) -> Dict[str, Any]:
        """Analyze usage patterns for project keys"""
        if not keys:
            return {"error": "No keys available for pattern analysis"}
        
        # Analyze usage distribution
        usage_counts = [key.usage_count for key in keys]
        if usage_counts:
            max_usage = max(usage_counts)
            min_usage = min(usage_counts)
            avg_usage = sum(usage_counts) / len(usage_counts)
        else:
            max_usage = min_usage = avg_usage = 0
        
        # Analyze temporal patterns
        recent_cutoff = datetime.utcnow() - timedelta(days=7)
        recently_used_keys = [k for k in keys if k.last_used_at and k.last_used_at >= recent_cutoff]
        
        return {
            "usage_distribution": {
                "max_usage": max_usage,
                "min_usage": min_usage,
                "average_usage": round(avg_usage, 2),
                "usage_variance": round(sum((x - avg_usage) ** 2 for x in usage_counts) / len(usage_counts), 2) if usage_counts else 0
            },
            "temporal_patterns": {
                "recently_active_keys": len(recently_used_keys),
                "dormant_keys": len(keys) - len(recently_used_keys),
                "activity_rate": (len(recently_used_keys) / len(keys) * 100) if keys else 0
            }
        }
    
    async def _get_project_security_insights(self, project_id: int, days_back: int) -> Dict[str, Any]:
        """Get security insights for a project"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Get security events for this project
        security_events_query = select(MeilisearchSecurityEvent).where(
            and_(
                MeilisearchSecurityEvent.metadata.op('->>')('project_id') == str(project_id),
                MeilisearchSecurityEvent.created_at >= cutoff_date
            )
        )
        
        events_result = await self.db.execute(security_events_query)
        events = events_result.scalars().all()
        
        # Analyze security events
        event_summary = defaultdict(int)
        severity_summary = defaultdict(int)
        
        for event in events:
            event_summary[event.event_type] += 1
            severity_summary[event.severity] += 1
        
        # Calculate security score
        security_score = 100
        security_score -= severity_summary.get("critical", 0) * 20
        security_score -= severity_summary.get("warning", 0) * 5
        security_score = max(0, security_score)
        
        return {
            "total_security_events": len(events),
            "events_by_type": dict(event_summary),
            "events_by_severity": dict(severity_summary),
            "security_score": security_score,
            "risk_level": "high" if security_score < 70 else "medium" if security_score < 90 else "low"
        }
    
    async def _generate_project_recommendations(
        self, 
        project_id: int, 
        keys: List[MeilisearchKey], 
        sharing_stats: Dict[str, Any], 
        performance_metrics: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations for project improvement"""
        recommendations = []
        
        # Key age recommendations
        old_keys = [k for k in keys if (datetime.utcnow() - k.created_at).days > 90]
        if old_keys:
            recommendations.append(f"Consider rotating {len(old_keys)} keys older than 90 days")
        
        # Usage efficiency recommendations
        efficiency = performance_metrics.get("usage_efficiency", 0)
        if efficiency < 1:
            recommendations.append("Low usage efficiency detected - consider optimizing key usage")
        
        # Sharing recommendations
        if sharing_stats.get("public_search_enabled") and not sharing_stats.get("active_shares"):
            recommendations.append("Public search is enabled but no active shares - review configuration")
        
        # Default recommendation
        if not recommendations:
            recommendations.append("Project security and performance are optimal")
        
        return recommendations
    
    def _generate_rate_limit_recommendations(
        self, 
        rate_limit_stats: Dict[str, Any], 
        blocked_identifiers: List[Dict], 
        total_requests: int
    ) -> List[str]:
        """Generate recommendations for rate limiting configuration"""
        recommendations = []
        
        # Check block rates by type
        for rate_type, stats in rate_limit_stats.items():
            if stats["blocked_identifiers"] > stats["total_requests"] * 0.1:  # >10% block rate
                recommendations.append(f"High block rate for {rate_type} - consider adjusting limits")
            elif stats["blocked_identifiers"] == 0 and stats["total_requests"] > 100:
                recommendations.append(f"No blocks detected for {rate_type} - limits may be too lenient")
        
        # Check for repeat offenders
        identifier_counts = defaultdict(int)
        for blocked in blocked_identifiers:
            identifier_counts[blocked["identifier"]] += 1
        
        repeat_offenders = [id for id, count in identifier_counts.items() if count > 3]
        if repeat_offenders:
            recommendations.append(f"Consider permanent blocking for {len(repeat_offenders)} repeat offenders")
        
        # Default recommendation
        if not recommendations:
            recommendations.append("Rate limiting configuration is optimal")
        
        return recommendations
    
    def _generate_forecast_recommendations(
        self, 
        total_projected: int, 
        avg_daily_usage: float, 
        growth_rate: float
    ) -> List[str]:
        """Generate recommendations based on usage forecast"""
        recommendations = []
        
        if growth_rate > 0.5:  # 50% growth
            recommendations.append("High growth rate detected - plan for capacity scaling")
        elif growth_rate < -0.3:  # 30% decline
            recommendations.append("Usage decline detected - review engagement strategies")
        
        if total_projected > 100000:  # High volume
            recommendations.append("High usage volume projected - consider optimization strategies")
        
        if avg_daily_usage < 10:  # Low usage
            recommendations.append("Low usage patterns detected - consider promoting features")
        
        if not recommendations:
            recommendations.append("Usage forecast appears healthy and sustainable")
        
        return recommendations


# Factory function for creating analytics service
async def get_analytics_service() -> KeyAnalyticsService:
    """Get analytics service instance with database session"""
    async for db in get_db():
        return KeyAnalyticsService(db)