"""
Service for managing admin settings
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.admin_settings import AdminSettings, AdminSettingsUpdate
from app.core.config import settings


async def get_admin_settings(db: AsyncSession) -> AdminSettings:
    """
    Get admin settings, creating defaults if none exist.
    """
    # Try to get existing settings
    stmt = select(AdminSettings)
    result = await db.execute(stmt)
    admin_settings = result.scalar_one_or_none()
    
    if not admin_settings:
        # Create default settings based on current config
        admin_settings = AdminSettings(
            users_open_registration=settings.USERS_OPEN_REGISTRATION,
            allow_invitation_tokens=settings.ALLOW_INVITATION_TOKENS
        )
        db.add(admin_settings)
        await db.commit()
        await db.refresh(admin_settings)
    
    return admin_settings


async def update_admin_settings(
    db: AsyncSession,
    settings_update: AdminSettingsUpdate,
    updated_by_id: int
) -> AdminSettings:
    """
    Update admin settings.
    """
    # Get existing settings
    admin_settings = await get_admin_settings(db)
    
    # Update fields
    if settings_update.users_open_registration is not None:
        admin_settings.users_open_registration = settings_update.users_open_registration
    
    if settings_update.allow_invitation_tokens is not None:
        admin_settings.allow_invitation_tokens = settings_update.allow_invitation_tokens
    
    admin_settings.updated_by_id = updated_by_id
    
    await db.commit()
    await db.refresh(admin_settings)
    
    return admin_settings


async def can_register_users(db: AsyncSession) -> bool:
    """
    Check if user registration is currently allowed.
    Falls back to config if no admin settings exist.
    """
    try:
        admin_settings = await get_admin_settings(db)
        return admin_settings.users_open_registration
    except Exception:
        # Fall back to config if database is unavailable
        return settings.USERS_OPEN_REGISTRATION


async def can_create_invitation_tokens(db: AsyncSession) -> bool:
    """
    Check if invitation token creation is currently allowed.
    Falls back to config if no admin settings exist.
    """
    try:
        admin_settings = await get_admin_settings(db)
        return admin_settings.allow_invitation_tokens
    except Exception:
        # Fall back to config if database is unavailable
        return settings.ALLOW_INVITATION_TOKENS