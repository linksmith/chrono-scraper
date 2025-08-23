"""
Admin user management endpoints for the admin dashboard
"""
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.api.deps import get_db, get_current_superuser
from app.models.user import User, UserRead, UserCreate
from app.core.security import get_password_hash

router = APIRouter()


@router.get("/users", response_model=List[dict])
async def get_all_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Get all users for admin management.
    
    Requires superuser permissions.
    """
    stmt = select(User).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    # Convert to dict format expected by frontend
    user_list = []
    for user in users:
        user_dict = {
            "id": user.id,
            "email": user.email,
            "username": user.email,  # Use email as username for compatibility
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_admin": user.is_superuser,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "approval_status": user.approval_status,
            "is_verified": user.is_verified
        }
        user_list.append(user_dict)
    
    return user_list


@router.post("/users", response_model=dict)
async def create_user(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    user_data: dict
) -> Any:
    """
    Create a new user (admin only).
    
    Requires superuser permissions.
    """
    # Check if user already exists
    stmt = select(User).where(User.email == user_data["email"])
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Create new user
    new_user = User(
        email=user_data["email"],
        full_name=user_data.get("full_name", ""),
        hashed_password=get_password_hash(user_data["password"]),
        is_active=user_data.get("is_active", True),
        is_superuser=user_data.get("is_admin", False),
        is_verified=user_data.get("is_verified", True),
        approval_status=user_data.get("approval_status", "approved"),
        data_handling_agreement=True,
        ethics_agreement=True,
        research_interests=user_data.get("research_interests", "Admin created user"),
        research_purpose=user_data.get("research_purpose", "Administrative"),
        expected_usage=user_data.get("expected_usage", "Standard usage")
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return {
        "id": new_user.id,
        "email": new_user.email,
        "username": new_user.email,  # Use email as username for compatibility
        "full_name": new_user.full_name,
        "is_active": new_user.is_active,
        "is_admin": new_user.is_superuser,
        "created_at": new_user.created_at.isoformat() if new_user.created_at else None,
        "last_login": new_user.last_login.isoformat() if new_user.last_login else None,
        "approval_status": new_user.approval_status,
        "is_verified": new_user.is_verified
    }


@router.patch("/users/{user_id}", response_model=dict)
async def update_user(
    user_id: int,
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    user_data: dict
) -> Any:
    """
    Update a user (admin only).
    
    Requires superuser permissions.
    """
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update user fields
    if "full_name" in user_data:
        user.full_name = user_data["full_name"]
    if "is_active" in user_data:
        user.is_active = user_data["is_active"]
    if "is_admin" in user_data:
        user.is_superuser = user_data["is_admin"]
    if "approval_status" in user_data:
        user.approval_status = user_data["approval_status"]
    
    await db.commit()
    await db.refresh(user)
    
    return {
        "id": user.id,
        "email": user.email,
        "username": user.email,  # Use email as username for compatibility
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_admin": user.is_superuser,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "approval_status": user.approval_status,
        "is_verified": user.is_verified
    }


@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: int,
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Delete a user (admin only).
    
    Requires superuser permissions.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    await db.delete(user)
    await db.commit()
    
    return {
        "message": "User deleted successfully",
        "user_id": user_id
    }


@router.post("/users/{user_id}/toggle-status", response_model=dict)
async def toggle_user_status(
    user_id: int,
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Toggle user active status (admin only).
    
    Requires superuser permissions.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify your own status"
        )
    
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    user.is_active = not user.is_active
    await db.commit()
    await db.refresh(user)
    
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "message": f"User {'activated' if user.is_active else 'deactivated'} successfully"
    }