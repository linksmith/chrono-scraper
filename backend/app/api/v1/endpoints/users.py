"""
User management endpoints
"""
from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_db
from app.api.deps import get_current_user, get_current_superuser
from app.models.user import User, UserUpdate, UserRead, UserReadWithStats
from app.services.user import UserService

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def read_user_me(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get current user
    """
    return current_user


@router.put("/me", response_model=UserRead)
async def update_user_me(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserUpdate,
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Update current user
    """
    return await UserService.update_user(db, current_user, user_in)


@router.get("/", response_model=List[UserRead])
async def read_users(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Retrieve users (superuser only)
    """
    result = await db.execute(
        select(User)
        .offset(skip)
        .limit(limit)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return users


@router.get("/{user_id}", response_model=UserReadWithStats)
async def read_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get a specific user by ID
    """
    # Only allow users to see their own profile or superusers to see any
    if user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions"
        )
    
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    # TODO: Add statistics like project count, pages scraped
    user_with_stats = UserReadWithStats(
        **user.model_dump(),
        project_count=0,  # Will be calculated from database
        total_pages_scraped=0  # Will be calculated from database
    )
    
    return user_with_stats


@router.post("/{user_id}/approve", response_model=UserRead)
async def approve_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Approve a user account (superuser only)
    """
    success = await UserService.approve_user(db, user_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    user = await UserService.get_user_by_id(db, user_id)
    return user


@router.post("/{user_id}/reject", response_model=UserRead)
async def reject_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Reject a user account (superuser only)
    """
    success = await UserService.reject_user(db, user_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    user = await UserService.get_user_by_id(db, user_id)
    return user