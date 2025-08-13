"""
User plans and rate limiting API endpoints
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_admin
from app.models.user import User
from app.models.plans import UserPlan, UserPlanUsage, PlanFeature, PlanTier
from app.services.plan_service import plan_service
from app.core.security import get_current_user

router = APIRouter()


@router.get("/current", response_model=Dict[str, Any])
async def get_current_plan(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's plan details"""
    try:
        plan = await plan_service.get_or_create_plan(db, current_user)
        rate_limit = await plan_service.get_or_create_rate_limit(db, current_user, plan)
        
        return {
            "plan": {
                "tier": plan.tier,
                "max_pages_per_minute": plan.max_pages_per_minute,
                "max_concurrent_jobs": plan.max_concurrent_jobs,
                "max_pages_per_session": plan.max_pages_per_session,
                "max_pages_per_day": plan.max_pages_per_day,
                "max_projects": plan.max_projects,
                "priority_processing": plan.priority_processing,
                "advanced_extraction": plan.advanced_extraction,
                "api_access": plan.api_access,
                "bulk_operations": plan.bulk_operations,
                "entity_extraction": plan.entity_extraction,
                "osint_features": plan.osint_features,
                "started_at": plan.started_at,
                "expires_at": plan.expires_at,
            },
            "rate_limit": {
                "pages_scraped_today": rate_limit.pages_scraped_today,
                "current_concurrent_jobs": rate_limit.current_concurrent_jobs,
                "priority_level": rate_limit.priority_level,
                "last_reset_date": rate_limit.last_reset_date,
            },
            "description": plan.get_plan_description() if hasattr(plan, 'get_plan_description') else {}
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get plan: {str(e)}"
        )


@router.get("/usage", response_model=Dict[str, Any])
async def get_usage_stats(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's usage statistics"""
    try:
        usage_stats = await plan_service.get_usage_stats(db, current_user, days)
        return usage_stats
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get usage stats: {str(e)}"
        )


@router.get("/rate-limit/check", response_model=Dict[str, Any])
async def check_rate_limit(
    operation: str = "scrape",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check if user can perform operation within rate limits"""
    try:
        allowed, message, limits_info = await plan_service.check_rate_limit(
            db, current_user, operation
        )
        
        return {
            "allowed": allowed,
            "message": message,
            "limits": limits_info
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check rate limit: {str(e)}"
        )


@router.get("/features", response_model=List[Dict[str, Any]])
async def get_available_features(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get features available to user based on their plan"""
    try:
        features = await plan_service.get_available_features(db, current_user)
        return features
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get features: {str(e)}"
        )


@router.get("/tiers", response_model=List[Dict[str, Any]])
async def get_plan_tiers():
    """Get all available plan tiers and their features"""
    try:
        tiers = []
        for tier in PlanTier:
            defaults = UserPlan.get_plan_defaults(tier)
            tiers.append({
                "tier": tier,
                "name": tier.value.title(),
                "features": defaults,
                "description": f"{tier.value.title()} tier plan"
            })
        
        return tiers
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get plan tiers: {str(e)}"
        )


@router.post("/upgrade")
async def upgrade_plan(
    new_tier: PlanTier,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upgrade user to a new plan tier (admin only for now)"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can upgrade plans"
        )
    
    try:
        plan = await plan_service.upgrade_plan(db, current_user, new_tier)
        return {
            "message": f"Plan upgraded to {new_tier}",
            "tier": plan.tier
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upgrade plan: {str(e)}"
        )


@router.post("/usage/record")
async def record_usage(
    operation: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Record usage for tracking (internal endpoint)"""
    try:
        await plan_service.record_usage(db, current_user, operation)
        return {"message": "Usage recorded"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record usage: {str(e)}"
        )


# Admin endpoints
@router.get("/admin/users/{user_id}/plan", response_model=Dict[str, Any])
async def get_user_plan(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get plan for specific user (admin only)"""
    try:
        # Get user
        from sqlmodel import select
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        plan = await plan_service.get_or_create_plan(db, user)
        rate_limit = await plan_service.get_or_create_rate_limit(db, user, plan)
        
        return {
            "user_id": user.id,
            "email": user.email,
            "plan": {
                "tier": plan.tier,
                "max_pages_per_minute": plan.max_pages_per_minute,
                "max_concurrent_jobs": plan.max_concurrent_jobs,
                "max_pages_per_day": plan.max_pages_per_day,
                "max_projects": plan.max_projects,
                "started_at": plan.started_at,
                "expires_at": plan.expires_at,
            },
            "rate_limit": {
                "pages_scraped_today": rate_limit.pages_scraped_today,
                "current_concurrent_jobs": rate_limit.current_concurrent_jobs,
                "priority_level": rate_limit.priority_level,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user plan: {str(e)}"
        )


@router.post("/admin/users/{user_id}/upgrade")
async def admin_upgrade_user_plan(
    user_id: int,
    new_tier: PlanTier,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Upgrade specific user's plan (admin only)"""
    try:
        # Get user
        from sqlmodel import select
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        plan = await plan_service.upgrade_plan(db, user, new_tier)
        return {
            "message": f"User {user.email} plan upgraded to {new_tier}",
            "user_id": user.id,
            "tier": plan.tier
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upgrade user plan: {str(e)}"
        )