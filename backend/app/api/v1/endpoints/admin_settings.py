"""
Admin settings management endpoints
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_superuser
from app.models.user import User
from app.models.admin_settings import AdminSettings, AdminSettingsRead, AdminSettingsUpdate
from app.services.admin_settings_service import get_admin_settings, update_admin_settings


router = APIRouter()


@router.get("/settings", response_model=AdminSettingsRead)
async def get_admin_settings_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser)
) -> Any:
    """
    Get current admin settings.
    
    Requires superuser permissions.
    """
    settings = await get_admin_settings(db)
    return settings


@router.patch("/settings", response_model=AdminSettingsRead)
async def update_admin_settings_endpoint(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
    settings_update: AdminSettingsUpdate
) -> Any:
    """
    Update admin settings.
    
    Requires superuser permissions.
    """
    if not any([
        settings_update.users_open_registration is not None,
        settings_update.allow_invitation_tokens is not None
    ]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one setting must be provided"
        )
    
    updated_settings = await update_admin_settings(
        db=db,
        settings_update=settings_update,
        updated_by_id=current_user.id
    )
    
    return updated_settings