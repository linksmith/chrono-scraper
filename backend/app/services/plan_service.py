"""
User plan management service
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plans import UserPlan, UserRateLimit, UserPlanUsage, PlanFeature, PlanTier
from app.models.user import User

logger = logging.getLogger(__name__)


class PlanService:
    """Service for managing user plans and rate limiting"""
    
    async def get_or_create_plan(self, db: AsyncSession, user: User) -> UserPlan:
        """Get or create user plan with defaults"""
        try:
            # Check if plan exists
            result = await db.execute(
                select(UserPlan).where(UserPlan.user_id == user.id)
            )
            plan = result.scalar_one_or_none()
            
            if plan:
                return plan
            
            # Create new plan with defaults
            tier = PlanTier.UNLIMITED if user.is_superuser else PlanTier.SPARK
            defaults = UserPlan.get_plan_defaults(tier)
            
            plan = UserPlan(
                user_id=user.id,
                tier=tier,
                **defaults
            )
            
            db.add(plan)
            await db.commit()
            await db.refresh(plan)
            
            # Create corresponding rate limit
            await self.get_or_create_rate_limit(db, user, plan)
            
            logger.info(f"Created {tier} plan for user {user.email}")
            return plan
            
        except Exception as e:
            logger.error(f"Failed to create plan for user {user.id}: {e}")
            await db.rollback()
            raise
    
    async def get_or_create_rate_limit(
        self, 
        db: AsyncSession, 
        user: User, 
        plan: Optional[UserPlan] = None
    ) -> UserRateLimit:
        """Get or create rate limit for user"""
        try:
            # Get existing rate limit
            result = await db.execute(
                select(UserRateLimit).where(UserRateLimit.user_id == user.id)
            )
            rate_limit = result.scalar_one_or_none()
            
            if not plan:
                plan = await self.get_or_create_plan(db, user)
            
            if rate_limit:
                # Sync with current plan
                rate_limit.sync_with_plan(plan)
                await db.commit()
                return rate_limit
            
            # Create new rate limit
            rate_limit = UserRateLimit(
                user_id=user.id,
                plan_id=plan.id,
                max_pages_per_minute=plan.max_pages_per_minute,
                max_concurrent_jobs=plan.max_concurrent_jobs,
                max_pages_per_session=plan.max_pages_per_session,
                max_pages_per_day=plan.max_pages_per_day,
                priority_level=plan.get_priority_level(),
                default_timeout_seconds=60 if not plan.custom_timeout_limits else 30,
                max_timeout_seconds=120 if not plan.custom_timeout_limits else 300,
            )
            
            db.add(rate_limit)
            await db.commit()
            await db.refresh(rate_limit)
            
            logger.info(f"Created rate limit for user {user.email}")
            return rate_limit
            
        except Exception as e:
            logger.error(f"Failed to create rate limit for user {user.id}: {e}")
            await db.rollback()
            raise
    
    async def upgrade_plan(
        self, 
        db: AsyncSession, 
        user: User, 
        new_tier: PlanTier
    ) -> UserPlan:
        """Upgrade user to a new plan tier"""
        try:
            plan = await self.get_or_create_plan(db, user)
            old_tier = plan.tier
            
            # Get new plan defaults
            defaults = UserPlan.get_plan_defaults(new_tier)
            
            # Update plan
            plan.tier = new_tier
            for field, value in defaults.items():
                setattr(plan, field, value)
            plan.updated_at = datetime.utcnow()
            
            # Update rate limit
            rate_limit = await self.get_or_create_rate_limit(db, user, plan)
            rate_limit.sync_with_plan(plan)
            
            await db.commit()
            
            logger.info(f"Upgraded user {user.email} from {old_tier} to {new_tier}")
            return plan
            
        except Exception as e:
            logger.error(f"Failed to upgrade plan for user {user.id}: {e}")
            await db.rollback()
            raise
    
    async def check_rate_limit(
        self, 
        db: AsyncSession, 
        user: User,
        operation_type: str = "scrape"
    ) -> tuple[bool, str, Dict[str, Any]]:
        """Check if user can perform operation within rate limits"""
        try:
            rate_limit = await self.get_or_create_rate_limit(db, user)
            
            # Check if rate limiting is bypassed
            if rate_limit.bypass_rate_limits:
                return True, "Rate limits bypassed", {}
            
            # Reset daily counter if needed
            today = datetime.utcnow().date()
            if rate_limit.last_reset_date.date() < today:
                rate_limit.pages_scraped_today = 0
                rate_limit.last_reset_date = datetime.utcnow()
                await db.commit()
            
            # Check limits
            limits_info = {
                "daily_limit": rate_limit.max_pages_per_day,
                "daily_used": rate_limit.pages_scraped_today,
                "concurrent_limit": rate_limit.max_concurrent_jobs,
                "concurrent_used": rate_limit.current_concurrent_jobs,
                "priority_level": rate_limit.priority_level,
            }
            
            # Daily limit check
            if rate_limit.pages_scraped_today >= rate_limit.max_pages_per_day:
                return False, f"Daily limit reached: {rate_limit.max_pages_per_day} pages", limits_info
            
            # Concurrent jobs check
            if operation_type == "scrape" and rate_limit.current_concurrent_jobs >= rate_limit.max_concurrent_jobs:
                return False, f"Concurrent job limit reached: {rate_limit.max_concurrent_jobs}", limits_info
            
            return True, "Within rate limits", limits_info
            
        except Exception as e:
            logger.error(f"Failed to check rate limit for user {user.id}: {e}")
            return False, "Rate limit check failed", {}
    
    async def record_usage(
        self, 
        db: AsyncSession, 
        user: User,
        operation: str,
        **kwargs
    ):
        """Record usage for tracking and billing"""
        try:
            today = datetime.utcnow().date()
            
            # Get or create usage record for today
            result = await db.execute(
                select(UserPlanUsage).where(
                    UserPlanUsage.user_id == user.id,
                    func.date(UserPlanUsage.date) == today
                )
            )
            usage = result.scalar_one_or_none()
            
            if not usage:
                plan = await self.get_or_create_plan(db, user)
                usage = UserPlanUsage(
                    user_id=user.id,
                    plan_id=plan.id,
                    date=datetime.utcnow()
                )
                db.add(usage)
            
            # Update usage metrics based on operation
            if operation == "page_scraped":
                usage.pages_scraped += 1
                if kwargs.get("success", True):
                    # Update rate limit counter
                    rate_limit = await self.get_or_create_rate_limit(db, user)
                    rate_limit.pages_scraped_today += 1
                    
            elif operation == "project_created":
                usage.projects_created += 1
                
            elif operation == "api_call":
                usage.api_calls += 1
                
            elif operation == "search":
                usage.searches_performed += 1
                
            elif operation == "entity_extracted":
                usage.entities_extracted += kwargs.get("count", 1)
            
            # Update performance metrics
            if "scrape_time" in kwargs:
                usage.total_scrape_time_seconds += int(kwargs["scrape_time"])
                if usage.pages_scraped > 0:
                    usage.average_pages_per_minute = (usage.pages_scraped * 60.0) / usage.total_scrape_time_seconds
            
            await db.commit()
            
        except Exception as e:
            logger.error(f"Failed to record usage for user {user.id}: {e}")
            await db.rollback()
    
    async def get_usage_stats(
        self, 
        db: AsyncSession, 
        user: User, 
        days: int = 30
    ) -> Dict[str, Any]:
        """Get usage statistics for user"""
        try:
            start_date = datetime.utcnow() - timedelta(days=days)
            
            result = await db.execute(
                select(UserPlanUsage).where(
                    UserPlanUsage.user_id == user.id,
                    UserPlanUsage.date >= start_date
                ).order_by(UserPlanUsage.date.desc())
            )
            usage_records = result.scalars().all()
            
            if not usage_records:
                return {
                    "total_pages": 0,
                    "total_searches": 0,
                    "total_api_calls": 0,
                    "total_entities": 0,
                    "daily_breakdown": [],
                    "performance_metrics": {}
                }
            
            total_pages = sum(r.pages_scraped for r in usage_records)
            total_searches = sum(r.searches_performed for r in usage_records)
            total_api_calls = sum(r.api_calls for r in usage_records)
            total_entities = sum(r.entities_extracted for r in usage_records)
            
            # Calculate performance metrics
            total_time = sum(r.total_scrape_time_seconds for r in usage_records)
            avg_pages_per_minute = (total_pages * 60.0 / total_time) if total_time > 0 else 0.0
            
            daily_breakdown = [
                {
                    "date": r.date.isoformat(),
                    "pages_scraped": r.pages_scraped,
                    "searches_performed": r.searches_performed,
                    "api_calls": r.api_calls,
                    "entities_extracted": r.entities_extracted,
                    "avg_pages_per_minute": r.average_pages_per_minute,
                }
                for r in usage_records
            ]
            
            return {
                "total_pages": total_pages,
                "total_searches": total_searches,
                "total_api_calls": total_api_calls,
                "total_entities": total_entities,
                "daily_breakdown": daily_breakdown,
                "performance_metrics": {
                    "avg_pages_per_minute": avg_pages_per_minute,
                    "total_scrape_time_hours": total_time / 3600.0,
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get usage stats for user {user.id}: {e}")
            return {}
    
    async def can_create_project(self, db: AsyncSession, user: User) -> tuple[bool, str]:
        """Check if user can create another project"""
        try:
            plan = await self.get_or_create_plan(db, user)
            
            # Count current projects
            result = await db.execute(
                select(func.count()).select_from(
                    select().select_from(
                        db.execute("SELECT id FROM projects WHERE user_id = :user_id")
                        .params(user_id=user.id)
                    ).subquery()
                )
            )
            current_count = result.scalar() or 0
            
            return plan.can_create_project(current_count)
            
        except Exception as e:
            logger.error(f"Failed to check project creation for user {user.id}: {e}")
            return False, "Failed to check project limits"
    
    async def get_available_features(
        self, 
        db: AsyncSession, 
        user: User
    ) -> List[Dict[str, Any]]:
        """Get features available to user based on their plan"""
        try:
            plan = await self.get_or_create_plan(db, user)
            
            result = await db.execute(select(PlanFeature))
            features = result.scalars().all()
            
            available_features = []
            for feature in features:
                if feature.is_available_for_tier(plan.tier):
                    available_features.append({
                        "name": feature.name,
                        "description": feature.description,
                        "code_name": feature.code_name,
                        "category": feature.category,
                    })
            
            return available_features
            
        except Exception as e:
            logger.error(f"Failed to get available features for user {user.id}: {e}")
            return []


# Global service instance
plan_service = PlanService()