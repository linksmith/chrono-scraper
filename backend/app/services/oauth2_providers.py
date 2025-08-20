"""
OAuth2 provider configurations for Chrono Scraper
"""
import secrets
import httpx
from typing import Dict, Any, Optional
from urllib.parse import urlencode
from fastapi import HTTPException, status

from app.core.config import settings


class OAuth2Provider:
    """Base class for OAuth2 providers"""
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
    
    def get_authorization_url(self, state: str) -> str:
        """Get authorization URL for OAuth2 flow"""
        raise NotImplementedError
    
    async def get_access_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange authorization code for access token"""
        raise NotImplementedError
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information using access token"""
        raise NotImplementedError


class GoogleOAuth2Provider(OAuth2Provider):
    """Google OAuth2 provider implementation"""
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        super().__init__(client_id, client_secret, redirect_uri)
        self.authorization_base_url = "https://accounts.google.com/o/oauth2/auth"
        self.token_url = "https://oauth2.googleapis.com/token"
        self.user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        self.scope = "openid email profile"
    
    def get_authorization_url(self, state: str) -> str:
        """Generate Google OAuth2 authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "response_type": "code",
            "state": state,
            "access_type": "offline",  # Get refresh token
            "prompt": "consent"  # Force consent screen
        }
        
        return f"{self.authorization_base_url}?{urlencode(params)}"
    
    async def get_access_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange authorization code for Google access token"""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_url, data=data)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to get access token: {response.text}"
                )
            
            return response.json()
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get Google user information"""
        headers = {"Authorization": f"Bearer {access_token}"}
        
        async with httpx.AsyncClient() as client:
            response = await client.get(self.user_info_url, headers=headers)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to get user info: {response.text}"
                )
            
            user_data = response.json()
            
            # Standardize user data format
            return {
                "id": user_data.get("id"),
                "email": user_data.get("email"),
                "full_name": user_data.get("name", ""),
                "first_name": user_data.get("given_name", ""),
                "last_name": user_data.get("family_name", ""),
                "picture": user_data.get("picture"),
                "provider": "google",
                "verified_email": user_data.get("verified_email", False)
            }


class GitHubOAuth2Provider(OAuth2Provider):
    """GitHub OAuth2 provider implementation"""
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        super().__init__(client_id, client_secret, redirect_uri)
        self.authorization_base_url = "https://github.com/login/oauth/authorize"
        self.token_url = "https://github.com/login/oauth/access_token"
        self.user_info_url = "https://api.github.com/user"
        self.user_emails_url = "https://api.github.com/user/emails"
        self.scope = "user:email"
    
    def get_authorization_url(self, state: str) -> str:
        """Generate GitHub OAuth2 authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
            "state": state,
            "allow_signup": "true"
        }
        
        return f"{self.authorization_base_url}?{urlencode(params)}"
    
    async def get_access_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange authorization code for GitHub access token"""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri
        }
        
        headers = {"Accept": "application/json"}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.token_url, data=data, headers=headers)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to get access token: {response.text}"
                )
            
            return response.json()
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get GitHub user information"""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        async with httpx.AsyncClient() as client:
            # Get basic user info
            user_response = await client.get(self.user_info_url, headers=headers)
            
            if user_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to get user info: {user_response.text}"
                )
            
            user_data = user_response.json()
            
            # Get user emails (GitHub requires separate endpoint)
            emails_response = await client.get(self.user_emails_url, headers=headers)
            emails = []
            primary_email = user_data.get("email")  # Public email
            verified_email = False
            
            if emails_response.status_code == 200:
                emails_data = emails_response.json()
                for email_info in emails_data:
                    if email_info.get("primary", False):
                        primary_email = email_info.get("email")
                        verified_email = email_info.get("verified", False)
                        break
            
            # Parse full name
            full_name = user_data.get("name", "")
            name_parts = full_name.split(" ", 1) if full_name else ["", ""]
            first_name = name_parts[0] if len(name_parts) > 0 else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            
            # Standardize user data format
            return {
                "id": str(user_data.get("id")),
                "email": primary_email,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "picture": user_data.get("avatar_url"),
                "provider": "github",
                "verified_email": verified_email,
                "login": user_data.get("login"),
                "bio": user_data.get("bio"),
                "company": user_data.get("company"),
                "location": user_data.get("location"),
                "blog": user_data.get("blog")
            }


class OAuth2ProviderManager:
    """Manager for OAuth2 providers"""
    
    def __init__(self):
        self.providers: Dict[str, OAuth2Provider] = {}
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize OAuth2 providers based on configuration"""
        base_redirect_uri = f"{settings.BACKEND_URL or 'http://localhost:8000'}{settings.API_V1_STR}/auth/oauth2"
        
        # Initialize Google provider
        if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
            self.providers["google"] = GoogleOAuth2Provider(
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
                redirect_uri=f"{base_redirect_uri}/google/callback"
            )
        
        # Initialize GitHub provider
        if settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET:
            self.providers["github"] = GitHubOAuth2Provider(
                client_id=settings.GITHUB_CLIENT_ID,
                client_secret=settings.GITHUB_CLIENT_SECRET,
                redirect_uri=f"{base_redirect_uri}/github/callback"
            )
    
    def get_provider(self, provider_name: str) -> OAuth2Provider:
        """Get OAuth2 provider by name"""
        if provider_name not in self.providers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"OAuth2 provider '{provider_name}' not configured"
            )
        
        return self.providers[provider_name]
    
    def list_enabled_providers(self) -> list[str]:
        """Get list of enabled OAuth2 providers"""
        return list(self.providers.keys())
    
    def is_enabled(self) -> bool:
        """Check if OAuth2 is enabled and has at least one provider"""
        return settings.OAUTH2_ENABLED and len(self.providers) > 0


# Global OAuth2 provider manager instance
oauth2_manager = OAuth2ProviderManager()


# Utility functions
def generate_oauth2_state() -> str:
    """Generate secure OAuth2 state parameter"""
    return secrets.token_urlsafe(32)


def validate_oauth2_state(provided_state: str, stored_state: str) -> bool:
    """Validate OAuth2 state parameter"""
    if not provided_state or not stored_state:
        return False
    
    return secrets.compare_digest(provided_state, stored_state)