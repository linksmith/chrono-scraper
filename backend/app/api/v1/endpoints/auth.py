"""
Authentication endpoints
"""
from typing import Any
from datetime import datetime
from fastapi import APIRouter, Body, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core import security
from app.core.config import settings
from app.api.deps import get_db, get_current_user
from app.schemas.user import Message
from app.models.user import User, UserCreate, UserRead
from app.services.auth import authenticate_user, create_user, create_session
from app.services.session_store import get_session_store, SessionStore
from app.api.v1.endpoints.invitations import consume_invitation_token

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


@router.get("/me", response_model=UserRead)
async def read_auth_me(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get current authenticated user (alias for /users/me)
    """
    return current_user




@router.post("/login", response_model=UserRead)
async def login(
    response: Response,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store),
    login_data: LoginRequest = Body(...)
) -> Any:
    """
    Login with Redis session authentication
    """
    user = await authenticate_user(
        db, email=login_data.email, password=login_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Create Redis session
    session_id = await create_session(session_store, user)
    
    # Set session cookie
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    
    # Refresh user to ensure all fields are loaded and return clean object
    await db.refresh(user)
    
    # Return clean user data - create UserRead manually to avoid relationship loading issues
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        is_verified=user.is_verified,
        institutional_email=user.institutional_email,
        linkedin_profile=user.linkedin_profile,
        research_interests=user.research_interests,
        academic_affiliation=user.academic_affiliation,
        orcid_id=user.orcid_id,
        professional_title=user.professional_title,
        organization_website=user.organization_website,
        research_purpose=user.research_purpose,
        expected_usage=user.expected_usage,
        data_handling_agreement=user.data_handling_agreement,
        ethics_agreement=user.ethics_agreement,
        approval_status=user.approval_status,
        approval_date=user.approval_date,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login=user.last_login,
        login_count=user.login_count,
        current_plan=user.current_plan
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session_store: SessionStore = Depends(get_session_store)
) -> Any:
    """
    Logout by clearing session and cookies
    """
    session_id = request.cookies.get("session_id")
    if not session_id:
        # Align with previous JWT tests expecting 401 when no token/cookie is provided
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    try:
        await session_store.delete_session(session_id)
    except Exception:
        pass
    response.delete_cookie(key="session_id")
    return {"message": "Successfully logged out"}


@router.post("/register", response_model=UserRead)
async def register(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate
) -> Any:
    """
    Register a new user
    """
    if not settings.USERS_OPEN_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Open user registration is forbidden on this server"
        )
    
    user = await create_user(db, user_in)
    
    return user


# Backward-compatibility shims for legacy tests expecting token endpoints
class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh_token(_: RefreshRequest):
    """
    Legacy token refresh endpoint (session-auth incompatible).
    Return 400 to indicate unsupported.
    """
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token refresh not supported with session auth")


@router.post("/register-with-invitation", response_model=UserRead)
async def register_with_invitation(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: UserCreate,
    invitation_token: str = Body(..., embed=True)
) -> Any:
    """
    Register a new user with an invitation token.
    Bypasses admin approval requirement.
    """
    # First validate the invitation token
    token_consumed = await consume_invitation_token(
        db, invitation_token, user_in.email
    )
    
    if not token_consumed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation token"
        )
    
    # Create user with pre-approval (bypasses manual approval)
    user = await create_user(db, user_in, created_by_admin=False)
    
    # Auto-approve users who registered with invitation
    user.approval_status = "approved"
    user.approval_date = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    
    return user




@router.post("/test-token", response_model=UserRead)
async def test_token(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Test access token
    """
    return current_user