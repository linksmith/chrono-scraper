"""
OAuth2 authentication endpoints
"""
from fastapi import APIRouter, HTTPException, status, Query, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.deps import get_db
from app.core.config import settings
from app.core.oauth2 import (
    get_oauth2_provider,
    OAuth2StateManager,
    normalize_oauth2_user_data
)
from app.services.auth import create_user, get_user_by_email, create_session
from app.models.user import UserCreate, UserRead
from app.services.session_store import get_session_store, SessionStore

router = APIRouter()


class OAuth2LoginResponse(BaseModel):
    """OAuth2 login redirect response"""
    authorization_url: str
    state: str


class OAuth2CallbackRequest(BaseModel):
    """OAuth2 callback request"""
    code: str
    state: str


@router.get("/providers", response_model=list[str])
async def get_oauth2_providers() -> list[str]:
    """
    Get available OAuth2 providers
    """
    if not settings.OAUTH2_ENABLED:
        return []
    
    providers = []
    
    if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
        providers.append("google")
    
    if settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET:
        providers.append("github")
    
    return providers


@router.post("/login/{provider}", response_model=OAuth2LoginResponse)
async def oauth2_login(provider: str) -> OAuth2LoginResponse:
    """
    Initiate OAuth2 login flow
    """
    if not settings.OAUTH2_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth2 authentication is disabled"
        )
    
    oauth2_provider = get_oauth2_provider(provider)
    if not oauth2_provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OAuth2 provider '{provider}' not found or not configured"
        )
    
    # Create state for security
    state = await OAuth2StateManager.create_state(provider)
    
    # Get authorization URL
    authorization_url = oauth2_provider.get_authorization_url(state)
    
    return OAuth2LoginResponse(
        authorization_url=authorization_url,
        state=state
    )


@router.post("/callback/{provider}", response_model=UserRead)
async def oauth2_callback(
    response: Response,
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store)
) -> UserRead:
    """
    Handle OAuth2 callback and create/login user
    """
    if not settings.OAUTH2_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="OAuth2 authentication is disabled"
        )
    
    # Validate state
    if not await OAuth2StateManager.validate_state(state, provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state parameter"
        )
    
    # Consume state (one-time use)
    await OAuth2StateManager.consume_state(state)
    
    # Get OAuth2 provider
    oauth2_provider = get_oauth2_provider(provider)
    if not oauth2_provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OAuth2 provider '{provider}' not found or not configured"
        )
    
    try:
        # Exchange code for token
        token_data = await oauth2_provider.exchange_code_for_token(code, state)
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get access token from OAuth2 provider"
            )
        
        # Get user info from provider
        user_info = await oauth2_provider.get_user_info(access_token)
        
        # Normalize user data
        normalized_data = normalize_oauth2_user_data(provider, user_info)
        
        if not normalized_data.get("email"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by OAuth2 provider"
            )
        
        # Check if user exists
        existing_user = await get_user_by_email(db, normalized_data["email"])
        
        if existing_user:
            # Update OAuth2 info if not set
            if not existing_user.oauth2_provider:
                existing_user.oauth2_provider = normalized_data["oauth2_provider"]
                existing_user.oauth2_id = normalized_data["oauth2_id"]
                await db.commit()
            
            user = existing_user
        else:
            # Create new user
            user_create_data = {
                "email": normalized_data["email"],
                "full_name": normalized_data["full_name"],
                "password": "oauth2_user",  # Placeholder password for OAuth2 users
                "is_verified": normalized_data["is_verified"],
                "oauth2_provider": normalized_data["oauth2_provider"],
                "oauth2_id": normalized_data["oauth2_id"],
                "approval_status": "approved"  # Auto-approve OAuth2 users
            }
            
            user_create = UserCreate(**user_create_data)
            user = await create_user(db, user_create, created_by_admin=True)
        
        # Create session for the user
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
        
        # Return user data
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
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth2 authentication failed: {str(e)}"
        )


@router.get("/config", response_model=dict)
async def get_oauth2_config() -> dict:
    """
    Get OAuth2 configuration for frontend
    """
    return {
        "enabled": settings.OAUTH2_ENABLED,
        "providers": await get_oauth2_providers()
    }