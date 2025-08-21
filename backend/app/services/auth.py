"""
Authentication services
"""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.core.email import (
    send_email, 
    generate_password_reset_email, 
    generate_email_verification_email,
    generate_approval_notification_email
)
from app.core.email_templates import email_templates
from app.models.user import User, UserCreate, UserUpdate
from app.models.user_approval import UserEvaluation, ApprovalToken, ApprovalTokenAction
from app.services.session_store import SessionStore
from app.services.user_evaluation_service import (
    evaluate_user_registration,
    generate_admin_notification
)

logger = logging.getLogger(__name__)


async def create_user(
    db: AsyncSession, 
    user_create: UserCreate,
    created_by_admin: bool = False
) -> User:
    """
    Create a new user with integrated LLM evaluation
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
    
    # Check duplicate email early to return 400 instead of 500 on unique violation
    existing = await db.execute(select(User).where(User.email == user_data["email"]))
    if existing.scalar_one_or_none():
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User with this email is already registered")

    user = User(**user_data)
    db.add(user)
    try:
        await db.commit()
    except Exception as e:
        # Fallback: handle race-condition unique constraint
        await db.rollback()
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User with this email is already registered")
    await db.refresh(user)
    
    # Send verification email if required
    if settings.REQUIRE_EMAIL_VERIFICATION and not created_by_admin:
        await send_verification_email(user)
    
    # Trigger LLM evaluation and send notifications for regular users (not admin-created)
    if not created_by_admin:
        try:
            # Send initial confirmation to user
            await send_pending_approval_notification(user)
            
            # Trigger LLM evaluation and admin notification
            await trigger_user_evaluation(db, user)
        except Exception as e:
            logger.error(f"Failed to trigger user evaluation for {user.email}: {str(e)}")
            # Continue even if evaluation fails - user creation should succeed
    
    return user


async def trigger_user_evaluation(db: AsyncSession, user: User) -> None:
    """
    Trigger LLM evaluation for a new user registration
    """
    logger.info(f"Triggering LLM evaluation for user {user.email}")
    
    try:
        # Check if evaluation already exists
        stmt = select(UserEvaluation).where(UserEvaluation.user_id == user.id)
        result = await db.execute(stmt)
        existing_evaluation = result.scalar_one_or_none()
        
        if existing_evaluation:
            logger.info(f"User evaluation already exists for {user.email}")
            return
        
        # Perform LLM evaluation
        evaluation_result = await evaluate_user_registration(user)
        
        # Create evaluation record
        evaluation = UserEvaluation(
            user_id=user.id,
            overall_score=evaluation_result.overall_score,
            legitimacy_score=evaluation_result.legitimacy_score,
            research_intent_score=evaluation_result.research_intent_score,
            risk_score=evaluation_result.risk_score,
            recommendation=evaluation_result.recommendation,
            reasoning=evaluation_result.reasoning,
            confidence=evaluation_result.confidence,
            red_flags=evaluation_result.red_flags,
            positive_indicators=evaluation_result.positive_indicators,
            additional_checks_needed=evaluation_result.additional_checks_needed,
            manual_review_required=evaluation_result.manual_review_required
        )
        
        db.add(evaluation)
        
        # Generate approval tokens
        approval_token = ApprovalToken(
            user_id=user.id,
            token=f"approve_{secrets.token_urlsafe(32)}",
            action=ApprovalTokenAction.APPROVE,
            expires_at=datetime.utcnow() + timedelta(hours=72),
            admin_message=f"LLM Score: {evaluation_result.overall_score:.1f}/10"
        )
        
        denial_token = ApprovalToken(
            user_id=user.id,
            token=f"deny_{secrets.token_urlsafe(32)}",
            action=ApprovalTokenAction.DENY, 
            expires_at=datetime.utcnow() + timedelta(hours=72),
            admin_message=f"Registration denied. Score: {evaluation_result.overall_score:.1f}/10"
        )
        
        db.add(approval_token)
        db.add(denial_token)
        await db.commit()
        
        # Generate admin notification data
        notification_data = await generate_admin_notification(user, evaluation_result)
        
        # Send admin notification email
        await send_admin_approval_notification(user, evaluation_result, approval_token, denial_token)
        
        logger.info(f"User evaluation completed for {user.email}: {evaluation_result.recommendation} (score: {evaluation_result.overall_score:.1f}/10)")
        
    except Exception as e:
        logger.error(f"Error during user evaluation for {user.email}: {str(e)}")
        # Don't re-raise - user creation should still succeed
        await db.rollback()


async def send_admin_approval_notification(
    user: User,
    evaluation_result,
    approval_token: ApprovalToken,
    denial_token: ApprovalToken
) -> bool:
    """
    Send email notification to admin about new user registration using professional templates
    """
    try:
        # Get admin email from settings
        admin_email = getattr(settings, 'ADMIN_EMAIL', None)
        if not admin_email:
            logger.warning("ADMIN_EMAIL not configured - cannot send approval notifications")
            return False
        
        # Generate professional email content
        subject, html_content, text_content = email_templates.generate_admin_approval_notification(
            user=user,
            evaluation=evaluation_result,
            approval_token=approval_token.token,
            denial_token=denial_token.token
        )
        
        return await send_email(admin_email, subject, html_content, text_content)
        
    except Exception as e:
        logger.error(f"Failed to send admin approval notification: {str(e)}")
        return False


async def send_user_approval_confirmation(
    user: User,
    approved: bool,
    admin_message: Optional[str] = None
) -> bool:
    """
    Send confirmation email to user about approval/denial decision
    """
    try:
        subject, html_content, text_content = email_templates.generate_user_approval_confirmation(
            user=user,
            approved=approved,
            admin_message=admin_message
        )
        
        return await send_email(user.email, subject, html_content, text_content)
        
    except Exception as e:
        logger.error(f"Failed to send user approval confirmation to {user.email}: {str(e)}")
        return False


async def send_pending_approval_notification(user: User) -> bool:
    """
    Send initial confirmation email to user that registration is pending review
    """
    try:
        subject, html_content, text_content = email_templates.generate_pending_approval_notification(user)
        
        return await send_email(user.email, subject, html_content, text_content)
        
    except Exception as e:
        logger.error(f"Failed to send pending approval notification to {user.email}: {str(e)}")
        return False


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
        "is_admin": user.is_superuser,  # Map superuser status to admin for frontend compatibility
        "is_superuser": user.is_superuser,
        "approval_status": user.approval_status
    }
    
    session_id = await session_store.create_session(user_data)
    return session_id