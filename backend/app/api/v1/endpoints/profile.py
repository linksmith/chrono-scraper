"""
Profile management endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.api.deps import get_current_user
from app.core.security import get_password_hash, verify_password
from app.models.user import User, UserRead, UserUpdate
from app.models.plans import Plan
from pydantic import BaseModel, EmailStr
import secrets
from datetime import datetime, timedelta
from app.core.email_service import email_service

router = APIRouter()


class PasswordChangeRequest(BaseModel):
    """Request model for password change"""
    current_password: str
    new_password: str


class PasswordResetRequest(BaseModel):
    """Request model for password reset"""
    email: EmailStr


class PlanChangeRequest(BaseModel):
    """Request model for plan change"""
    plan_name: str  # free, flash, blaze, lightning


class APIKeysUpdate(BaseModel):
    """Request model for updating API keys"""
    openrouter_api_key: Optional[str] = None
    proxy_api_key: Optional[str] = None


@router.get("/me", response_model=UserRead)
async def get_current_profile(
    current_user: User = Depends(get_current_user)
):
    """Get current user profile"""
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_profile(
    user_update: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user profile"""
    # Update only provided fields
    update_data = user_update.dict(exclude_unset=True)
    
    # Don't allow updating password through this endpoint
    if 'password' in update_data:
        del update_data['password']
    
    # Don't allow updating email if it's already in use
    if 'email' in update_data and update_data['email'] != current_user.email:
        existing = await db.execute(
            select(User).where(User.email == update_data['email'])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)
    
    return current_user


@router.post("/change-password")
async def change_password(
    password_change: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password"""
    # Verify current password
    if not verify_password(password_change.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(password_change.new_password)
    current_user.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {"message": "Password changed successfully"}


@router.post("/request-password-reset")
async def request_password_reset(
    reset_request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """Request a password reset email"""
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == reset_request.email)
    )
    user = result.scalar_one_or_none()
    
    # Always return success to prevent email enumeration
    if not user:
        return {"message": "If the email exists, a reset link has been sent"}
    
    # Generate reset token
    reset_token = secrets.token_urlsafe(32)
    user.password_reset_token = reset_token
    user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
    
    await db.commit()
    
    # Send reset email
    try:
        await email_service.send_password_reset_email(
            email=user.email,
            token=reset_token,
            user_name=user.full_name or user.email
        )
    except Exception as e:
        # Log error but don't expose it to user
        print(f"Failed to send password reset email: {e}")
    
    return {"message": "If the email exists, a reset link has been sent"}


@router.patch("/api-keys", response_model=UserRead)
async def update_api_keys(
    api_keys: APIKeysUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user's personal API keys"""
    # Update only provided keys
    if api_keys.openrouter_api_key is not None:
        # In production, encrypt this before storing
        current_user.openrouter_api_key = api_keys.openrouter_api_key
    
    if api_keys.proxy_api_key is not None:
        # In production, encrypt this before storing
        current_user.proxy_api_key = api_keys.proxy_api_key
    
    current_user.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(current_user)
    
    return current_user


@router.post("/change-plan")
async def change_plan(
    plan_request: PlanChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user's subscription plan"""
    # Validate plan name
    valid_plans = ["free", "flash", "blaze", "lightning"]
    if plan_request.plan_name not in valid_plans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan. Must be one of: {', '.join(valid_plans)}"
        )
    
    # Check if plan exists in database
    result = await db.execute(
        select(Plan).where(Plan.name == plan_request.plan_name)
    )
    plan = result.scalar_one_or_none()
    
    if not plan:
        # Create default plan if it doesn't exist
        plan = Plan(
            name=plan_request.plan_name,
            display_name=plan_request.plan_name.title(),
            price_monthly=0 if plan_request.plan_name == "free" else 
                         29 if plan_request.plan_name == "flash" else
                         99 if plan_request.plan_name == "blaze" else 299,
            pages_per_month=1000 if plan_request.plan_name == "free" else
                           10000 if plan_request.plan_name == "flash" else
                           50000 if plan_request.plan_name == "blaze" else 200000,
            projects_limit=1 if plan_request.plan_name == "free" else
                          5 if plan_request.plan_name == "flash" else
                          20 if plan_request.plan_name == "blaze" else -1,
            rate_limit_per_minute=10 if plan_request.plan_name == "free" else
                                 30 if plan_request.plan_name == "flash" else
                                 60 if plan_request.plan_name == "blaze" else 120
        )
        db.add(plan)
        await db.commit()
    
    # Update user's plan
    current_user.current_plan = plan_request.plan_name
    current_user.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return {
        "message": f"Successfully changed to {plan_request.plan_name} plan",
        "plan": plan_request.plan_name
    }


@router.get("/plans")
async def get_available_plans(db: AsyncSession = Depends(get_db)):
    """Get all available subscription plans"""
    result = await db.execute(select(Plan))
    plans = result.scalars().all()
    
    # If no plans exist, create default ones
    if not plans:
        default_plans = [
            Plan(
                name="free",
                display_name="Free",
                price_monthly=0,
                pages_per_month=1000,
                projects_limit=1,
                rate_limit_per_minute=10,
                features=["Basic scraping", "1 project", "Community support"]
            ),
            Plan(
                name="flash",
                display_name="Flash",
                price_monthly=29,
                pages_per_month=10000,
                projects_limit=5,
                rate_limit_per_minute=30,
                features=["10K pages/month", "5 projects", "Email support", "API access"]
            ),
            Plan(
                name="blaze",
                display_name="Blaze",
                price_monthly=99,
                pages_per_month=50000,
                projects_limit=20,
                rate_limit_per_minute=60,
                features=["50K pages/month", "20 projects", "Priority support", "Advanced extraction"]
            ),
            Plan(
                name="lightning",
                display_name="Lightning",
                price_monthly=299,
                pages_per_month=200000,
                projects_limit=-1,  # Unlimited
                rate_limit_per_minute=120,
                features=["200K pages/month", "Unlimited projects", "24/7 support", "Custom features"]
            )
        ]
        
        for plan in default_plans:
            db.add(plan)
        
        await db.commit()
        plans = default_plans
    
    return plans