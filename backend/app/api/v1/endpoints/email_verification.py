"""
Email verification endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.services.auth import verify_email_with_token, send_verification_email, get_user_by_email

router = APIRouter()


class EmailVerificationRequest(BaseModel):
    """Email verification request schema"""
    token: str


class ResendVerificationRequest(BaseModel):
    """Resend verification email schema"""
    email: EmailStr


class EmailVerificationResponse(BaseModel):
    """Email verification response schema"""
    message: str


@router.post("/verify", response_model=EmailVerificationResponse)
async def verify_email(
    request: EmailVerificationRequest,
    db: AsyncSession = Depends(get_db)
) -> EmailVerificationResponse:
    """
    Verify email with token
    """
    success = await verify_email_with_token(db, request.token)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )
    
    return EmailVerificationResponse(
        message="Email verified successfully"
    )


@router.post("/resend", response_model=EmailVerificationResponse)
async def resend_verification_email(
    request: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db)
) -> EmailVerificationResponse:
    """
    Resend email verification
    """
    user = await get_user_by_email(db, request.email)
    
    if not user:
        # Don't reveal if email exists
        return EmailVerificationResponse(
            message="If the email exists and needs verification, a link has been sent"
        )
    
    if user.is_verified:
        return EmailVerificationResponse(
            message="Email is already verified"
        )
    
    if not user.email_verification_token:
        return EmailVerificationResponse(
            message="No verification token found"
        )
    
    await send_verification_email(user)
    
    return EmailVerificationResponse(
        message="Verification email sent"
    )


@router.get("/status", response_model=dict)
async def get_verification_status(
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Get current user's email verification status
    """
    return {
        "email": current_user.email,
        "is_verified": current_user.is_verified,
        "needs_verification": not current_user.is_verified and bool(current_user.email_verification_token)
    }