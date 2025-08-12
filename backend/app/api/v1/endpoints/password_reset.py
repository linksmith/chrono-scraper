"""
Password reset endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr

from app.api.deps import get_db
from app.services.auth import request_password_reset, reset_password_with_token

router = APIRouter()


class PasswordResetRequest(BaseModel):
    """Password reset request schema"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation schema"""
    token: str
    new_password: str


class PasswordResetResponse(BaseModel):
    """Password reset response schema"""
    message: str


@router.post("/request", response_model=PasswordResetResponse)
async def request_password_reset_endpoint(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
) -> PasswordResetResponse:
    """
    Request password reset token
    """
    await request_password_reset(db, request.email)
    
    # Always return success to prevent email enumeration
    return PasswordResetResponse(
        message="If the email exists, a password reset link has been sent"
    )


@router.post("/confirm", response_model=PasswordResetResponse)
async def confirm_password_reset(
    request: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
) -> PasswordResetResponse:
    """
    Confirm password reset with token
    """
    success = await reset_password_with_token(
        db, 
        request.token, 
        request.new_password
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    return PasswordResetResponse(
        message="Password has been reset successfully"
    )