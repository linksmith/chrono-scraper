"""
Authentication services
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.email import (
    send_email, 
    generate_password_reset_email, 
    generate_email_verification_email,
    generate_approval_notification_email
)
from app.models.user import User, UserCreate, UserUpdate
from app.services.session_store import SessionStore


async def create_user(
    db: AsyncSession, 
    user_create: UserCreate,
    created_by_admin: bool = False
) -> User:
    """
    Create a new user
    """
    # Create user data
    user_data = user_create.model_dump(exclude={"password"})
    
    # Handle OAuth2 users (they don't need real passwords)
    if hasattr(user_create, 'oauth2_provider') and getattr(user_create, 'oauth2_provider', None):
        # OAuth2 users get a placeholder password hash
        user_data["hashed_password"] = get_password_hash("oauth2_placeholder")
    else:
        user_data["hashed_password"] = get_password_hash(user_create.password)
    
    # Set initial status
    if created_by_admin:
        user_data["is_verified"] = True
        user_data["approval_status"] = "approved"
        user_data["approval_date"] = datetime.utcnow()
    else:
        # Generate email verification token if required
        if settings.REQUIRE_EMAIL_VERIFICATION:
            user_data["email_verification_token"] = secrets.token_urlsafe(32)
    
    user = User(**user_data)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Send verification email if required
    if settings.REQUIRE_EMAIL_VERIFICATION and not created_by_admin:
        await send_verification_email(user)
    
    return user


async def authenticate_user(
    db: AsyncSession, 
    email: str, 
    password: str
) -> Optional[User]:
    """
    Authenticate user with email and password
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    # Update login tracking
    user.last_login = datetime.utcnow()
    user.login_count += 1
    await db.commit()
    
    return user


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """
    Get user by email
    """
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    """
    Get user by ID
    """
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def request_password_reset(db: AsyncSession, email: str) -> bool:
    """
    Request password reset token
    Returns True if email was sent, False otherwise
    """
    user = await get_user_by_email(db, email)
    if not user:
        # Don't reveal if email exists or not
        return True
    
    # Generate reset token
    reset_token = secrets.token_urlsafe(32)
    user.password_reset_token = reset_token
    user.password_reset_expires = datetime.utcnow() + timedelta(
        hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS
    )
    
    await db.commit()
    
    # Send reset email
    subject, html_content = generate_password_reset_email(email, reset_token)
    return await send_email(email, subject, html_content)


async def reset_password_with_token(
    db: AsyncSession, 
    token: str, 
    new_password: str
) -> bool:
    """
    Reset password using token
    Returns True if successful, False otherwise
    """
    result = await db.execute(
        select(User).where(User.password_reset_token == token)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return False
    
    # Check if token is expired
    if not user.password_reset_expires or user.password_reset_expires < datetime.utcnow():
        return False
    
    # Update password and clear reset token
    user.hashed_password = get_password_hash(new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    
    await db.commit()
    return True


async def verify_email_with_token(db: AsyncSession, token: str) -> bool:
    """
    Verify email using token
    Returns True if successful, False otherwise
    """
    result = await db.execute(
        select(User).where(User.email_verification_token == token)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return False
    
    # Mark as verified and clear token
    user.is_verified = True
    user.email_verification_token = None
    
    await db.commit()
    return True


async def update_user(
    db: AsyncSession, 
    user: User, 
    user_update: UserUpdate
) -> User:
    """
    Update user information
    """
    update_data = user_update.model_dump(exclude_unset=True)
    
    # Handle password update
    if "password" in update_data:
        password = update_data.pop("password")
        update_data["hashed_password"] = get_password_hash(password)
    
    for field, value in update_data.items():
        setattr(user, field, value)
    
    await db.commit()
    await db.refresh(user)
    return user


async def approve_user(
    db: AsyncSession, 
    user_id: int, 
    approved_by_id: int,
    approved: bool = True
) -> Optional[User]:
    """
    Approve or reject user account
    """
    user = await get_user_by_id(db, user_id)
    if not user:
        return None
    
    user.approval_status = "approved" if approved else "rejected"
    user.approval_date = datetime.utcnow()
    user.approved_by_id = approved_by_id
    
    await db.commit()
    
    # Send notification email
    subject, html_content = generate_approval_notification_email(user.email, approved)
    await send_email(user.email, subject, html_content)
    
    return user


async def send_verification_email(user: User) -> bool:
    """
    Send email verification email
    """
    if not user.email_verification_token:
        return False
    
    subject, html_content = generate_email_verification_email(
        user.email, 
        user.email_verification_token
    )
    return await send_email(user.email, subject, html_content)


async def create_login_token(user: User) -> Tuple[str, datetime]:
    """
    Create access token for user (legacy support)
    Returns (token, expires_at)
    """
    token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), 
        expires_delta=token_expires
    )
    expires_at = datetime.utcnow() + token_expires
    
    return access_token, expires_at


async def create_session(session_store: SessionStore, user: User) -> str:
    """
    Create Redis session for user
    Returns session_id
    """
    user_data = {
        "id": user.id,
        "email": user.email,
        "username": user.email,  # Use email as username since no username field exists
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "is_admin": getattr(user, 'is_admin', False),  # Safe access for optional fields
        "is_superuser": user.is_superuser,
        "approval_status": user.approval_status
    }
    
    session_id = await session_store.create_session(user_data)
    return session_id