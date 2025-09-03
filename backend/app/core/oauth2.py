"""
OAuth2 providers configuration and utilities
"""
import secrets
from typing import Optional, Dict, Any
from datetime import datetime
import httpx
from fastapi import HTTPException, status

from app.core.config import settings


class OAuth2Provider:
    """Base OAuth2 provider class"""
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
    
    def get_authorization_url(self, state: str) -> str:
        """Get authorization URL for OAuth2 flow"""
        raise NotImplementedError
    
    async def exchange_code_for_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange authorization code for access token"""
        raise NotImplementedError
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from OAuth2 provider"""
        raise NotImplementedError


class GoogleOAuth2Provider(OAuth2Provider):
    """Google OAuth2 provider"""
    
    authorization_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    
    def get_authorization_url(self, state: str) -> str:
        """Get Google authorization URL"""
        scope = "openid email profile"
        return (
            f"{self.authorization_url}?"
            f"client_id={self.client_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"scope={scope}&"
            f"response_type=code&"
            f"state={state}&"
            f"access_type=offline&"
            f"prompt=consent"
        )
    
    async def exchange_code_for_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange Google authorization code for token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to exchange code for token"
                )
            
            return response.json()
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from Google"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.user_info_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user info"
                )
            
            return response.json()


class GitHubOAuth2Provider(OAuth2Provider):
    """GitHub OAuth2 provider"""
    
    authorization_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    user_info_url = "https://api.github.com/user"
    user_emails_url = "https://api.github.com/user/emails"
    
    def get_authorization_url(self, state: str) -> str:
        """Get GitHub authorization URL"""
        scope = "user:email"
        return (
            f"{self.authorization_url}?"
            f"client_id={self.client_id}&"
            f"redirect_uri={self.redirect_uri}&"
            f"scope={scope}&"
            f"state={state}"
        )
    
    async def exchange_code_for_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange GitHub authorization code for token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Accept": "application/json"}
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to exchange code for token"
                )
            
            return response.json()
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from GitHub"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with httpx.AsyncClient() as client:
            # Get user info
            user_response = await client.get(self.user_info_url, headers=headers)
            if user_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user info"
                )
            
            user_data = user_response.json()
            
            # Get user emails (GitHub doesn't always include email in user info)
            emails_response = await client.get(self.user_emails_url, headers=headers)
            if emails_response.status_code == 200:
                emails = emails_response.json()
                primary_email = next(
                    (email["email"] for email in emails if email["primary"]), 
                    None
                )
                if primary_email:
                    user_data["email"] = primary_email
            
            return user_data


class OAuth2StateManager:
    """Manage OAuth2 state for security using Redis"""
    
    @classmethod
    async def create_state(cls, provider: str, user_id: Optional[int] = None) -> str:
        """Create a new OAuth2 state"""
        from app.services.session_store import get_session_store
        
        state = secrets.token_urlsafe(32)
        {
            "provider": provider,
            "user_id": user_id,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": datetime.utcnow().timestamp() + 600  # 10 minutes
        }
        
        session_store = await get_session_store()
        await session_store.redis.setex(
            f"oauth2_state:{state}",
            600,  # 10 minutes TTL
            f"{provider}:{user_id or 'anonymous'}"
        )
        
        return state
    
    @classmethod
    async def validate_state(cls, state: str, provider: str) -> bool:
        """Validate OAuth2 state"""
        from app.services.session_store import get_session_store
        
        try:
            session_store = await get_session_store()
            stored_data = await session_store.redis.get(f"oauth2_state:{state}")
            
            if not stored_data:
                return False
            
            stored_provider, _ = stored_data.decode('utf-8').split(':', 1)
            
            # Check provider matches
            if stored_provider != provider:
                return False
            
            return True
            
        except Exception:
            return False
    
    @classmethod
    async def consume_state(cls, state: str) -> Optional[Dict[str, Any]]:
        """Consume OAuth2 state (one-time use)"""
        from app.services.session_store import get_session_store
        
        try:
            session_store = await get_session_store()
            stored_data = await session_store.redis.get(f"oauth2_state:{state}")
            
            if not stored_data:
                return None
            
            # Delete the state (one-time use)
            await session_store.redis.delete(f"oauth2_state:{state}")
            
            stored_provider, stored_user_id = stored_data.decode('utf-8').split(':', 1)
            
            return {
                "provider": stored_provider,
                "user_id": int(stored_user_id) if stored_user_id != 'anonymous' else None
            }
            
        except Exception:
            return None


# OAuth2 provider factory
def get_oauth2_provider(provider: str) -> Optional[OAuth2Provider]:
    """Get OAuth2 provider instance"""
    # Construct base redirect URI from backend URL
    base_backend_url = settings.BACKEND_URL or "http://localhost:8000"
    base_redirect_uri = f"{base_backend_url}{settings.API_V1_STR}/auth/oauth2"
    
    if provider == "google":
        client_id = getattr(settings, "GOOGLE_CLIENT_ID", None)
        client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", None)
        redirect_uri = f"{base_redirect_uri}/google/callback"
        
        if client_id and client_secret:
            return GoogleOAuth2Provider(client_id, client_secret, redirect_uri)
    
    elif provider == "github":
        client_id = getattr(settings, "GITHUB_CLIENT_ID", None)
        client_secret = getattr(settings, "GITHUB_CLIENT_SECRET", None)
        redirect_uri = f"{base_redirect_uri}/github/callback"
        
        if client_id and client_secret:
            return GitHubOAuth2Provider(client_id, client_secret, redirect_uri)
    
    return None


def normalize_oauth2_user_data(provider: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize user data from different OAuth2 providers"""
    if provider == "google":
        return {
            "email": user_data.get("email"),
            "full_name": user_data.get("name"),
            "oauth2_provider": provider,
            "oauth2_id": user_data.get("id"),
            "is_verified": user_data.get("verified_email", False),
        }
    
    elif provider == "github":
        return {
            "email": user_data.get("email"),
            "full_name": user_data.get("name") or user_data.get("login"),
            "oauth2_provider": provider,
            "oauth2_id": str(user_data.get("id")),
            "is_verified": True,  # GitHub emails are considered verified
        }
    
    return {}