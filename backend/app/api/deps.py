"""
Authentication and authorization dependencies
"""
from typing import Optional, Generator
from fastapi import Depends, HTTPException, status, WebSocket, Query
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_jwt_token, verify_api_key, CREDENTIALS_EXCEPTION
from app.models.user import User
from app.models.api_config import APIKey
from app.services.rbac import RBACService

# OAuth2 scheme for JWT tokens
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)

# Bearer scheme for API keys
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Get current authenticated user from JWT token
    """
    # Decode the token
    payload = verify_jwt_token(token)
    if payload is None:
        raise CREDENTIALS_EXCEPTION
    
    # Extract user ID from token
    user_id = payload.get("sub")
    if user_id is None:
        raise CREDENTIALS_EXCEPTION
    
    # Get user from database
    try:
        user_id = int(user_id)
    except ValueError:
        raise CREDENTIALS_EXCEPTION
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise CREDENTIALS_EXCEPTION
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current superuser
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user


async def get_current_verified_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Get current verified user
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified"
        )
    return current_user


async def get_current_approved_user(
    current_user: User = Depends(get_current_verified_user)
) -> User:
    """
    Get current approved user
    """
    if current_user.approval_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account not approved"
        )
    return current_user


async def get_user_from_api_key(
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
) -> Optional[User]:
    """
    Get user from API key (optional authentication)
    """
    if not credentials or not credentials.credentials:
        return None
    
    api_key = credentials.credentials
    
    # Check if it's an API key (starts with cs_)
    if not api_key.startswith("cs_"):
        return None
    
    # Get API key prefix for lookup
    from app.core.security import get_api_key_prefix
    key_prefix = get_api_key_prefix(api_key)
    
    # Find API key in database
    result = await db.execute(
        select(APIKey).where(
            APIKey.key_prefix == key_prefix,
            APIKey.active == True
        )
    )
    api_key_obj = result.scalar_one_or_none()
    
    if not api_key_obj:
        return None
    
    # Verify the key
    if not verify_api_key(api_key, api_key_obj.key_hash):
        return None
    
    # Check expiration
    from datetime import datetime
    if api_key_obj.expires_at and api_key_obj.expires_at < datetime.utcnow():
        return None
    
    # Update usage stats
    api_key_obj.total_requests += 1
    api_key_obj.last_used = datetime.utcnow()
    db.add(api_key_obj)
    await db.commit()
    
    # Get the user
    result = await db.execute(select(User).where(User.id == api_key_obj.user_id))
    user = result.scalar_one_or_none()
    
    return user


async def get_current_user_or_api_key(
    db: AsyncSession = Depends(get_db),
    jwt_user: Optional[User] = Depends(get_current_user),
    api_user: Optional[User] = Depends(get_user_from_api_key)
) -> User:
    """
    Get current user from either JWT token or API key
    """
    user = jwt_user or api_user
    
    if not user:
        raise CREDENTIALS_EXCEPTION
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return user


def check_user_permissions(required_permissions: list[str]):
    """
    Decorator to check user permissions using RBAC
    """
    async def permission_checker(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_approved_user)
    ):
        # Check each required permission
        for permission in required_permissions:
            has_permission = await RBACService.user_has_permission(
                db, current_user.id, permission
            )
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {permission}"
                )
        return current_user
    
    return permission_checker


def require_permission(permission: str):
    """
    Dependency to require a specific permission
    """
    async def permission_dependency(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_approved_user)
    ):
        has_permission = await RBACService.user_has_permission(
            db, current_user.id, permission
        )
        if not has_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}"
            )
        return current_user
    
    return permission_dependency


# Common permission dependencies
require_approved_user = Depends(get_current_approved_user)
require_verified_user = Depends(get_current_verified_user)
require_active_user = Depends(get_current_active_user)
require_superuser = Depends(get_current_superuser)

# Alias for admin (same as superuser)
require_admin = get_current_superuser


async def get_current_user_from_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    Get current user from WebSocket connection using token query parameter
    """
    if not token:
        return None
    
    # Decode the token
    payload = verify_jwt_token(token)
    if payload is None:
        return None
    
    # Extract user ID from token
    user_id = payload.get("sub")
    if user_id is None:
        return None
    
    # Get user from database
    try:
        user_id = int(user_id)
    except ValueError:
        return None
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        return None
    
    if not user.is_active:
        return None
    
    return user