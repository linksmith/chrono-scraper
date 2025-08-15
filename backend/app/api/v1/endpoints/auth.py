"""
Authentication endpoints
"""
from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Body, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core import security
from app.core.config import settings
from app.api.deps import get_db, get_current_user
from app.schemas.token import Token
from app.schemas.user import Message
from app.models.user import User, UserCreate, UserRead
from app.services.auth import authenticate_user, create_user, create_login_token, create_session
from app.services.session_store import get_session_store, SessionStore

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


@router.post("/login", response_model=Token)
async def login(
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    user = await authenticate_user(
        db, email=form_data.username, password=form_data.password
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
    
    access_token, expires_at = await create_login_token(user)
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.post("/login/json", response_model=UserRead)
async def login_json(
    response: Response,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store),
    login_data: LoginRequest = Body(...)
) -> Any:
    """
    JSON-based login with Redis session authentication
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
    
    # Also set legacy JWT cookie for backwards compatibility
    access_token, expires_at = await create_login_token(user)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
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
    # Delete Redis session if exists
    session_id = request.cookies.get("session_id")
    if session_id:
        await session_store.delete_session(session_id)
    
    # Clear cookies
    response.delete_cookie(key="session_id")
    response.delete_cookie(key="access_token")  # Legacy support
    
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




@router.post("/test-token", response_model=UserRead)
async def test_token(
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Test access token
    """
    return current_user